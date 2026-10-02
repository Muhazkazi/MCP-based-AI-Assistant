"""Schema-aware CRUD primitives used only behind MCP.

Identifiers are selected from SQLite schema metadata; values are always bound
parameters. The LLM never supplies SQL text.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .database import DEFAULT_DB_PATH, connect, row_to_dict, rows_to_dicts

SUPPORTED_TABLES = (
    "students", "teachers", "departments", "courses", "enrollments", "exams",
    "results", "classrooms", "timetable", "attendance", "fees",
    "library_books", "library_transactions",
)
PROTECTED_COLUMNS = {"id", "provenance_id", "data_origin"}


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


def table_schema(table: str | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    tables = [_table(table)] if table else list(SUPPORTED_TABLES)
    with connect(db_path) as db:
        result = {}
        for name in tables:
            result[name] = [dict(row) for row in db.execute(f"PRAGMA table_info({name})").fetchall()]
    return {"tables": result}
