from src.agent import (
    QueryPlan,
    WikidataContext,
    validate_query_plan,
)


def test_validate_query_plan_accepts_resolved_ids():
    context = WikidataContext(
        user_agent="test-agent",
        resolved_entity_ids={"Q312"},
        resolved_property_ids={"P112"},
    )

    plan = QueryPlan(
        subject_id="Q312",
        property_id="P112",
    )

    assert validate_query_plan(plan, context)


def test_validate_query_plan_rejects_unknown_entity():
    context = WikidataContext(
        user_agent="test-agent",
        resolved_entity_ids={"Q312"},
        resolved_property_ids={"P112"},
    )

    plan = QueryPlan(
        subject_id="Q999999",
        property_id="P112",
    )

    assert not validate_query_plan(plan, context)


def test_validate_query_plan_rejects_unknown_property():
    context = WikidataContext(
        user_agent="test-agent",
        resolved_entity_ids={"Q312"},
        resolved_property_ids={"P112"},
    )

    plan = QueryPlan(
        subject_id="Q312",
        property_id="P999999",
    )

    assert not validate_query_plan(plan, context)
