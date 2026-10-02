import pytest

from mcp_database_assistant import crud
from mcp_database_assistant.database import connect, seed_demo_data


@pytest.fixture
def college_db(tmp_path):
    path = tmp_path / "crud.db"
    seed_demo_data(path)
    return path


def test_generic_student_update_supports_any_editable_fields(college_db):
    result = crud.update_record(
        "students",
        {"id": 1},
        {"phone_number": "9876543210", "gender": "Male", "address": "Updated address", "current_semester": 7, "cgpa": 9.2},
        college_db,
    )
    assert result["success"] and result["record"]["current_semester"] == 7
    assert result["record"]["phone_number"] == "9876543210"
    with pytest.raises(ValueError, match="Protected"):
        crud.update_record("students", {"id": 1}, {"id": 99}, college_db)


def test_generic_crud_other_tables_and_foreign_keys(college_db):
    inserted = crud.insert_record("classrooms", {"building": "Block Z", "room_number": "999", "capacity": 40, "classroom_type": "Lecture Hall"}, college_db)
    room_id = inserted["record_id"]
    assert crud.update_record("classrooms", {"id": room_id}, {"capacity": 45}, college_db)["record"]["capacity"] == 45
    assert crud.delete_record("classrooms", {"id": room_id}, confirmed=True, db_path=college_db)["changed"]
    with pytest.raises(ValueError, match="constraints"):
        crud.insert_record("enrollments", {"student_id": 99999, "course_id": 1, "academic_year": 2024, "semester": 1, "enrollment_date": "2024-07-01"}, college_db)


def test_ambiguous_update_and_cascade_confirmation(college_db):
    with connect(college_db) as db:
        db.execute("UPDATE students SET name = 'Duplicate Student' WHERE id IN (1, 2)")
        db.commit()
    ambiguous = crud.update_record("students", {"name": "Duplicate Student"}, {"address": "x"}, college_db)
    assert ambiguous["ambiguous"] and not ambiguous["success"]
    blocked = crud.delete_record("students", {"id": 1}, confirmed=True, db_path=college_db)
    assert blocked["requires_cascade_confirmation"]
    deleted = crud.delete_record("students", {"id": 1}, confirmed=True, cascade_confirmed=True, db_path=college_db)
    assert deleted["changed"]
