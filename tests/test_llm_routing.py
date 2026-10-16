from types import SimpleNamespace

from mcp_database_assistant.llm import _tools_for_request


def _tools(*names):
    return [SimpleNamespace(name=name) for name in names]


def test_grouped_count_requests_include_rows_tool():
    selected = _tools_for_request(
        _tools("list_students", "get_student_count", "search_students", "get_database_summary"),
        "How many students are there in each branch?",
    )
    assert {tool.name for tool in selected} == {
        "list_students",
        "get_student_count",
        "search_students",
        "get_database_summary",
    }
