"""Validation and Plotly rendering for chart payloads returned by MCP."""

from __future__ import annotations

from typing import Any

import plotly.express as px

CHART_TYPES = {"pie", "donut", "bar", "horizontal_bar", "line", "histogram", "scatter"}


class ChartValidationError(ValueError):
    pass


def validate_chart_payload(chart: dict[str, Any]) -> dict[str, Any]:
    spec = chart.get("spec", {})
    data = chart.get("data", {})
    chart_type = str(spec.get("chart_type") or data.get("chart_type") or "bar").lower()
    rows = data.get("rows") or []
    if chart_type not in CHART_TYPES:
        raise ChartValidationError(f"Unsupported chart type: {chart_type}")
    if not isinstance(rows, list) or not rows:
        raise ChartValidationError("There is not enough data to create this chart.")
    if len(rows) > 500:
        raise ChartValidationError("The chart contains too many points; add a filter or lower the limit.")
    if chart_type == "scatter":
        if not all(row.get("x") is not None and row.get("y") is not None for row in rows):
            raise ChartValidationError("A scatter plot requires numeric X and Y values.")
    elif not all(row.get("value") is not None for row in rows):
        raise ChartValidationError("The selected dataset does not contain numeric chart values.")
    return {
        "chart_type": chart_type,
        "title": spec.get("title") or data.get("title") or "Database chart",
        "rows": rows,
    }


def render_chart(chart: dict[str, Any]):
    validated = validate_chart_payload(chart)
    chart_type = validated["chart_type"]
    title = validated["title"]
    rows = validated["rows"]
    if chart_type in {"pie", "donut"}:
        figure = px.pie(rows, names="label", values="value", title=title, hole=0.48 if chart_type == "donut" else 0)
        figure.update_traces(textposition="inside", textinfo="percent+label")
    elif chart_type == "histogram":
        figure = px.histogram(rows, x="value", title=title, labels={"value": "Value", "count": "Count"}, nbins=10)
    elif chart_type == "scatter":
        figure = px.scatter(rows, x="x", y="y", hover_name="label", title=title, labels={"x": "X", "y": "Y"})
    elif chart_type == "horizontal_bar":
        figure = px.bar(rows, x="value", y="label", orientation="h", title=title, text_auto=True, labels={"label": "", "value": "Value"})
    elif chart_type == "line":
        figure = px.line(rows, x="label", y="value", title=title, markers=True, labels={"label": "", "value": "Value"})
    else:
        figure = px.bar(rows, x="label", y="value", title=title, text_auto=True, labels={"label": "", "value": "Value"})
    figure.update_layout(hovermode="x unified", margin={"t": 70, "l": 30, "r": 30, "b": 50})
    return figure

