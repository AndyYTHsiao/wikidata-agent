from src.agent import (
    Candidate,
    QueryResult,
    format_query_result,
)


def test_format_query_result():
    result = QueryResult(
        items=[
            Candidate(
                id="Q19837",
                label="Steve Jobs",
            ),
            Candidate(
                id="Q483382",
                label="Steve Wozniak",
            ),
        ]
    )

    output = format_query_result(result)

    assert output == ("- Steve Jobs (Q19837)\n- Steve Wozniak (Q483382)")


def test_format_empty_query_result():
    result = QueryResult(items=[])

    assert format_query_result(result) == "No results found."
