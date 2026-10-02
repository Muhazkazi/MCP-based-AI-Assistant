"""LLM orchestration: natural language in, MCP tool calls out, answer back."""

from __future__ import annotations

import json
import os
import re
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
        selected = {"get_table_schema", "find_records", "insert_record", "update_record", "delete_record", "search_students", "get_student", "add_student", "update_student", "delete_student"}
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
                    "Never modify id, provenance_id, or data_origin."
                ),
            }
        ]

    async def respond(self, user_text: str) -> str:
        self.last_charts = []
        self.last_sql = None
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
                if tool_call.function.name == "delete_student":
                    lookup = await self.client.call_tool("get_student", {"student_id": arguments["student_id"]})
                    student = lookup.get("student")
                    if not lookup.get("found"):
                        tool_result = {"success": False, "found": False, "changed": False}
                    elif not await self.confirm_delete(student):
                        tool_result = {"success": False, "found": True, "changed": False, "cancelled": True}
                    else:
                        tool_result = await self.client.call_tool(tool_call.function.name, arguments)
                elif tool_call.function.name == "delete_record":
                    preview_args = {"table": arguments["table"], "where": arguments["where"], "limit": 2}
                    preview = await self.client.call_tool("find_records", preview_args)
                    records = preview.get("records", [])
                    if len(records) != 1:
                        tool_result = {"success": False, "found": bool(records), "ambiguous": len(records) > 1, "message": "Deletion requires one exact record."}
                    elif not await self.confirm_delete({"table": arguments["table"], "where": arguments["where"], "record": records[0], "delete_request": arguments}):
                        tool_result = {"success": False, "found": True, "cancelled": True, "requires_confirmation": True, "record": records[0], "delete_request": arguments}
                    else:
                        arguments["confirmed"] = True
                        tool_result = await self.client.call_tool(tool_call.function.name, arguments)
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
        return "I could not complete that request within the tool-call limit."

