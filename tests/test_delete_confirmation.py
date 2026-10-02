import time

import pytest

from mcp_database_assistant import crud
from mcp_database_assistant.database import connect, seed_demo_data
from mcp_database_assistant import server


@pytest.fixture
def delete_db(tmp_path, monkeypatch):
    path = tmp_path / "delete.db"
    seed_demo_data(path)
    with connect(path) as db:
        for index in range(4):
            db.execute("INSERT INTO classrooms (building, room_number, capacity, classroom_type) VALUES (?, ?, ?, ?)", ("Test Block", str(900 + index), 20, "Test"))
        db.commit()
    monkeypatch.setattr(crud, "PENDING_STORE", tmp_path / "pending.json")
    crud.PENDING_DELETIONS.clear()
    return path


def test_request_does_not_change_record_and_confirmation_deletes_exactly_once(delete_db):
    before = crud.find_records("classrooms", {"id": 21}, db_path=delete_db)["records"][0]
    request = crud.request_delete("classrooms", {"id": 21}, "session-a", db_path=delete_db)
    assert request["pending"] and request["record"] == before
    assert crud.find_records("classrooms", {"id": 21}, db_path=delete_db)["count"] == 1
    confirmed = crud.confirm_delete(request["confirmation_id"], "session-a", db_path=delete_db)
    assert confirmed["changed"]
    assert crud.find_records("classrooms", {"id": 21}, db_path=delete_db)["count"] == 0
    reused = crud.confirm_delete(request["confirmation_id"], "session-a", db_path=delete_db)
    assert not reused["success"]


def test_cancel_and_unrelated_or_wrong_session_do_not_delete(delete_db):
    request = crud.request_delete("classrooms", {"id": 22}, "session-a", db_path=delete_db)
    wrong = crud.confirm_delete(request["confirmation_id"], "session-b", db_path=delete_db)
    assert not wrong["success"]
    assert crud.find_records("classrooms", {"id": 22}, db_path=delete_db)["count"] == 1
    cancelled = crud.cancel_delete(request["confirmation_id"], "session-a")
    assert cancelled["cancelled"]
    assert crud.find_records("classrooms", {"id": 22}, db_path=delete_db)["count"] == 1


def test_expiry_stale_record_and_ambiguity_are_rejected(delete_db):
    expired = crud.request_delete("classrooms", {"id": 23}, "session-a", db_path=delete_db)
    crud.PENDING_DELETIONS[expired["confirmation_id"]]["expires_at"] = time.time() - 1
    crud._save_pending()
    assert not crud.confirm_delete(expired["confirmation_id"], "session-a", db_path=delete_db)["success"]

    stale = crud.request_delete("classrooms", {"id": 24}, "session-a", db_path=delete_db)
    with connect(delete_db) as db:
        db.execute("UPDATE classrooms SET capacity = capacity + 1 WHERE id = 24")
        db.commit()
    result = crud.confirm_delete(stale["confirmation_id"], "session-a", db_path=delete_db)
    assert result["stale"] and crud.find_records("classrooms", {"id": 24}, db_path=delete_db)["count"] == 1

    with connect(delete_db) as db:
        db.execute("UPDATE classrooms SET building = 'Same' WHERE id IN (21, 22)")
        db.commit()
    ambiguous = crud.request_delete("classrooms", {"building": "Same"}, "session-a", db_path=delete_db)
    assert ambiguous["ambiguous"]


def test_cascade_requires_separate_confirmation_and_legacy_tools_cannot_bypass(delete_db):
    request = crud.request_delete("students", {"id": 1}, "session-a", db_path=delete_db)
    first = crud.confirm_delete(request["confirmation_id"], "session-a", db_path=delete_db)
    assert first["requires_cascade_confirmation"]
    assert crud.find_records("students", {"id": 1}, db_path=delete_db)["count"] == 1
    final = crud.confirm_delete(request["confirmation_id"], "session-a", cascade_confirmed=True, db_path=delete_db)
    assert final["changed"]
    assert not server.delete_record("students", {"id": 2}, True, True)["success"]
