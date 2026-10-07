import asyncio
import httpx
import os

from dotenv import load_dotenv
from pydantic import BaseModel
from dataclasses import dataclass, field


from typing import Literal

from agents import (
    Agent,
    RunContextWrapper,
    Runner,
    SQLiteSession,
)
from agents.decorators import tool
from pyparsing import ParseException
from rdflib.plugins.sparql.parser import parseQuery


AGENT_INSTRUCTIONS = """
Resolve the Wikidata entities and properties needed for the user's query.

Use the resolver tools to find candidate IDs and create a QueryPlan.

Do not answer the user's factual question from your own knowledge.
The final factual answer will be produced from the executed SPARQL results.

If the query is ambiguous, ask for clarification instead of creating a QueryPlan.
Never invent Wikidata IDs.

Use clarification only when the user's intended entity or property is ambiguous.

Do not use clarification for tool failures, API errors, rate limits,
or empty results caused by an error.

If a tool fails and the query cannot be resolved, return an error instead.
"""


class Candidate(BaseModel):
    id: str
    label: str
    description: str | None = None


class QueryPlan(BaseModel):
    subject_id: str
    property_id: str


class QueryResult(BaseModel):
    items: list[Candidate]
    error: str | None = None


class Output(BaseModel):
    entity_candidates: list[Candidate] | None = None
    property_candidates: list[Candidate] | None = None
    query_plan: QueryPlan | None = None
    clarification: str | None = None
    error: str | None = None


class SparqlValidation(BaseModel):
    valid: bool
    error: str | None = None


@dataclass
class WikidataContext:
    user_agent: str
    resolved_entity_ids: set[str] = field(default_factory=set)
    resolved_property_ids: set[str] = field(default_factory=set)


async def _resolve_candidates(
    ctx: RunContextWrapper[WikidataContext],
    mention: str,
    entity_type: Literal["item", "property"],
) -> list[Candidate]:
    if entity_type not in ("item", "property"):
        raise ValueError("entity_type must be 'item' or 'property'")

    params = {
        "action": "wbsearchentities",
        "search": mention,
        "language": "en",
        "uselang": "en",
        "format": "json",
        "type": entity_type,
        "limit": 5,
        "maxlag": 5,
    }

    headers = {
        "User-Agent": ctx.context.user_agent,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://www.wikidata.org/w/api.php",
            params=params,
            headers=headers,
        )

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "2"))
            await asyncio.sleep(retry_after)

            response = await client.get(
                "https://www.wikidata.org/w/api.php",
                params=params,
                headers=headers,
            )

        response.raise_for_status()
        data = response.json()

    candidates = [
        Candidate(
            id=item["id"],
            label=item.get("label", item["id"]),
            description=item.get("description"),
        )
        for item in data.get("search", [])
    ]

    # Update the context with resolved IDs for future validation
    if entity_type == "item":
        ctx.context.resolved_entity_ids.update(candidate.id for candidate in candidates)
    else:
        ctx.context.resolved_property_ids.update(
            candidate.id for candidate in candidates
        )

    return candidates


@tool
async def resolve_entity_candidates(
    ctx: RunContextWrapper[WikidataContext],
    mention: str,
) -> list[Candidate]:
    """Search Wikidata for item candidates matching an entity mention."""

    return await _resolve_candidates(
        ctx=ctx,
        mention=mention,
        entity_type="item",
    )


@tool
async def resolve_property_candidates(
    ctx: RunContextWrapper[WikidataContext],
    mention: str,
) -> list[Candidate]:
    """Search Wikidata for property candidates matching a relation mention."""

    return await _resolve_candidates(
        ctx=ctx,
        mention=mention,
        entity_type="property",
    )


def compile_query_plan(plan: QueryPlan) -> str:
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX bd: <http://www.bigdata.com/rdf#>

SELECT ?value ?valueLabel
WHERE {{
    wd:{plan.subject_id} wdt:{plan.property_id} ?value .

    SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "en,mul".
    }}
}}
""".strip()


def validate_query_plan(
    plan: QueryPlan,
    context: WikidataContext,
) -> bool:
    return (
        plan.subject_id in context.resolved_entity_ids
        and plan.property_id in context.resolved_property_ids
    )


def validate_sparql(sparql: str) -> SparqlValidation:
    try:
        parseQuery(sparql)
    except ParseException as error:
        return SparqlValidation(
            valid=False,
            error=str(error),
        )

    return SparqlValidation(
        valid=True,
    )


async def execute_sparql(
    sparql: str,
    user_agent: str,
) -> QueryResult:
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/sparql-results+json",
    }

    params = {
        "query": sparql,
        "format": "json",
    }

    timeout = httpx.Timeout(
        connect=10.0,
        read=65.0,
        write=10.0,
        pool=10.0,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                "https://query.wikidata.org/sparql",
                params=params,
                headers=headers,
            )

            response.raise_for_status()
            data = response.json()

    except httpx.ReadTimeout:
        return QueryResult(
            items=[],
            error="Wikidata SPARQL query timed out.",
        )

    items = []

    for binding in data["results"]["bindings"]:
        value = binding.get("value")
        label = binding.get("valueLabel")

        if value is None:
            continue

        uri = value["value"]

        items.append(
            Candidate(
                id=uri.rsplit("/", 1)[-1],
                label=label["value"] if label else uri,
            )
        )

    return QueryResult(items=items)


def format_query_result(result: QueryResult) -> str:
    if not result.items:
        return "No results found."

    return "\n".join(f"- {item.label} ({item.id})" for item in result.items)


agent = Agent[WikidataContext](
    name="wikidata_agent",
    instructions=AGENT_INSTRUCTIONS.strip(),
    tools=[resolve_entity_candidates, resolve_property_candidates],
    output_type=Output,
)


async def main():
    session = SQLiteSession("wikidata_conversation")

    user_agent = os.environ["WIKIDATA_USER_AGENT"]

    context = WikidataContext(
        user_agent=user_agent,
    )

    user_input = input("Query: ")

    result = await Runner.run(
        agent,
        user_input,
        context=context,
        session=session,
    )

    if result.final_output.error:
        print(result.final_output.error)
        return

    MAX_CLARIFICATIONS = 2
    clarification_count = 0

    while result.final_output.clarification:
        if clarification_count >= MAX_CLARIFICATIONS:
            print("Unable to resolve the query unambiguously.")
            return

        print(result.final_output.clarification)

        user_input = input("Clarification: ")

        result = await Runner.run(
            agent,
            user_input,
            context=context,
            session=session,
        )

        if result.final_output.error:
            print(result.final_output.error)
            return

        clarification_count += 1

    print("Entity Candidates:")
    for candidate in result.final_output.entity_candidates or []:
        print(f"  - {candidate.label} ({candidate.id}): {candidate.description}")

    print("Property Candidates:")
    for candidate in result.final_output.property_candidates or []:
        print(f"  - {candidate.label} ({candidate.id}): {candidate.description}")

    if result.final_output.query_plan is None:
        print("Unable to produce a QueryPlan.")
        return

    if not validate_query_plan(
        result.final_output.query_plan,
        context,
    ):
        print("Invalid QueryPlan: IDs were not returned by the resolver tools.")
        return

    compiled_query = compile_query_plan(result.final_output.query_plan)

    validation = validate_sparql(compiled_query)

    if not validation.valid:
        print(f"Invalid SPARQL: {validation.error}")
        return

    query_result = await execute_sparql(
        compiled_query,
        context.user_agent,
    )

    if query_result.error:
        print(query_result.error)
        return

    print("Results:")
    print(format_query_result(query_result))


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
