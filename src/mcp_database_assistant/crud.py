"""Schema-aware CRUD primitives used only behind MCP.

Identifiers are selected from SQLite schema metadata; values are always bound
parameters. The LLM never supplies SQL text.
"""

from __future__ import annotations

import sqlite3
import hashlib
import json
import time
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from .database import DEFAULT_DB_PATH, connect, row_to_dict, rows_to_dicts

SUPPORTED_TABLES = (
    "students", "teachers", "departments", "courses", "enrollments", "exams",
    "results", "classrooms", "timetable", "attendance", "fees",
    "library_books", "library_transactions",
)
PROTECTED_COLUMNS = {"id", "provenance_id", "data_origin"}
PENDING_DELETIONS: dict[str, dict[str, Any]] = {}
DELETE_TTL_SECONDS = 300
PENDING_STORE = DEFAULT_DB_PATH.with_name(".pending_deletions.json")


def _table(table: str) -> str:
    if not isinstance(table, str) or table not in SUPPORTED_TABLES:
        raise ValueError(f"Unsupported table. Choose from: {', '.join(SUPPORTED_TABLES)}")
    return table


def _columns(db: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {row[1]: row for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _validate_fields(schema: dict[str, sqlite3.Row], values: dict[str, Any], *, allow_protected: bool = False) -> None:
    if not isinstance(values, dict) or not values:
        raise ValueError("values must be a non-empty object")
    unknown = set(values) - set(schema)
    if unknown:
        raise ValueError(f"Unsupported column(s): {', '.join(sorted(unknown))}")
    protected = set(values) & PROTECTED_COLUMNS
    if protected and not allow_protected:
        raise ValueError(f"Protected column(s) cannot be modified: {', '.join(sorted(protected))}")
    for name, value in values.items():
        declared = (schema[name][2] or "").upper()
        if value is None:
            continue
        if "INT" in declared and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"{name} must be an integer")
        if any(token in declared for token in ("REAL", "FLOA", "DOUB", "NUM")) and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError(f"{name} must be numeric")
        if "TEXT" in declared and not isinstance(value, str):
            raise ValueError(f"{name} must be text")


def _where(schema: dict[str, sqlite3.Row], where: dict[str, Any] | None) -> tuple[str, list[Any]]:
    if not isinstance(where, dict) or not where:
        raise ValueError("where must identify the record with at least one field")
    _validate_fields(schema, where, allow_protected=True)
    clauses, params = [], []
    for name, value in where.items():
        clauses.append(f'"{name}" IS ?' if value is None else f'"{name}" = ?')
        params.append(value)
    return " AND ".join(clauses), params


def find_records(table: str, where: dict[str, Any] | None = None, limit: int = 50,
                 db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    table = _table(table)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("limit must be an integer from 1 to 200")
    with connect(db_path) as db:
        schema = _columns(db, table)
        params: list[Any] = []
        query = f'SELECT * FROM "{table}"'
        if where:
            clause, params = _where(schema, where)
            query += f" WHERE {clause}"
        query += " ORDER BY id LIMIT ?" if "id" in schema else " LIMIT ?"
        params.append(limit)
        rows = rows_to_dicts(db.execute(query, params).fetchall())
    return {"table": table, "records": rows, "count": len(rows), "ambiguous": len(rows) > 1}


def insert_record(table: str, values: dict[str, Any], db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    table = _table(table)
    with connect(db_path) as db:
        schema = _columns(db, table)
        _validate_fields(schema, values)
        required = [name for name, info in schema.items() if info[3] and not info[4] and info[5] is None]
        missing = [name for name in required if name not in values]
        if missing:
            raise ValueError(f"Missing required column(s): {', '.join(missing)}")
        names = list(values)
        placeholders = ", ".join("?" for _ in names)
        try:
            cursor = db.execute(f'INSERT INTO "{table}" ({", ".join(names)}) VALUES ({placeholders})', [values[name] for name in names])
            record_id = cursor.lastrowid
            row = db.execute(f'SELECT * FROM "{table}" WHERE id = ?', (record_id,)).fetchone() if "id" in schema else None
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ValueError(f"Insert rejected by database constraints: {exc}") from exc
    return {"success": True, "table": table, "record_id": record_id, "record": row_to_dict(row)}


def update_record(table: str, where: dict[str, Any], values: dict[str, Any], db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    table = _table(table)
    with connect(db_path) as db:
        schema = _columns(db, table)
        _validate_fields(schema, values)
        clause, where_params = _where(schema, where)
        matches = db.execute(f'SELECT * FROM "{table}" WHERE {clause}', where_params).fetchall()
        if not matches:
            return {"success": False, "found": False, "changed": False, "table": table, "message": "No matching record."}
        if len(matches) != 1:
            return {"success": False, "found": True, "ambiguous": True, "changed": False, "table": table, "count": len(matches), "message": "The identifier matches multiple records; provide a primary key or more conditions."}
        assignments = ", ".join(f'"{name}" = ?' for name in values)
        try:
            cursor = db.execute(f'UPDATE "{table}" SET {assignments} WHERE {clause}', [*values.values(), *where_params])
            record_id = matches[0]["id"] if "id" in schema else None
            row = db.execute(f'SELECT * FROM "{table}" WHERE id = ?', (record_id,)).fetchone() if record_id is not None else None
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ValueError(f"Update rejected by database constraints: {exc}") from exc
    return {"success": True, "found": True, "changed": cursor.rowcount > 0, "table": table, "record_id": record_id, "changed_fields": values, "record": row_to_dict(row)}


def _dependent_counts(db: sqlite3.Connection, table: str, record_id: Any) -> list[dict[str, Any]]:
    dependencies = []
    for child in SUPPORTED_TABLES:
        for fk in db.execute(f"PRAGMA foreign_key_list({child})").fetchall():
            if fk[2] == table and fk[4] == "id":
                count = db.execute(f'SELECT COUNT(*) FROM "{child}" WHERE "{fk[3]}" = ?', (record_id,)).fetchone()[0]
                if count:
                    dependencies.append({"table": child, "count": count, "on_delete": fk[6]})
    return dependencies


def delete_record(table: str, where: dict[str, Any], confirmed: bool = False,
                  cascade_confirmed: bool = False, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    table = _table(table)
    with connect(db_path) as db:
        schema = _columns(db, table)
        clause, params = _where(schema, where)
        matches = db.execute(f'SELECT * FROM "{table}" WHERE {clause}', params).fetchall()
        if not matches:
            return {"success": False, "found": False, "changed": False, "table": table, "message": "No matching record."}
        if len(matches) != 1:
            return {"success": False, "found": True, "ambiguous": True, "changed": False, "count": len(matches), "message": "Deletion requires one exact record."}
        if not confirmed:
            return {"success": False, "found": True, "requires_confirmation": True, "changed": False, "record": row_to_dict(matches[0])}
        record_id = matches[0]["id"] if "id" in schema else None
        dependencies = _dependent_counts(db, table, record_id) if record_id is not None else []
        cascades = [item for item in dependencies if item["on_delete"].upper() == "CASCADE"]
        if cascades and not cascade_confirmed:
            return {"success": False, "found": True, "requires_cascade_confirmation": True, "changed": False, "record": row_to_dict(matches[0]), "dependencies": dependencies}
        try:
            db.execute(f'DELETE FROM "{table}" WHERE {clause}', params)
            remaining = db.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {clause}', params).fetchone()[0]
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise ValueError(f"Delete rejected because related records remain: {exc}") from exc
    return {"success": remaining == 0, "found": True, "changed": remaining == 0, "table": table, "record_id": record_id, "deleted_record": row_to_dict(matches[0]), "dependencies": dependencies}


def _fingerprint(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expire_pending() -> None:
    global PENDING_DELETIONS
    if PENDING_STORE.exists():
        try:
            PENDING_DELETIONS = json.loads(PENDING_STORE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            PENDING_DELETIONS = {}
    now = time.time()
    changed = False
    for token, request in list(PENDING_DELETIONS.items()):
        if request["expires_at"] <= now:
            PENDING_DELETIONS.pop(token, None)
            changed = True
    if changed:
        _save_pending()


def _save_pending() -> None:
    try:
        PENDING_STORE.parent.mkdir(parents=True, exist_ok=True)
        PENDING_STORE.write_text(json.dumps(PENDING_DELETIONS), encoding="utf-8")
    except OSError:
        # The in-process map remains authoritative when a read-only deployment
        # cannot create the optional sidecar.
        pass


def request_delete(table: str, where: dict[str, Any], session_id: str,
                   db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    """Fetch exactly one record and create a five-minute, session-bound deletion request."""
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is required")
    _expire_pending()
    found = find_records(table, where, limit=2, db_path=db_path)
    if found["count"] == 0:
        return {"success": False, "found": False, "message": "No matching record."}
    if found["count"] != 1:
        return {"success": False, "found": True, "ambiguous": True, "count": found["count"], "message": "Deletion requires one exact record."}
    record = found["records"][0]
    with connect(db_path) as db:
        dependencies = _dependent_counts(db, table, record.get("id"))
    token = uuid4().hex
    expires_at = time.time() + DELETE_TTL_SECONDS
    PENDING_DELETIONS[token] = {
        "session_id": session_id,
        "table": table,
        "where": dict(where),
        "record": record,
        "fingerprint": _fingerprint(record),
        "dependencies": dependencies,
        "expires_at": expires_at,
    }
    _save_pending()
    return {
        "success": True,
        "pending": True,
        "confirmation_id": token,
        "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        "table": table,
        "record": record,
        "dependencies": dependencies,
        "requires_cascade_confirmation": bool(dependencies),
        "message": "Record fetched. No deletion has occurred. Explicit confirmation is required.",
    }


def confirm_delete(confirmation_id: str, session_id: str, cascade_confirmed: bool = False,
                   db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    """Confirm one pending request, revalidate its record, then delete exactly once."""
    _expire_pending()
    request = PENDING_DELETIONS.get(confirmation_id)
    if not request:
        return {"success": False, "changed": False, "message": "Confirmation is expired, cancelled, completed, or unknown."}
    if request["session_id"] != session_id:
        return {"success": False, "changed": False, "message": "This confirmation belongs to another session."}
    if request["dependencies"] and not cascade_confirmed:
        return {"success": False, "changed": False, "requires_cascade_confirmation": True, "dependencies": request["dependencies"], "message": "Related records exist. A separate cascade confirmation is required."}
    table = request["table"]
    where = request["where"]
    with connect(db_path) as db:
        schema = _columns(db, table)
        clause, params = _where(schema, where)
        current = db.execute(f'SELECT * FROM "{table}" WHERE {clause}', params).fetchall()
        if len(current) != 1 or _fingerprint(dict(current[0])) != request["fingerprint"]:
            PENDING_DELETIONS.pop(confirmation_id, None)
            _save_pending()
            return {"success": False, "changed": False, "stale": True, "message": "The record changed or no longer exists; confirmation was invalidated."}
        try:
            db.execute(f'DELETE FROM "{table}" WHERE {clause}', params)
            remaining = db.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {clause}', params).fetchone()[0]
            if remaining:
                db.rollback()
                return {"success": False, "changed": False, "message": "The record could not be verified as deleted."}
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            PENDING_DELETIONS.pop(confirmation_id, None)
            _save_pending()
            return {"success": False, "changed": False, "message": f"Delete rejected because related records remain: {exc}"}
    PENDING_DELETIONS.pop(confirmation_id, None)
    _save_pending()
    return {"success": True, "changed": True, "table": table, "record": request["record"], "message": "Deletion verified."}


def cancel_delete(confirmation_id: str, session_id: str) -> dict[str, Any]:
    _expire_pending()
    request = PENDING_DELETIONS.get(confirmation_id)
    if not request:
        return {"success": False, "cancelled": False, "message": "Confirmation is expired, cancelled, completed, or unknown."}
    if request["session_id"] != session_id:
        return {"success": False, "cancelled": False, "message": "This confirmation belongs to another session."}
    PENDING_DELETIONS.pop(confirmation_id, None)
    _save_pending()
    return {"success": True, "cancelled": True, "message": "Deletion cancelled. The record was retained."}


def table_schema(table: str | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    tables = [_table(table)] if table else list(SUPPORTED_TABLES)
    with connect(db_path) as db:
        result = {}
        for name in tables:
            result[name] = [dict(row) for row in db.execute(f"PRAGMA table_info({name})").fetchall()]
    return {"tables": result}
