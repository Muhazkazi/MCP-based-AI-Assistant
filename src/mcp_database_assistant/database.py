"""SQLite schema, migration, and explicit demonstration-data initialization."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "students.db"

DEPARTMENTS = [
    ("Computer Engineering", "COMP", "Block A", 1998),
    ("Information Technology", "IT", "Block A", 2002),
    ("Electronics and Telecommunication", "ENTC", "Block B", 1995),
    ("Mechanical Engineering", "MECH", "Block C", 1990),
    ("Civil Engineering", "CIVIL", "Block D", 1988),
    ("Electrical Engineering", "ELEC", "Block B", 1992),
]


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _create_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            code TEXT NOT NULL UNIQUE,
            head_teacher_id INTEGER,
            office_location TEXT,
            established_year INTEGER CHECK (established_year BETWEEN 1800 AND 2100)
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            branch TEXT NOT NULL,
            year INTEGER NOT NULL CHECK (year BETWEEN 1 AND 8),
            marks REAL NOT NULL CHECK (marks BETWEEN 0 AND 100),
            email TEXT,
            full_name TEXT,
            phone_number TEXT,
            gender TEXT,
            date_of_birth TEXT,
            department_id INTEGER REFERENCES departments(id),
            academic_year INTEGER,
            admission_year INTEGER,
            current_semester INTEGER,
            enrollment_status TEXT DEFAULT 'active',
            address TEXT,
            cgpa REAL CHECK (cgpa BETWEEN 0 AND 10)
        );
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone_number TEXT,
            department_id INTEGER NOT NULL REFERENCES departments(id),
            designation TEXT NOT NULL,
            qualification TEXT,
            date_of_joining TEXT,
            salary REAL CHECK (salary >= 0),
            employment_status TEXT NOT NULL DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            department_id INTEGER NOT NULL REFERENCES departments(id),
            credits INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 8),
            semester INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 8),
            course_type TEXT NOT NULL CHECK (course_type IN ('core', 'elective')),
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            academic_year INTEGER NOT NULL,
            semester INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 8),
            enrollment_date TEXT NOT NULL,
            enrollment_status TEXT NOT NULL DEFAULT 'enrolled',
            UNIQUE(student_id, course_id, academic_year, semester)
        );
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            exam_type TEXT NOT NULL,
            exam_date TEXT,
            maximum_marks REAL NOT NULL CHECK (maximum_marks > 0),
            academic_year INTEGER NOT NULL,
            semester INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 8)
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
            marks_obtained REAL NOT NULL CHECK (marks_obtained >= 0),
            grade TEXT,
            result_status TEXT NOT NULL DEFAULT 'published',
            UNIQUE(student_id, exam_id)
        );
        CREATE TABLE IF NOT EXISTS classrooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            building TEXT NOT NULL,
            room_number TEXT NOT NULL,
            capacity INTEGER NOT NULL CHECK (capacity > 0),
            classroom_type TEXT NOT NULL,
            UNIQUE(building, room_number)
        );
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            teacher_id INTEGER NOT NULL REFERENCES teachers(id),
            classroom_id INTEGER NOT NULL REFERENCES classrooms(id),
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            academic_year INTEGER NOT NULL,
            semester INTEGER NOT NULL CHECK (semester BETWEEN 1 AND 8)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('present', 'absent', 'late')),
            UNIQUE(student_id, course_id, attendance_date)
        );
        CREATE TABLE IF NOT EXISTS fees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            fee_type TEXT NOT NULL,
            amount REAL NOT NULL CHECK (amount >= 0),
            due_date TEXT NOT NULL,
            payment_date TEXT,
            payment_status TEXT NOT NULL CHECK (payment_status IN ('paid', 'unpaid', 'partial'))
        );
        CREATE TABLE IF NOT EXISTS library_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT NOT NULL UNIQUE,
            publisher TEXT,
            publication_year INTEGER,
            available_copies INTEGER NOT NULL CHECK (available_copies >= 0),
            total_copies INTEGER NOT NULL CHECK (total_copies >= available_copies),
            category TEXT
        );
        CREATE TABLE IF NOT EXISTS library_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            book_id INTEGER NOT NULL REFERENCES library_books(id),
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            return_date TEXT,
            transaction_status TEXT NOT NULL CHECK (transaction_status IN ('issued', 'returned', 'overdue'))
        );
        """
    )


def _migrate_legacy_students(connection: sqlite3.Connection) -> None:
    """Add expanded student fields without deleting the original columns/rows."""
    columns = _table_columns(connection, "students")
    additions = {
        "full_name": "TEXT", "phone_number": "TEXT", "gender": "TEXT",
        "date_of_birth": "TEXT", "department_id": "INTEGER", "academic_year": "INTEGER",
        "admission_year": "INTEGER", "current_semester": "INTEGER",
        "enrollment_status": "TEXT DEFAULT 'active'", "address": "TEXT", "cgpa": "REAL",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE students ADD COLUMN {column} {definition}")
    connection.execute("UPDATE students SET full_name = COALESCE(full_name, name)")
    connection.execute("UPDATE students SET academic_year = COALESCE(academic_year, year)")
    connection.execute("UPDATE students SET cgpa = COALESCE(cgpa, ROUND(marks / 10.0, 2))")
    connection.execute("UPDATE students SET enrollment_status = COALESCE(enrollment_status, 'active')")


def migrate_schema(connection: sqlite3.Connection) -> None:
    """Create or upgrade all tables. This never seeds demonstration rows."""
    connection.execute("PRAGMA foreign_keys = ON")
    _create_tables(connection)
    _migrate_legacy_students(connection)
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_students_department ON students(department_id);
        CREATE INDEX IF NOT EXISTS idx_students_academic_year ON students(academic_year);
        CREATE INDEX IF NOT EXISTS idx_students_marks ON students(marks);
        CREATE INDEX IF NOT EXISTS idx_teachers_department ON teachers(department_id);
        CREATE INDEX IF NOT EXISTS idx_courses_department ON courses(department_id);
        CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
        CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id);
        CREATE INDEX IF NOT EXISTS idx_results_student ON results(student_id);
        CREATE INDEX IF NOT EXISTS idx_attendance_student_course ON attendance(student_id, course_id);
        CREATE INDEX IF NOT EXISTS idx_fees_student_status ON fees(student_id, payment_status);
        CREATE INDEX IF NOT EXISTS idx_library_title ON library_books(title);
        """
    )
    connection.commit()


def create_schema(connection: sqlite3.Connection) -> None:
    migrate_schema(connection)


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    migrate_schema(connection)
    return connection


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def seed_demo_data(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, int]:
    """Explicitly add deterministic sample college data without duplicating rows."""
    with connect(db_path) as db:
        db.executemany("INSERT OR IGNORE INTO departments (name, code, office_location, established_year) VALUES (?, ?, ?, ?)", DEPARTMENTS)
        department_rows = db.execute("SELECT id, name FROM departments ORDER BY id").fetchall()
        department_ids = {row["name"]: row["id"] for row in department_rows}
        branch_names = [row["name"] for row in department_rows]

        designations = ["Assistant Professor", "Associate Professor", "Professor"]
        teacher_rows = []
        for index in range(20):
            department = branch_names[index % len(branch_names)]
            teacher_rows.append((f"Faculty Member {index + 1}", f"faculty{index + 1}@college.example", f"900000{index:04d}", department_ids[department], designations[index % 3], "PhD" if index % 3 == 0 else "M.Tech", f"{2010 + index % 12}-07-01", 65000 + index * 2500, "active"))
        db.executemany("INSERT OR IGNORE INTO teachers (full_name, email, phone_number, department_id, designation, qualification, date_of_joining, salary, employment_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", teacher_rows)
        teacher_ids = [row[0] for row in db.execute("SELECT id FROM teachers ORDER BY id").fetchall()]
        for index, department in enumerate(branch_names):
            db.execute("UPDATE departments SET head_teacher_id = ? WHERE id = ? AND head_teacher_id IS NULL", (teacher_ids[index % len(teacher_ids)], department_ids[department]))

        for row in db.execute("SELECT id, name, branch FROM students").fetchall():
            department = row["branch"] if row["branch"] in department_ids else branch_names[row["id"] % len(branch_names)]
            db.execute("UPDATE students SET department_id = ?, full_name = COALESCE(full_name, name), academic_year = COALESCE(academic_year, year), cgpa = COALESCE(cgpa, ROUND(marks / 10.0, 2)) WHERE id = ?", (department_ids[department], row["id"]))

        existing_count = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        first_names = ["Aarav", "Ananya", "Diya", "Ishaan", "Kavya", "Neel", "Riya", "Tanvi", "Vikram", "Zoya"]
        last_names = ["Patil", "Joshi", "Kulkarni", "Shah", "Deshmukh", "Bhat", "Nair", "Verma"]
        for index in range(existing_count, 100):
            department = branch_names[index % len(branch_names)]
            year = index % 4 + 1
            marks = 65 + (index * 7) % 35
            name = f"{first_names[index % len(first_names)]} {last_names[index % len(last_names)]} {index + 1}"
            db.execute("INSERT OR IGNORE INTO students (name, branch, year, marks, email, full_name, phone_number, gender, date_of_birth, department_id, academic_year, admission_year, current_semester, enrollment_status, address, cgpa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)", (name, department, year, marks, f"student{index + 1}@college.example", name, f"910000{index:04d}", "Female" if index % 2 else "Male", f"200{3 + index % 5}-05-{(index % 27) + 1:02d}", department_ids[department], year, 2022 + index % 4, min(year * 2, 8), f"Campus Residence {index + 1}", round(marks / 10, 2)))

        student_ids = [row[0] for row in db.execute("SELECT id FROM students ORDER BY id").fetchall()]
        course_rows = []
        for index in range(30):
            department = branch_names[index % len(branch_names)]
            course_rows.append((f"Engineering Course {index + 1}", f"ENG{index + 1:03d}", department_ids[department], 3 if index % 4 else 4, index % 8 + 1, "core" if index % 3 else "elective", f"Sample curriculum course for {department}."))
        db.executemany("INSERT OR IGNORE INTO courses (name, code, department_id, credits, semester, course_type, description) VALUES (?, ?, ?, ?, ?, ?, ?)", course_rows)
        course_ids = [row[0] for row in db.execute("SELECT id FROM courses ORDER BY id").fetchall()]
        db.executemany("INSERT OR IGNORE INTO enrollments (student_id, course_id, academic_year, semester, enrollment_date) VALUES (?, ?, ?, ?, ?)", [(student_ids[index % len(student_ids)], course_ids[(index * 7) % len(course_ids)], 2024 + index % 2, index % 8 + 1, "2024-07-15") for index in range(300)])
        db.executemany("INSERT INTO exams (course_id, name, exam_type, exam_date, maximum_marks, academic_year, semester) SELECT ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM exams WHERE course_id = ? AND name = ?)", [(course_ids[index % len(course_ids)], f"Exam {index + 1}", "midterm" if index % 2 else "end-semester", f"2024-{(index % 9) + 1:02d}-15", 100, 2024, index % 8 + 1, course_ids[index % len(course_ids)], f"Exam {index + 1}") for index in range(100)])
        exam_ids = [row[0] for row in db.execute("SELECT id FROM exams ORDER BY id").fetchall()]
        db.executemany("INSERT OR IGNORE INTO results (student_id, exam_id, marks_obtained, grade) VALUES (?, ?, ?, ?)", [(student_ids[(index // 100) * 5 + (index % 5)], exam_ids[index % 100], 55 + (index * 11) % 46, "A" if index % 3 == 0 else "B") for index in range(500)])
        classroom_rows = [(f"Block {chr(65 + index % 4)}", f"{100 + index}", 30 + (index % 5) * 20, "Laboratory" if index % 4 == 0 else "Lecture Hall") for index in range(20)]
        db.executemany("INSERT OR IGNORE INTO classrooms (building, room_number, capacity, classroom_type) VALUES (?, ?, ?, ?)", classroom_rows)
        classroom_ids = [row[0] for row in db.execute("SELECT id FROM classrooms ORDER BY id").fetchall()]
        db.executemany("INSERT INTO timetable (course_id, teacher_id, classroom_id, day_of_week, start_time, end_time, academic_year, semester) SELECT ?, ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM timetable WHERE course_id = ? AND semester = ?)", [(course_ids[index], teacher_ids[index % len(teacher_ids)], classroom_ids[index % len(classroom_ids)], ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][index % 5], "10:00", "11:00", 2024, index % 8 + 1, course_ids[index], index % 8 + 1) for index in range(len(course_ids))])
        db.executemany("INSERT OR IGNORE INTO attendance (student_id, course_id, attendance_date, status) VALUES (?, ?, ?, ?)", [(student_ids[index % len(student_ids)], course_ids[(index * 3) % len(course_ids)], f"2024-08-{index % 28 + 1:02d}", ["present", "present", "late", "absent"][index % 4]) for index in range(600)])
        db.executemany("INSERT INTO fees (student_id, fee_type, amount, due_date, payment_date, payment_status) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM fees WHERE student_id = ? AND fee_type = ?)", [(student_id, "Tuition", 85000, "2024-08-01", "2024-07-25" if index % 4 else None, "paid" if index % 4 else "unpaid", student_id, "Tuition") for index, student_id in enumerate(student_ids)])
        books = [(f"Engineering Reference {index + 1}", f"Author {index + 1}", f"978000000{index + 1:04d}", "Academic Press", 2015 + index % 9, 2 + index % 4, 5 + index % 4, "Engineering") for index in range(15)]
        db.executemany("INSERT OR IGNORE INTO library_books (title, author, isbn, publisher, publication_year, available_copies, total_copies, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", books)
        book_ids = [row[0] for row in db.execute("SELECT id FROM library_books ORDER BY id").fetchall()]
        db.executemany("INSERT INTO library_transactions (student_id, book_id, issue_date, due_date, return_date, transaction_status) SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM library_transactions WHERE student_id = ? AND book_id = ?)", [(student_ids[index % len(student_ids)], book_ids[index % len(book_ids)], "2024-08-01", "2024-08-15", "2024-08-12" if index % 3 else None, "returned" if index % 3 else "issued", student_ids[index % len(student_ids)], book_ids[index % len(book_ids)]) for index in range(50)])
        db.commit()
        return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("students", "teachers", "departments", "courses", "enrollments")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate or explicitly seed the college database.")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--seed-demo", action="store_true")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    if not args.migrate and not args.seed_demo:
        parser.error("Choose --migrate or --seed-demo")
    if args.seed_demo:
        print(seed_demo_data(args.db))
    else:
        with connect(args.db):
            pass
        print(f"Migrated {args.db}")


if __name__ == "__main__":
    main()

