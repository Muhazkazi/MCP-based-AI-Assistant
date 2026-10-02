import pytest

from mcp_database_assistant import db_tools
from mcp_database_assistant.database import connect, seed_demo_data


@pytest.fixture
def relational_db(tmp_path):
    path = tmp_path / "relational.db"
    seed_demo_data(path)
    with connect(path) as db:
        db.execute("DELETE FROM students WHERE name LIKE 'Zoya%'")
        department_id = db.execute("SELECT id FROM departments ORDER BY id LIMIT 1").fetchone()[0]
        course_ids = [row[0] for row in db.execute("SELECT id FROM courses ORDER BY id LIMIT 2").fetchall()]
        db.execute("INSERT INTO students (name, full_name, branch, year, marks, department_id, academic_year, cgpa, data_origin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unknown')", ("Zoya", "Zoya", "Computer Engineering", 3, 88, department_id, 2024, 8.8))
        first = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO students (name, full_name, branch, year, marks, department_id, academic_year, cgpa, data_origin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unknown')", ("Zoya", "Zoya", "Computer Engineering", 3, 91, department_id, 2024, 9.1))
        second = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for student_id, course_id in ((first, course_ids[0]), (second, course_ids[1])):
            db.execute("INSERT INTO enrollments (student_id, course_id, academic_year, semester, enrollment_date) VALUES (?, ?, 2024, 3, '2024-07-15')", (student_id, course_id))
        db.commit()
    return path


def test_duplicate_names_are_distinguished_and_joined(relational_db):
    result = db_tools.query_college("students_by_name_courses", {"name": "zoya"}, db_path=relational_db)
    assert result["count"] == 2
    assert {row["student_id"] for row in result["rows"]}.__len__() == 2
    assert {row["course_id"] for row in result["rows"]}.__len__() == 2


def test_sql_generation_is_parameterized_and_does_not_execute(relational_db):
    result = db_tools.get_sql_query("students_by_name_courses", {"name": "Zoya"})
    assert "JOIN enrollments" in result["sql"]
    assert "JOIN courses" in result["sql"]
    assert "?" in result["sql"]
    assert "Zoya" not in result["sql"]
    with pytest.raises(ValueError):
        db_tools.query_college("students_by_name_courses", {"name": "Zoya", "sql": "DROP TABLE students"}, db_path=relational_db)


def test_provenance_is_explicit(relational_db):
    with connect(relational_db) as db:
        row = db.execute("SELECT data_origin, source_name FROM data_provenance ORDER BY id LIMIT 1").fetchone()
        assert row[0] == "synthetic_demo"
        assert "demonstration" in row[1].lower()
