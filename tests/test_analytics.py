from mcp_database_assistant.analytics import (
    branch_average_marks,
    branch_counts,
    marks_distribution,
    students_from_result,
    summary_values,
)


def test_analytics_use_mcp_student_rows():
    students = [
        {"id": 1, "branch": "Computer Engineering", "year": 2, "marks": 80},
        {"id": 2, "branch": "Computer Engineering", "year": 3, "marks": 90},
        {"id": 3, "branch": "Civil Engineering", "year": 2, "marks": 70},
    ]
    assert students_from_result({"students": students}) == students
    assert branch_counts(students) == [
        {"branch": "Computer Engineering", "students": 2},
        {"branch": "Civil Engineering", "students": 1},
    ]
    assert branch_average_marks(students) == [
        {"branch": "Civil Engineering", "average_marks": 70.0},
        {"branch": "Computer Engineering", "average_marks": 85.0},
    ]
    assert marks_distribution(students) == [80.0, 90.0, 70.0]
    assert summary_values(students, {"average_marks": 80.0}) == {
        "student_count": 3,
        "average_marks": 80.0,
        "branch_count": 2,
        "year_count": 2,
    }


def test_analytics_handle_empty_results():
    assert students_from_result({}) == []
    assert branch_counts([]) == []
    assert branch_average_marks([]) == []
    assert marks_distribution([]) == []
    assert summary_values([], {}) == {
        "student_count": 0,
        "average_marks": None,
        "branch_count": 0,
        "year_count": 0,
    }

