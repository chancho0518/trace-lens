"""Test the Transaction Analyzer graph.

Official document URL:
    https://docs.langchain.com/oss/python/langgraph/test"""

from __future__ import annotations

from casts.transaction_analyzer.graph import transaction_analyzer_graph


def test_graph_produces_message() -> None:
    graph = transaction_analyzer_graph()

    # Invoke with minimal state — OutputState filter exposes only the ``result`` key.
    result = graph.invoke({"query": "I'm joining Act"})

    # Verify SampleNode populated ``result``.
    assert "result" in result
    assert result["result"] == "Welcome to the Act!"
