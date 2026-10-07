# Wikidata Agent

Wikidata Agent is an agent-based natural-language interface for Wikidata.

It resolves Wikidata entities and properties, handles ambiguity through multi-turn clarification, constructs validated query plans, compiles them into SPARQL, and executes grounded queries against Wikidata.


## Quick Start

1. Install dependencies:

```bash
uv sync
```

2. Create a `.env` file:

```
OPENAI_API_KEY=your_key_here
WIKIDATA_USER_AGENT=your_user-agent_header
```

3. Run the agent:

```bash
uv run python -m src.agent
```

4. Run the tests:
```
uv run --with pytest pytest
```

## Work Flow

```
User query
    ↓
Resolve entity and property candidates
    ↓
Clarify ambiguous mentions if needed
    ↓
Construct and validate QueryPlan
    ↓
Compile SPARQL
    ↓
Validate SPARQL syntax
    ↓
Execute query against Wikidata
    ↓
Format results
```

The LLM is responsible for interpreting the query, selecting among retrieved candidates, handling ambiguity, and constructing the query plan.

The remaining pipeline is deterministic Python responsible for validating resolved IDs, compiling and validating SPARQL, executing the query, and formatting the returned results.

## Future Update

- Handle multi-hop query planning
- More flexible SPARQL generation