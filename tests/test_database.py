import sqlite3

from mcp_database_assistant.database import connect


def test_connection_and_schema(tmp_path):
    path = tmp_path / "students.db"
    with connect(path) as db:
        columns = db.execute("PRAGMA table_info(students)").fetchall()
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    column_names = {column[1] for column in columns}
    assert {"id", "name", "branch", "year", "marks", "email"}.issubset(column_names)
    assert {"full_name", "department_id", "academic_year", "cgpa"}.issubset(column_names)
    assert {"departments", "teachers", "courses", "enrollments", "exams", "results", "attendance", "fees", "library_books", "library_transactions"}.issubset(tables)


def test_schema_does_not_seed_records(tmp_path):
    with connect(tmp_path / "students.db") as db:
        assert db.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0


def test_legacy_student_rows_survive_migration(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE students (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, branch TEXT NOT NULL, year INTEGER NOT NULL, marks REAL NOT NULL, email TEXT)")
        db.execute("INSERT INTO students (name, branch, year, marks, email) VALUES (?, ?, ?, ?, ?)", ("Legacy Student", "Computer Engineering", 3, 88, "legacy@example.com"))
        db.commit()
    with connect(path) as db:
        row = db.execute("SELECT name, full_name, academic_year, cgpa FROM students").fetchone()
    assert tuple(row) == ("Legacy Student", "Legacy Student", 3, 8.8)

