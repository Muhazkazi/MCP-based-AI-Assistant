"""Pure analytics helpers for data returned through MCP."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def students_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Return student rows from an MCP result, tolerating an empty response."""
    students = result.get("students", [])
    return students if isinstance(students, list) else []


def branch_counts(students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(student.get("branch") or "Unknown" for student in students)
    return [
        {"branch": branch, "students": count}
        for branch, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def branch_average_marks(students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    marks_by_branch: dict[str, list[float]] = defaultdict(list)
    for student in students:
        branch = student.get("branch") or "Unknown"
        marks = student.get("marks")
        if marks is not None:
            marks_by_branch[branch].append(float(marks))
    return [
        {"branch": branch, "average_marks": sum(marks) / len(marks)}
        for branch, marks in sorted(marks_by_branch.items())
        if marks
    ]


def marks_distribution(students: list[dict[str, Any]]) -> list[float]:
    return [float(student["marks"]) for student in students if student.get("marks") is not None]


def summary_values(students: list[dict[str, Any]], average_result: dict[str, Any]) -> dict[str, Any]:
    years = {student.get("year") for student in students if student.get("year") is not None}
    return {
        "student_count": len(students),
        "average_marks": average_result.get("average_marks"),
        "branch_count": len({student.get("branch") for student in students if student.get("branch")}),
        "year_count": len(years),
    }

