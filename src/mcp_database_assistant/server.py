"""MCP database server. It is the only process that imports the SQLite layer."""

from __future__ import annotations

from mcp.server import MCPServer

try:
    from . import db_tools
except ImportError:  # Supports the MCP CLI importing this file by path.
    from mcp_database_assistant import db_tools

mcp = MCPServer(
    "Student Database Server",
    instructions="Expose safe, validated student database operations. Never execute arbitrary SQL.",
)


@mcp.tool()
def list_students() -> dict:
    """Return all students in the database."""
    return db_tools.list_students()


@mcp.tool()
def get_student(student_id: int) -> dict:
    """Return one student by positive integer ID, or found=false when absent."""
    return db_tools.get_student(student_id)


@mcp.tool()
def search_students(name: str | None = None, branch: str | None = None,
                    min_marks: float | None = None, max_marks: float | None = None) -> dict:
    """Search students using optional name, branch, minimum marks, and maximum marks filters."""
    return db_tools.search_students(name, branch, min_marks, max_marks)


@mcp.tool()
def get_average_marks() -> dict:
    """Return the average marks and the number of students included."""
    return db_tools.get_average_marks()


@mcp.tool()
def get_student_count() -> dict:
    """Return the total number of students."""
    return db_tools.get_student_count()


@mcp.tool()
def get_top_students(limit: int = 5) -> dict:
    """Return up to 100 students with the highest marks."""
    return db_tools.get_top_students(limit)


@mcp.tool()
def get_students_by_branch(branch: str) -> dict:
    """Return students whose branch contains the supplied text."""
    return db_tools.get_students_by_branch(branch)


@mcp.tool()
def get_students_by_year(year: int) -> dict:
    """Return students in academic year 1 through 8."""
    return db_tools.get_students_by_year(year)


@mcp.tool()
def add_student(name: str, branch: str, year: int, marks: float, email: str | None = None) -> dict:
    """Insert a student after validating name, branch, year, marks, and optional email."""
    return db_tools.add_student(name, branch, year, marks, email)


@mcp.tool()
def update_student(student_id: int, name: str | None = None, branch: str | None = None,
                  year: int | None = None, marks: float | None = None,
                  email: str | None = None) -> dict:
    """Update only the provided fields of an existing student and report whether data changed."""
    return db_tools.update_student(student_id, name, branch, year, marks, email)


@mcp.tool()
def delete_student(student_id: int) -> dict:
    """Delete one student by ID and report whether a database row was changed."""
    return db_tools.delete_student(student_id)


@mcp.tool()
def list_teachers(search: str | None = None, department: str | None = None) -> dict:
    """List teachers, optionally filtered by name or department."""
    return db_tools.list_teachers(search, department)


@mcp.tool()
def get_teacher(teacher_id: int) -> dict:
    """Return one teacher by ID."""
    return db_tools.get_teacher(teacher_id)


@mcp.tool()
def list_departments() -> dict:
    """List departments and their heads where assigned."""
    return db_tools.list_departments()


@mcp.tool()
def list_courses(department: str | None = None, semester: int | None = None) -> dict:
    """List courses, optionally filtered by department or semester."""
    return db_tools.list_courses(department, semester)


@mcp.tool()
def list_enrollments(student_id: int | None = None, course_id: int | None = None,
                     academic_year: int | None = None) -> dict:
    """List course enrollments with student and course details."""
    return db_tools.list_enrollments(student_id, course_id, academic_year)


@mcp.tool()
def list_results(student_id: int | None = None, course_id: int | None = None) -> dict:
    """List exam results, optionally for a student or course."""
    return db_tools.list_results(student_id, course_id)


@mcp.tool()
def list_attendance(student_id: int | None = None, course_id: int | None = None) -> dict:
    """List attendance records, optionally for a student or course."""
    return db_tools.list_attendance(student_id, course_id)


@mcp.tool()
def list_fees(student_id: int | None = None, payment_status: str | None = None) -> dict:
    """List student fee records, optionally filtered by student or payment status."""
    return db_tools.list_fees(student_id, payment_status)


@mcp.tool()
def search_library_books(query_text: str | None = None, category: str | None = None) -> dict:
    """Search library books by title, author, ISBN, or category."""
    return db_tools.search_library_books(query_text, category)


@mcp.tool()
def list_library_transactions(student_id: int | None = None, status: str | None = None) -> dict:
    """List library transactions, optionally filtered by student or status."""
    return db_tools.list_library_transactions(student_id, status)


@mcp.tool()
def list_timetable(teacher_id: int | None = None, course_id: int | None = None,
                   academic_year: int | None = None) -> dict:
    """List timetable entries, optionally filtered by teacher, course, or year."""
    return db_tools.list_timetable(teacher_id, course_id, academic_year)


@mcp.tool()
def get_database_summary() -> dict:
    """Return live counts for students, teachers, departments, courses, and enrollments."""
    return db_tools.get_database_summary()


@mcp.tool()
def query_college(operation: str, filters: dict | None = None, limit: int = 100) -> dict:
    """Run a safe named read-only relational query across multiple tables.

    Supported operations include students_by_name_courses, students_by_course,
    marks_by_student_name, course_marks_above, teacher_courses,
    attendance_below, unpaid_fees_by_department, and overdue_books.
    Filters are ordinary values such as name, course, min_marks, threshold, or teacher;
    arbitrary SQL is never accepted.
    """
    return db_tools.query_college(operation, filters, limit)


@mcp.tool()
def get_sql_query(operation: str, filters: dict | None = None, limit: int = 100) -> dict:
    """Return approved parameterized SQL for a named relational operation without executing it."""
    return db_tools.get_sql_query(operation, filters, limit)


@mcp.tool()
def get_table_schema(table: str | None = None) -> dict:
    """Return actual columns and SQLite metadata for one supported table or all tables."""
    return db_tools.table_schema(table)


@mcp.tool()
def find_records(table: str, where: dict | None = None, limit: int = 50) -> dict:
    """Find records in any supported table using exact, schema-validated field filters."""
    return db_tools.find_records(table, where, limit)


@mcp.tool()
def insert_record(table: str, values: dict) -> dict:
    """Insert one record into any supported table; required fields and foreign keys are validated."""
    return db_tools.insert_record(table, values)


@mcp.tool()
def update_record(table: str, where: dict, values: dict) -> dict:
    """Update one unambiguous record in any supported table. Primary keys and provenance metadata are protected."""
    return db_tools.update_record(table, where, values)


@mcp.tool()
def delete_record(table: str, where: dict, confirmed: bool = False,
                 cascade_confirmed: bool = False) -> dict:
    """Delete exactly one record after explicit confirmation; dependent cascades require separate confirmation."""
    return db_tools.delete_record(table, where, confirmed, cascade_confirmed)


@mcp.tool()
def get_chart_data(dataset: str, chart_type: str = "bar", title: str | None = None,
                  filters: dict | None = None, limit: int = 100) -> dict:
    """Return validated, read-only chart rows from a supported college dataset.

    Choose a dataset such as students_by_branch, students_average_marks_by_branch,
    students_by_gender, teacher_salary_distribution, courses_by_department,
    course_enrollment, enrollments_by_year, or student_marks_distribution.
    This tool never accepts SQL or Python code.
    """
    return db_tools.get_chart_data(dataset, chart_type, title, filters, limit)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

