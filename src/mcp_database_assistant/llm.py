"""LLM orchestration: natural language in, MCP tool calls out, answer back."""

from __future__ import annotations

import json
import os
import re
from uuid import uuid4
from collections.abc import Awaitable, Callable
from typing import Any

from groq import AsyncGroq

from .mcp_client import DatabaseMCPClient

ConfirmDelete = Callable[[dict[str, Any]], Awaitable[bool]]


def _groq_tools(mcp_tools: list[Any]) -> list[dict[str, Any]]:
    result = []
    for tool in mcp_tools:
        schema = tool.input_schema
        if hasattr(schema, "model_dump"):
            schema = schema.model_dump(by_alias=True, exclude_none=True)
        result.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "MCP database operation",
                "parameters": schema,
            },
        })
    return result


def _tools_for_request(mcp_tools: list[Any], request: str) -> list[Any]:
    """Keep Groq's free-tier prompt small while retaining MCP tool access."""
    names = {tool.name for tool in mcp_tools}
    text = request.lower()
    selected: set[str]
    if any(word in text for word in ("chart", "plot", "graph", "histogram", "pie", "bar")):
        selected = {"get_chart_data"}
    elif any(word in text for word in ("sql", "query")):
        selected = {"get_sql_query", "query_college", "search_students", "list_courses"}
    elif any(word in text for word in ("course", "enroll", "marks", "result", "attendance", "fee", "library", "teacher", "department")):
        selected = {"query_college", "search_students", "list_courses", "list_teachers", "list_departments"}
    elif any(word in text for word in ("add", "update", "delete", "remove")):
        selected = {"get_table_schema", "find_records", "insert_record", "update_record", "request_delete", "search_students", "get_student", "add_student", "update_student"}
    elif any(word in text for word in ("how many", "count", "number of")):
        selected = {"get_student_count", "search_students", "get_database_summary"}
    else:
        selected = {"list_students", "search_students", "get_student_count", "get_average_marks", "get_top_students"}
    return [tool for tool in mcp_tools if tool.name in selected & names]


class LLMDatabaseAssistant:
    def __init__(self, mcp_client: DatabaseMCPClient, confirm_delete: ConfirmDelete) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is required. Copy .env.example to .env and set it.")
        self.client = mcp_client
        self.confirm_delete = confirm_delete
        # The Groq SDK appends /openai/v1/chat/completions to its base URL.
        # Keeping the SDK base at the host avoids generating /openai/v1 twice.
        self.llm = AsyncGroq(api_key=api_key, base_url="https://api.groq.com")
        self.model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.last_charts: list[dict[str, Any]] = []
        self.last_sql: dict[str, Any] | None = None
        self.session_id = uuid4().hex
        self.pending_deletion: dict[str, Any] | None = None
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful student database assistant. You must use the supplied MCP tools "
                    "for every database fact or change. You cannot access SQL or SQLite directly. "
                    "Use IDs for update/delete; when the user gives a name, search first. Never claim a "
                    "write succeeded unless the tool result says it succeeded. Keep answers concise and clear. "
                    "For every chart request, call get_chart_data before answering. Select a supported dataset "
                    "and the user's requested chart_type. Never invent chart values, SQL, or Python code. "
                    "Supported datasets include students_by_branch, students_by_year, students_by_gender, "
                    "students_average_marks_by_branch, student_marks_distribution, top_students_marks, "
                    "teachers_by_department, teacher_salary_distribution, courses_by_department, "
                    "course_enrollment, enrollments_by_year, fees_by_status, books_by_category, "
                    "attendance_by_status, and student_marks_by_year."
                    " For questions requiring joins, use query_college with a named operation instead of isolated table calls. "
                    "Supported relational operations include students_by_name_courses, students_by_course, "
                    "marks_by_student_name, course_marks_above, teacher_courses, attendance_below, "
                    "unpaid_fees_by_department, and overdue_books. Preserve student IDs when resolving follow-ups "
                    "such as 'they', 'those students', or 'their courses'. If the user explicitly asks to write/show "
                    "SQL, call get_sql_query and present its returned parameterized SQL in a code block; do not execute it."
                    " For modifications, inspect get_table_schema when needed, use insert_record/update_record/delete_record "
                    "for all tables, and use find_records to resolve identifiers. Never update an ambiguous match. "
                    "For deletion, call request_delete only; never call or simulate confirmation yourself. The application "
                    "will separately confirm or cancel the returned confirmation request. "
                    "Never modify id, provenance_id, or data_origin."
                ),
            }
        ]

    async def respond(self, user_text: str) -> str:
        self.last_charts = []
        self.last_sql = None
        normalized = user_text.strip().lower()
        affirmative = bool(re.fullmatch(r"(?:yes|y|yes,? delete it|confirm(?: deletion)?|i am sure|proceed(?: with deletion)?)", normalized))
        cancellation = bool(re.fullmatch(r"(?:no|n|cancel|keep the record|do not delete|don't delete)", normalized))
        if self.pending_deletion and affirmative:
            result = await self.client.call_tool("confirm_delete", {
                "confirmation_id": self.pending_deletion["confirmation_id"],
                "session_id": self.session_id,
                "cascade_confirmed": bool(self.pending_deletion.get("cascade_confirmation_requested")),
            })
            if result.get("requires_cascade_confirmation"):
                self.pending_deletion["cascade_confirmation_requested"] = True
                return "Related records exist. Please explicitly confirm the additional cascade deletion."
            self.pending_deletion = None
            return result.get("message", "Deletion was not completed.")
        if self.pending_deletion and cancellation:
            result = await self.client.call_tool("cancel_delete", {
                "confirmation_id": self.pending_deletion["confirmation_id"],
                "session_id": self.session_id,
            })
            self.pending_deletion = None
            return result.get("message", "Deletion cancelled.")
        if self.pending_deletion and not any(word in normalized for word in ("delete", "remove")):
            return "A deletion is pending for the displayed record. Reply with a clear confirmation or cancellation."
        self.messages.append({"role": "user", "content": user_text})
        requested_chart_type = None
        chart_type_patterns = (
            ("horizontal_bar", r"horizontal\s+bar"),
            ("donut", r"donut"),
            ("histogram", r"histogram"),
            ("scatter", r"scatter"),
            ("line", r"line\s+chart|line\s+plot"),
            ("pie", r"pie\s+chart|pie\s+plot"),
            ("bar", r"bar\s+chart|bar\s+plot"),
        )
        for chart_type, pattern in chart_type_patterns:
            if re.search(pattern, user_text, re.IGNORECASE):
                requested_chart_type = chart_type
                break
        tools = _groq_tools(_tools_for_request(await self.client.list_tools(), user_text))
        for _ in range(8):
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=1024,
                max_completion_tokens=1024,
            )
            message = response.choices[0].message
            if not message.tool_calls:
                answer = message.content or "I could not produce a response."
                self.messages.append({"role": "assistant", "content": answer})
                return answer

            assistant_message = message.model_dump(exclude_none=True)
            self.messages.append(assistant_message)
            for tool_call in message.tool_calls:
                arguments = json.loads(tool_call.function.arguments or "{}")
                if tool_call.function.name == "get_chart_data" and requested_chart_type:
                    arguments["chart_type"] = requested_chart_type
                if tool_call.function.name == "request_delete":
                    arguments["session_id"] = self.session_id
                    tool_result = await self.client.call_tool("request_delete", arguments)
                    if tool_result.get("pending"):
                        self.pending_deletion = tool_result
                else:
                    tool_result = await self.client.call_tool(tool_call.function.name, arguments)
                if tool_call.function.name == "get_chart_data":
                    self.last_charts.append({"spec": arguments, "data": tool_result})
                if tool_call.function.name == "get_sql_query":
                    self.last_sql = tool_result
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result, default=str),
                })
                if tool_call.function.name == "request_delete" and tool_result.get("pending"):
                    record = tool_result.get("record", {})
                    label = record.get("name") or record.get("full_name") or f"{tool_result.get('table')} record"
                    return f"I found {label}: {json.dumps(record, default=str)}. No deletion has occurred. Please explicitly confirm or cancel this deletion."
        return "I could not complete that request within the tool-call limit."

