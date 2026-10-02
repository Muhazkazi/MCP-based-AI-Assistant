"""Validated database operations used by the MCP tool definitions."""

from __future__ import annotations

import sqlite3
from typing import Any

from .database import DEFAULT_DB_PATH, connect, rows_to_dicts, row_to_dict
from .query_planner import execute_relational_query, sql_for_operation
from .crud import delete_record, find_records, insert_record, table_schema, update_record


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} cannot be empty.")
    return value.strip()


def _student_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("student_id must be a positive integer.")
    return value


def _year(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 8:
        raise ValueError("year must be an integer from 1 to 8.")
    return value


def _academic_year(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 2000 <= value <= 2100:
        raise ValueError("academic_year must be a calendar year from 2000 to 2100.")
    return value


def _marks(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
        raise ValueError("marks must be between 0 and 100.")
    return float(value)


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError("limit must be an integer from 1 to 100.")
    return value


def list_students(db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    with connect(db_path) as db:
        rows = db.execute("SELECT * FROM students ORDER BY id").fetchall()
    return {"students": rows_to_dicts(rows), "count": len(rows)}


def get_student(student_id: int, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    student_id = _student_id(student_id)
    with connect(db_path) as db:
        row = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    student = row_to_dict(row)
    return {"found": student is not None, "student": student}


def search_students(name: str | None = None, branch: str | None = None,
                    min_marks: float | None = None, max_marks: float | None = None,
                    db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses: list[str] = []
    values: list[Any] = []
    if name is not None:
        clauses.append("name LIKE ?")
        values.append(f"%{_text(name, 'name')}%")
    if branch is not None:
        clauses.append("branch LIKE ?")
        values.append(f"%{_text(branch, 'branch')}%")
    if min_marks is not None:
        clauses.append("marks >= ?")
        values.append(_marks(min_marks))
    if max_marks is not None:
        clauses.append("marks <= ?")
        values.append(_marks(max_marks))
    if min_marks is not None and max_marks is not None and min_marks > max_marks:
        raise ValueError("min_marks cannot be greater than max_marks.")
    query = "SELECT * FROM students"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"students": rows_to_dicts(rows), "count": len(rows)}


def get_average_marks(db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    with connect(db_path) as db:
        row = db.execute("SELECT AVG(marks) AS average_marks, COUNT(*) AS count FROM students").fetchone()
    return {"average_marks": row["average_marks"], "count": row["count"]}


def get_student_count(db_path=DEFAULT_DB_PATH) -> dict[str, int]:
    with connect(db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    return {"count": count}


def get_top_students(limit: int = 5, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    limit = _limit(limit)
    with connect(db_path) as db:
        rows = db.execute("SELECT * FROM students ORDER BY marks DESC, id LIMIT ?", (limit,)).fetchall()
    return {"students": rows_to_dicts(rows), "count": len(rows), "limit": limit}


def get_students_by_branch(branch: str, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    branch = _text(branch, "branch")
    with connect(db_path) as db:
        rows = db.execute("SELECT * FROM students WHERE branch LIKE ? ORDER BY id", (f"%{branch}%",)).fetchall()
    return {"students": rows_to_dicts(rows), "count": len(rows), "branch": branch}


def get_students_by_year(year: int, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    year = _year(year)
    with connect(db_path) as db:
        rows = db.execute("SELECT * FROM students WHERE year = ? ORDER BY id", (year,)).fetchall()
    return {"students": rows_to_dicts(rows), "count": len(rows), "year": year}


def add_student(name: str, branch: str, year: int, marks: float,
                email: str | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    name, branch, year, marks = _text(name, "name"), _text(branch, "branch"), _year(year), _marks(marks)
    if email is not None:
        email = _text(email, "email")
    with connect(db_path) as db:
        department = db.execute("SELECT id FROM departments WHERE name = ?", (branch,)).fetchone()
        cursor = db.execute(
            "INSERT INTO students (name, branch, year, marks, email, full_name, department_id, academic_year, cgpa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, branch, year, marks, email, name, department[0] if department else None, year, round(marks / 10, 2)),
        )
        student_id = cursor.lastrowid
        db.commit()
        row = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return {"success": True, "student": row_to_dict(row)}


def update_student(student_id: int, name: str | None = None, branch: str | None = None,
                   year: int | None = None, marks: float | None = None,
                   email: str | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    student_id = _student_id(student_id)
    fields: dict[str, Any] = {}
    if name is not None:
        fields["name"] = _text(name, "name")
    if branch is not None:
        fields["branch"] = _text(branch, "branch")
    if year is not None:
        fields["year"] = _year(year)
    if marks is not None:
        fields["marks"] = _marks(marks)
    if email is not None:
        fields["email"] = _text(email, "email")
    if not fields:
        raise ValueError("At least one field must be provided for update.")
    with connect(db_path) as db:
        before = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if before is None:
            return {"success": False, "found": False, "changed": False, "student": None}
        assignments = ", ".join(f"{field} = ?" for field in fields)
        db.execute(f"UPDATE students SET {assignments} WHERE id = ?", [*fields.values(), student_id])
        db.commit()
        after = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return {"success": True, "found": True, "changed": dict(before) != dict(after), "student": row_to_dict(after)}


def delete_student(student_id: int, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    student_id = _student_id(student_id)
    with connect(db_path) as db:
        before = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if before is None:
            return {"success": False, "found": False, "changed": False, "student": None}
        db.execute("DELETE FROM students WHERE id = ?", (student_id,))
        db.commit()
    return {"success": True, "found": True, "changed": True, "student": row_to_dict(before)}


def list_teachers(search: str | None = None, department: str | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if search:
        clauses.append("t.full_name LIKE ?")
        values.append(f"%{_text(search, 'search')}%")
    if department:
        clauses.append("d.name LIKE ?")
        values.append(f"%{_text(department, 'department')}%")
    query = "SELECT t.*, d.name AS department_name FROM teachers t JOIN departments d ON d.id = t.department_id"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY t.id"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"teachers": rows_to_dicts(rows), "count": len(rows)}


def get_teacher(teacher_id: int, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    teacher_id = _student_id(teacher_id)
    with connect(db_path) as db:
        row = db.execute("SELECT t.*, d.name AS department_name FROM teachers t JOIN departments d ON d.id = t.department_id WHERE t.id = ?", (teacher_id,)).fetchone()
    return {"found": row is not None, "teacher": row_to_dict(row)}


def list_departments(db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    with connect(db_path) as db:
        rows = db.execute("SELECT d.*, t.full_name AS head_teacher_name FROM departments d LEFT JOIN teachers t ON t.id = d.head_teacher_id ORDER BY d.id").fetchall()
    return {"departments": rows_to_dicts(rows), "count": len(rows)}


def list_courses(department: str | None = None, semester: int | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if department:
        clauses.append("d.name LIKE ?")
        values.append(f"%{_text(department, 'department')}%")
    if semester is not None:
        clauses.append("c.semester = ?")
        values.append(_year(semester))
    query = "SELECT c.*, d.name AS department_name FROM courses c JOIN departments d ON d.id = c.department_id"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY c.id"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"courses": rows_to_dicts(rows), "count": len(rows)}


def list_enrollments(student_id: int | None = None, course_id: int | None = None,
                     academic_year: int | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if student_id is not None:
        clauses.append("e.student_id = ?")
        values.append(_student_id(student_id))
    if course_id is not None:
        clauses.append("e.course_id = ?")
        values.append(_student_id(course_id))
    if academic_year is not None:
        clauses.append("e.academic_year = ?")
        values.append(_academic_year(academic_year))
    query = "SELECT e.*, s.full_name, c.name AS course_name, c.code AS course_code FROM enrollments e JOIN students s ON s.id = e.student_id JOIN courses c ON c.id = e.course_id"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY e.id"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"enrollments": rows_to_dicts(rows), "count": len(rows)}


def list_results(student_id: int | None = None, course_id: int | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if student_id is not None:
        clauses.append("r.student_id = ?")
        values.append(_student_id(student_id))
    if course_id is not None:
        clauses.append("e.course_id = ?")
        values.append(_student_id(course_id))
    query = "SELECT r.*, s.full_name, e.course_id, e.name AS exam_name, e.exam_type FROM results r JOIN students s ON s.id = r.student_id JOIN exams e ON e.id = r.exam_id"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY r.id"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"results": rows_to_dicts(rows), "count": len(rows)}


def list_attendance(student_id: int | None = None, course_id: int | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if student_id is not None:
        clauses.append("a.student_id = ?")
        values.append(_student_id(student_id))
    if course_id is not None:
        clauses.append("a.course_id = ?")
        values.append(_student_id(course_id))
    query = "SELECT a.*, s.full_name, c.name AS course_name FROM attendance a JOIN students s ON s.id = a.student_id JOIN courses c ON c.id = a.course_id"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY a.attendance_date, a.id"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"attendance": rows_to_dicts(rows), "count": len(rows)}


def list_fees(student_id: int | None = None, payment_status: str | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if student_id is not None:
        clauses.append("f.student_id = ?")
        values.append(_student_id(student_id))
    if payment_status:
        payment_status = _text(payment_status, "payment_status").lower()
        if payment_status not in {"paid", "unpaid", "partial"}:
            raise ValueError("payment_status must be paid, unpaid, or partial.")
        clauses.append("f.payment_status = ?")
        values.append(payment_status)
    query = "SELECT f.*, s.full_name FROM fees f JOIN students s ON s.id = f.student_id"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY f.due_date"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"fees": rows_to_dicts(rows), "count": len(rows)}


def search_library_books(query_text: str | None = None, category: str | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if query_text:
        query_text = _text(query_text, "query_text")
        clauses.append("(title LIKE ? OR author LIKE ? OR isbn LIKE ?)")
        values.extend([f"%{query_text}%"] * 3)
    if category:
        clauses.append("category LIKE ?")
        values.append(f"%{_text(category, 'category')}%")
    query = "SELECT * FROM library_books"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY title"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"books": rows_to_dicts(rows), "count": len(rows)}


def list_library_transactions(student_id: int | None = None, status: str | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if student_id is not None:
        clauses.append("t.student_id = ?")
        values.append(_student_id(student_id))
    if status:
        clauses.append("t.transaction_status = ?")
        values.append(_text(status, "status").lower())
    query = "SELECT t.*, s.full_name, b.title FROM library_transactions t JOIN students s ON s.id = t.student_id JOIN library_books b ON b.id = t.book_id"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY t.id"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"transactions": rows_to_dicts(rows), "count": len(rows)}


def list_timetable(teacher_id: int | None = None, course_id: int | None = None,
                   academic_year: int | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    clauses, values = [], []
    if teacher_id is not None:
        clauses.append("tt.teacher_id = ?")
        values.append(_student_id(teacher_id))
    if course_id is not None:
        clauses.append("tt.course_id = ?")
        values.append(_student_id(course_id))
    if academic_year is not None:
        clauses.append("tt.academic_year = ?")
        values.append(_academic_year(academic_year))
    query = "SELECT tt.*, c.name AS course_name, t.full_name AS teacher_name, cl.building, cl.room_number FROM timetable tt JOIN courses c ON c.id = tt.course_id JOIN teachers t ON t.id = tt.teacher_id JOIN classrooms cl ON cl.id = tt.classroom_id"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY tt.day_of_week, tt.start_time"
    with connect(db_path) as db:
        rows = db.execute(query, values).fetchall()
    return {"timetable": rows_to_dicts(rows), "count": len(rows)}


def get_database_summary(db_path=DEFAULT_DB_PATH) -> dict[str, int]:
    tables = ("students", "teachers", "departments", "courses", "enrollments")
    with connect(db_path) as db:
        return {f"{table}_count": db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def query_college(operation: str, filters: dict[str, Any] | None = None,
                  limit: int = 100, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    """Execute one named, read-only multi-table query plan."""
    return execute_relational_query(operation, filters, limit, db_path)


def get_sql_query(operation: str, filters: dict[str, Any] | None = None,
                  limit: int = 100) -> dict[str, Any]:
    """Return an approved parameterized SQL statement without executing it."""
    return sql_for_operation(operation, filters, limit)


CHART_DATASETS = {
    "students_by_branch": "students_by_branch",
    "students_by_year": "students_by_year",
    "students_by_gender": "students_by_gender",
    "students_average_marks_by_branch": "students_average_marks_by_branch",
    "student_marks_distribution": "student_marks_distribution",
    "top_students_marks": "top_students_marks",
    "teachers_by_department": "teachers_by_department",
    "teacher_salary_distribution": "teacher_salary_distribution",
    "courses_by_department": "courses_by_department",
    "course_enrollment": "course_enrollment",
    "enrollments_by_year": "enrollments_by_year",
    "fees_by_status": "fees_by_status",
    "books_by_category": "books_by_category",
    "attendance_by_status": "attendance_by_status",
    "student_marks_by_year": "student_marks_by_year",
}


def get_chart_data(dataset: str, chart_type: str = "bar", title: str | None = None,
                  filters: dict[str, Any] | None = None, limit: int = 100,
                  db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    """Return controlled aggregate/raw rows for chart rendering; filters never contain SQL."""
    dataset = _text(dataset, "dataset")
    chart_type = _text(chart_type, "chart_type").lower()
    if dataset not in CHART_DATASETS:
        raise ValueError(f"Unsupported chart dataset. Choose from: {', '.join(CHART_DATASETS)}")
    if chart_type not in {"pie", "donut", "bar", "horizontal_bar", "line", "histogram", "scatter"}:
        raise ValueError("chart_type must be pie, donut, bar, horizontal_bar, line, histogram, or scatter.")
    limit = _limit(limit)
    filters = filters or {}
    allowed_filters = {"department", "academic_year", "gender", "semester", "status", "category"}
    if set(filters) - allowed_filters:
        raise ValueError(f"Unsupported chart filters: {', '.join(sorted(set(filters) - allowed_filters))}")

    templates = {
        "students_by_branch": ("SELECT COALESCE(d.name, s.branch, 'Unknown') AS label, COUNT(*) AS value FROM students s LEFT JOIN departments d ON d.id = s.department_id", "label"),
        "students_by_year": ("SELECT COALESCE(s.academic_year, s.year) AS label, COUNT(*) AS value FROM students s LEFT JOIN departments d ON d.id = s.department_id", "label"),
        "students_by_gender": ("SELECT COALESCE(s.gender, 'Unknown') AS label, COUNT(*) AS value FROM students s LEFT JOIN departments d ON d.id = s.department_id", "label"),
        "students_average_marks_by_branch": ("SELECT COALESCE(d.name, s.branch, 'Unknown') AS label, ROUND(AVG(s.marks), 2) AS value FROM students s LEFT JOIN departments d ON d.id = s.department_id", "label"),
        "student_marks_distribution": ("SELECT s.marks AS value FROM students s LEFT JOIN departments d ON d.id = s.department_id", "value"),
        "top_students_marks": ("SELECT COALESCE(s.full_name, s.name) AS label, s.marks AS value FROM students s LEFT JOIN departments d ON d.id = s.department_id", "label"),
        "teachers_by_department": ("SELECT d.name AS label, COUNT(*) AS value FROM teachers t JOIN departments d ON d.id = t.department_id", "label"),
        "teacher_salary_distribution": ("SELECT t.full_name AS label, t.salary AS value FROM teachers t JOIN departments d ON d.id = t.department_id", "label"),
        "courses_by_department": ("SELECT d.name AS label, COUNT(*) AS value FROM courses c JOIN departments d ON d.id = c.department_id", "label"),
        "course_enrollment": ("SELECT c.name AS label, COUNT(e.id) AS value FROM courses c JOIN departments d ON d.id = c.department_id LEFT JOIN enrollments e ON e.course_id = c.id", "label"),
        "enrollments_by_year": ("SELECT e.academic_year AS label, COUNT(*) AS value FROM enrollments e JOIN students s ON s.id = e.student_id LEFT JOIN departments d ON d.id = s.department_id", "label"),
        "fees_by_status": ("SELECT f.payment_status AS label, COUNT(*) AS value FROM fees f JOIN students s ON s.id = f.student_id LEFT JOIN departments d ON d.id = s.department_id", "label"),
        "books_by_category": ("SELECT COALESCE(b.category, 'Unknown') AS label, COUNT(*) AS value FROM library_books b", "label"),
        "attendance_by_status": ("SELECT a.status AS label, COUNT(*) AS value FROM attendance a JOIN students s ON s.id = a.student_id JOIN courses c ON c.id = a.course_id LEFT JOIN departments d ON d.id = s.department_id", "label"),
        "student_marks_by_year": ("SELECT COALESCE(s.academic_year, s.year) AS x, s.marks AS y, COALESCE(s.full_name, s.name) AS label FROM students s LEFT JOIN departments d ON d.id = s.department_id", "x"),
    }
    query, _ = templates[dataset]
    clauses, values = [], []
    if "department" in filters:
        if dataset == "books_by_category":
            raise ValueError("department is not a valid filter for books_by_category.")
        clauses.append("d.name LIKE ?")
        values.append(f"%{_text(str(filters['department']), 'department')}%")
    if "academic_year" in filters:
        student_year = dataset in {"students_by_branch", "students_by_year", "students_by_gender", "students_average_marks_by_branch", "student_marks_distribution", "top_students_marks", "student_marks_by_year"}
        if student_year:
            clauses.append("COALESCE(s.academic_year, s.year) = ?")
            values.append(_year(int(filters["academic_year"])))
        elif dataset == "enrollments_by_year":
            clauses.append("e.academic_year = ?")
            values.append(_academic_year(int(filters["academic_year"])))
        else:
            raise ValueError(f"academic_year is not a valid filter for {dataset}.")
    if "gender" in filters:
        if dataset not in {"students_by_branch", "students_by_year", "students_by_gender", "students_average_marks_by_branch", "student_marks_distribution", "top_students_marks", "student_marks_by_year"}:
            raise ValueError(f"gender is not a valid filter for {dataset}.")
        clauses.append("s.gender = ?")
        values.append(_text(str(filters["gender"]), "gender"))
    if "semester" in filters:
        if dataset != "course_enrollment":
            raise ValueError(f"semester is not a valid filter for {dataset}.")
        clauses.append("COALESCE(e.semester, c.semester) = ?")
        values.append(_year(int(filters["semester"])))
    if "status" in filters:
        if dataset not in {"fees_by_status", "attendance_by_status"}:
            raise ValueError(f"status is not a valid filter for {dataset}.")
        clauses.append("f.payment_status = ?" if dataset == "fees_by_status" else "a.status = ?")
        values.append(_text(str(filters["status"]), "status"))
    if "category" in filters:
        if dataset != "books_by_category":
            raise ValueError(f"category is not a valid filter for {dataset}.")
        clauses.append("b.category LIKE ?")
        values.append(f"%{_text(str(filters['category']), 'category')}%")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    if dataset not in {"student_marks_distribution", "top_students_marks", "student_marks_by_year", "teacher_salary_distribution"}:
        query += " GROUP BY label"
    query += " ORDER BY value DESC" if dataset != "student_marks_by_year" else " ORDER BY x, y"
    query += " LIMIT ?"
    values.append(limit)
    with connect(db_path) as db:
        rows = rows_to_dicts(db.execute(query, values).fetchall())
    return {"dataset": dataset, "chart_type": chart_type, "title": title or dataset.replace("_", " ").title(), "rows": rows, "count": len(rows)}

