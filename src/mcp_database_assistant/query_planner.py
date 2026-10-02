"""Small, explicit query planner for safe relational MCP reads.

The planner exposes named operations rather than allowing model-generated SQL to
run. Every value is bound as a SQLite parameter and every statement is read-only.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from .database import DEFAULT_DB_PATH, connect, rows_to_dicts

MAX_LIMIT = 200


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer from 1 to {MAX_LIMIT}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


PLANS: dict[str, tuple[str, tuple[str, ...]]] = {
    "students_by_name_courses": (
        """SELECT DISTINCT s.id AS student_id, COALESCE(s.full_name, s.name) AS student_name,
                  d.name AS department_name, c.id AS course_id, c.code AS course_code,
                  c.name AS course_name, e.academic_year, e.semester
           FROM students AS s
           LEFT JOIN departments AS d ON d.id = s.department_id
           JOIN enrollments AS e ON e.student_id = s.id
           JOIN courses AS c ON c.id = e.course_id
           WHERE s.name LIKE ? COLLATE NOCASE
              OR COALESCE(s.full_name, s.name) LIKE ? COLLATE NOCASE
           ORDER BY student_name, e.academic_year, e.semester, c.name
           LIMIT ?""",
        ("name",),
    ),
    "students_by_course": (
        """SELECT DISTINCT s.id AS student_id, COALESCE(s.full_name, s.name) AS student_name,
                  d.name AS department_name, c.code AS course_code, c.name AS course_name,
                  e.academic_year, e.semester
           FROM courses AS c
           JOIN enrollments AS e ON e.course_id = c.id
           JOIN students AS s ON s.id = e.student_id
           LEFT JOIN departments AS d ON d.id = s.department_id
           WHERE c.name LIKE ? COLLATE NOCASE OR c.code LIKE ? COLLATE NOCASE
           ORDER BY student_name, e.academic_year, e.semester
           LIMIT ?""",
        ("course",),
    ),
    "marks_by_student_name": (
        """SELECT s.id AS student_id, COALESCE(s.full_name, s.name) AS student_name,
                  c.code AS course_code, c.name AS course_name, e.name AS exam_name,
                  r.marks_obtained, e.maximum_marks, r.grade
           FROM students AS s
           JOIN results AS r ON r.student_id = s.id
           JOIN exams AS e ON e.id = r.exam_id
           JOIN courses AS c ON c.id = e.course_id
           WHERE s.name LIKE ? COLLATE NOCASE OR COALESCE(s.full_name, s.name) LIKE ? COLLATE NOCASE
           ORDER BY student_name, e.exam_date, c.name
           LIMIT ?""",
        ("name",),
    ),
    "course_marks_above": (
        """SELECT s.id AS student_id, COALESCE(s.full_name, s.name) AS student_name,
                  d.name AS department_name, c.name AS course_name, r.marks_obtained,
                  e.maximum_marks, r.grade
           FROM results AS r
           JOIN students AS s ON s.id = r.student_id
           JOIN exams AS e ON e.id = r.exam_id
           JOIN courses AS c ON c.id = e.course_id
           LEFT JOIN departments AS d ON d.id = s.department_id
           WHERE (c.name LIKE ? COLLATE NOCASE OR c.code LIKE ? COLLATE NOCASE)
             AND r.marks_obtained > ?
           ORDER BY r.marks_obtained DESC, student_name
           LIMIT ?""",
        ("course", "min_marks"),
    ),
    "teacher_courses": (
        """SELECT t.id AS teacher_id, t.full_name AS teacher_name,
                  d.name AS department_name, c.code AS course_code, c.name AS course_name,
                  tt.academic_year, tt.semester
           FROM teachers AS t
           JOIN timetable AS tt ON tt.teacher_id = t.id
           JOIN courses AS c ON c.id = tt.course_id
           LEFT JOIN departments AS d ON d.id = t.department_id
           WHERE t.full_name LIKE ? COLLATE NOCASE
           ORDER BY c.name, tt.academic_year, tt.semester
           LIMIT ?""",
        ("teacher",),
    ),
    "attendance_below": (
        """SELECT s.id AS student_id, COALESCE(s.full_name, s.name) AS student_name,
                  c.code AS course_code, c.name AS course_name,
                  ROUND(100.0 * SUM(CASE WHEN a.status IN ('present', 'late') THEN 1 ELSE 0 END) / COUNT(*), 2) AS attendance_percent,
                  COUNT(*) AS sessions
           FROM attendance AS a
           JOIN students AS s ON s.id = a.student_id
           JOIN courses AS c ON c.id = a.course_id
           WHERE c.name LIKE ? COLLATE NOCASE OR c.code LIKE ? COLLATE NOCASE
           GROUP BY s.id, c.id
           HAVING attendance_percent < ?
           ORDER BY attendance_percent, student_name
           LIMIT ?""",
        ("course", "threshold"),
    ),
    "unpaid_fees_by_department": (
        """SELECT s.id AS student_id, COALESCE(s.full_name, s.name) AS student_name,
                  d.name AS department_name, f.fee_type, f.amount, f.payment_status, f.due_date
           FROM fees AS f
           JOIN students AS s ON s.id = f.student_id
           LEFT JOIN departments AS d ON d.id = s.department_id
           WHERE f.payment_status IN ('unpaid', 'partial')
           ORDER BY department_name, student_name, f.due_date
           LIMIT ?""",
        (),
    ),
    "overdue_books": (
        """SELECT s.id AS student_id, COALESCE(s.full_name, s.name) AS student_name,
                  b.title, b.author, lt.issue_date, lt.due_date
           FROM library_transactions AS lt
           JOIN students AS s ON s.id = lt.student_id
           JOIN library_books AS b ON b.id = lt.book_id
           WHERE lt.transaction_status = 'overdue' OR (lt.return_date IS NULL AND lt.due_date < date('now'))
           ORDER BY lt.due_date
           LIMIT ?""",
        (),
    ),
}


def execute_relational_query(operation: str, filters: dict[str, Any] | None = None,
                             limit: int = 100, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    operation = _text(operation, "operation")
    if operation not in PLANS:
        raise ValueError(f"Unsupported relational operation. Choose from: {', '.join(sorted(PLANS))}")
    limit = _limit(limit)
    filters = filters or {}
    query, fields = PLANS[operation]
    allowed = set(fields)
    if set(filters) - allowed:
        raise ValueError(f"Unsupported filters: {', '.join(sorted(set(filters) - allowed))}")
    params: list[Any] = []
    if operation in {"students_by_name_courses", "marks_by_student_name"}:
        value = f"%{_text(filters['name'], 'name')}%"
        params.extend((value, value))
    elif operation == "students_by_course":
        value = f"%{_text(filters['course'], 'course')}%"
        params.extend((value, value))
    elif operation == "course_marks_above":
        value = f"%{_text(filters['course'], 'course')}%"
        threshold = float(filters["min_marks"])
        if not 0 <= threshold <= 100:
            raise ValueError("min_marks must be between 0 and 100")
        params.extend((value, value, threshold))
    elif operation == "teacher_courses":
        params.append(f"%{_text(filters['teacher'], 'teacher')}%")
    elif operation == "attendance_below":
        value = f"%{_text(filters['course'], 'course')}%"
        threshold = float(filters["threshold"])
        if not 0 <= threshold <= 100:
            raise ValueError("threshold must be between 0 and 100")
        params.extend((value, value, threshold))
    params.append(limit)
    with connect(db_path) as db:
        db.set_progress_handler(lambda: 1, 100000)
        try:
            rows = rows_to_dicts(db.execute(query, params).fetchall())
        except sqlite3.OperationalError as exc:
            raise ValueError(f"Relational query failed: {exc}") from exc
        finally:
            db.set_progress_handler(None, 0)
    return {"operation": operation, "rows": rows, "count": len(rows), "limit": limit}


def sql_for_operation(operation: str, filters: dict[str, Any] | None = None,
                      limit: int = 100) -> dict[str, Any]:
    if operation not in PLANS:
        raise ValueError(f"Unsupported relational operation: {operation}")
    _limit(limit)
    filters = filters or {}
    unknown = set(filters) - set(PLANS[operation][1])
    if unknown:
        raise ValueError(f"Unsupported filters: {', '.join(sorted(unknown))}")
    return {"operation": operation, "sql": PLANS[operation][0], "parameters": filters, "limit": limit}


def infer_operation(request: str) -> tuple[str, dict[str, Any]] | None:
    text = request.strip()
    name = re.search(r"(?:named|name(?:d)?|called)\s+([A-Za-z][A-Za-z ]*)", text, re.I)
    course = re.search(r"(?:course|in)\s+([A-Za-z][A-Za-z ]*)", text, re.I)
    if re.search(r"courses?.*(?:taken|enrolled)|what courses", text, re.I) and name:
        return "students_by_name_courses", {"name": name.group(1).strip()}
    if re.search(r"students?.*(?:enrolled|taken).*(?:course|in)", text, re.I) and course:
        return "students_by_course", {"course": course.group(1).strip()}
    if re.search(r"marks?.*(?:named|name|called)", text, re.I) and name:
        return "marks_by_student_name", {"name": name.group(1).strip()}
    return None
