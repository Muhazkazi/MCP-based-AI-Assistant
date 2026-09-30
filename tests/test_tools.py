import pytest

from mcp_database_assistant.database import connect, seed_demo_data
from mcp_database_assistant import db_tools


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "students.db"
    for student in [
        ("Rahul Sharma", "Computer Engineering", 3, 88, "rahul@example.com"),
        ("Meera Nair", "Information Technology", 2, 76, "meera@example.com"),
        ("Arjun Rao", "Computer Engineering", 4, 93, "arjun@example.com"),
    ]:
        db_tools.add_student(*student, db_path=path)
    return path


def test_list_get_search_and_filters(db_path):
    assert db_tools.list_students(db_path)["count"] == 3
    assert db_tools.get_student(1, db_path)["student"]["name"] == "Rahul Sharma"
    assert db_tools.search_students(min_marks=80, db_path=db_path)["count"] == 2
    assert db_tools.get_students_by_branch("computer", db_path)["count"] == 2
    assert db_tools.get_students_by_year(2, db_path)["count"] == 1


def test_statistics_and_top_students(db_path):
    assert db_tools.get_student_count(db_path)["count"] == 3
    assert db_tools.get_average_marks(db_path)["average_marks"] == pytest.approx(85.6666, rel=1e-3)
    assert db_tools.get_top_students(2, db_path)["students"][0]["name"] == "Arjun Rao"


def test_add_update_delete_persist(db_path):
    added = db_tools.add_student("Test Student", "Civil Engineering", 1, 81, db_path=db_path)
    student_id = added["student"]["id"]
    updated = db_tools.update_student(student_id, marks=91, db_path=db_path)
    assert updated["success"] and updated["changed"] and updated["student"]["marks"] == 91
    deleted = db_tools.delete_student(student_id, db_path=db_path)
    assert deleted["success"] and deleted["changed"]
    assert not db_tools.get_student(student_id, db_path)["found"]


def test_invalid_inputs_and_missing_records(db_path):
    with pytest.raises(ValueError, match="marks"):
        db_tools.add_student("Bad", "Arts", 1, 101, db_path=db_path)
    with pytest.raises(ValueError, match="student_id"):
        db_tools.get_student(0, db_path)
    with pytest.raises(ValueError, match="limit"):
        db_tools.get_top_students(0, db_path)
    assert db_tools.search_students(name="Nobody", db_path=db_path)["count"] == 0
    assert not db_tools.update_student(999, marks=50, db_path=db_path)["found"]
    assert not db_tools.delete_student(999, db_path=db_path)["found"]


def test_expanded_college_tools_and_chart_data(tmp_path):
    path = tmp_path / "college.db"
    counts = seed_demo_data(path)
    assert counts["students"] == 100
    assert counts["teachers"] == 20
    assert db_tools.list_departments(path)["count"] == 6
    assert db_tools.list_teachers(department="Information Technology", db_path=path)["count"] > 0
    assert db_tools.list_courses(db_path=path)["count"] == 30
    assert db_tools.list_enrollments(academic_year=2024, db_path=path)["count"] > 0
    assert db_tools.list_results(db_path=path)["count"] > 0
    assert db_tools.list_attendance(db_path=path)["count"] > 0
    assert db_tools.list_fees(payment_status="unpaid", db_path=path)["count"] > 0
    assert db_tools.search_library_books(category="Engineering", db_path=path)["count"] == 15
    chart = db_tools.get_chart_data("students_by_branch", chart_type="pie", db_path=path)
    assert chart["count"] == 6
    assert sum(row["value"] for row in chart["rows"]) == 100

