import pytest

from mcp_database_assistant.charting import ChartValidationError, render_chart, validate_chart_payload


def test_chart_payload_validation_and_plotly_rendering():
    chart = {
        "spec": {"chart_type": "donut", "title": "Students by branch"},
        "data": {"rows": [{"label": "Computer Engineering", "value": 4}]},
    }
    validated = validate_chart_payload(chart)
    assert validated["chart_type"] == "donut"
    assert render_chart(chart).data


def test_chart_payload_rejects_empty_or_unsupported_data():
    with pytest.raises(ChartValidationError, match="not enough"):
        validate_chart_payload({"spec": {"chart_type": "bar"}, "data": {"rows": []}})
    with pytest.raises(ChartValidationError, match="Unsupported"):
        validate_chart_payload({"spec": {"chart_type": "radar"}, "data": {"rows": [{"value": 1}]}})
