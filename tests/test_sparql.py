from src.agent import (
    QueryPlan,
    compile_query_plan,
    validate_sparql,
)


def test_compile_query_plan():
    plan = QueryPlan(
        subject_id="Q312",
        property_id="P112",
    )

    sparql = compile_query_plan(plan)

    assert "wd:Q312" in sparql
    assert "wdt:P112" in sparql
    assert "SELECT ?value ?valueLabel" in sparql


def test_compiled_query_is_valid_sparql():
    plan = QueryPlan(
        subject_id="Q312",
        property_id="P112",
    )

    sparql = compile_query_plan(plan)
    validation = validate_sparql(sparql)

    assert validation.valid
    assert validation.error is None


def test_validate_sparql_rejects_invalid_query():
    sparql = """
    SELECT ?value
    WHERE {
        wd:Q312 wdt:P112
    """

    validation = validate_sparql(sparql)

    assert not validation.valid
    assert validation.error is not None
