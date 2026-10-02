"""Streamlit dashboard and web chat for the existing MCP assistant."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from mcp_database_assistant.analytics import students_from_result
from mcp_database_assistant.charting import ChartValidationError, render_chart
from mcp_database_assistant.llm import LLMDatabaseAssistant
from mcp_database_assistant.mcp_client import DatabaseMCPClient

load_dotenv()

st.set_page_config(
    page_title="MCP Database Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 3rem; }
    [data-testid="stMetric"] { border: 1px solid #d9e2ec; padding: 1rem; border-radius: 10px; background: #ffffff; }
    [data-testid="stSidebar"] { border-right: 1px solid #d9e2ec; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _run(coroutine):
    return asyncio.run(coroutine)


def _friendly_error(exc: Exception) -> str:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return "Groq is rate-limiting requests right now. Please wait a moment and try again."
    if status_code in {401, 403}:
        return "The Groq API key is missing or invalid. Check GROQ_API_KEY in .env."
    if status_code and status_code >= 500:
        return "The Groq service is temporarily unavailable. Please try again shortly."
    return str(exc)


async def _fetch_dashboard_data() -> dict[str, int]:
    async with DatabaseMCPClient() as client:
        return await client.call_tool("get_database_summary", {})


async def _fetch_students() -> list[dict[str, Any]]:
    async with DatabaseMCPClient() as client:
        return students_from_result(await client.call_tool("list_students", {}))


async def _delete_confirmed(pending: dict[str, Any], cascade_confirmed: bool = False) -> dict[str, Any]:
    async with DatabaseMCPClient() as client:
        if pending.get("delete_request"):
            request = dict(pending["delete_request"])
            request["confirmed"] = True
            request["cascade_confirmed"] = cascade_confirmed
            return await client.call_tool("delete_record", request)
        return await client.call_tool("delete_student", {"student_id": pending["id"]})


async def _chat_turn(history: list[dict[str, Any]], user_text: str) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None, list[dict[str, Any]]]:
    pending_delete: dict[str, Any] | None = None

    async def confirm_delete(student: dict[str, Any]) -> bool:
        nonlocal pending_delete
        pending_delete = student
        return False

    async with DatabaseMCPClient() as client:
        assistant = LLMDatabaseAssistant(client, confirm_delete)
        if history:
            assistant.messages = history
        answer = await assistant.respond(user_text)
        return assistant.messages, answer, pending_delete, assistant.last_charts


def _load_dashboard() -> None:
    try:
        summary = _run(_fetch_dashboard_data())
    except Exception as exc:
        st.error(f"Could not load dashboard data: {_friendly_error(exc)}")
        return

    st.title("MCP-Based AI Database Assistant")
    st.caption("A natural-language interface to the college database, powered by Groq and MCP.")
    st.markdown(
        "Ask questions in ordinary language, retrieve college information, manage supported records, "
        "and generate interactive charts directly inside AI Chat. Groq interprets the request; the MCP "
        "client discovers and calls safe tools on the MCP server; the server reads or changes SQLite."
    )

    st.subheader("Live college database")
    cards = st.columns(5)
    cards[0].metric("Students", summary.get("students_count", 0))
    cards[1].metric("Teachers", summary.get("teachers_count", 0))
    cards[2].metric("Departments", summary.get("departments_count", 0))
    cards[3].metric("Courses", summary.get("courses_count", 0))
    cards[4].metric("Enrollments", summary.get("enrollments_count", 0))

    st.subheader("Architecture")
    st.code("User → Streamlit UI → Groq LLM → MCP Client → MCP Server → College SQLite Database")
    st.markdown(
        "### Start with AI Chat\n"
        "Try `How many students are in each department?`, `Show students with attendance below 75%`, "
        "or `Create a pie chart of average marks by branch.` The charts are generated from live MCP results."
    )


def _render_chat() -> None:
    st.title("AI Chat")
    st.caption("Natural-language requests are interpreted by Groq and executed through MCP tools.")

    if "chat_display" not in st.session_state:
        st.session_state.chat_display = []
    if "llm_messages" not in st.session_state:
        st.session_state.llm_messages = []

    for message in st.session_state.chat_display:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for chart in message.get("charts", []):
                try:
                    st.plotly_chart(render_chart(chart), use_container_width=True)
                except ChartValidationError as exc:
                    st.info(str(exc))

    pending = st.session_state.get("pending_delete")
    if pending:
        record = pending.get("record", pending)
        label = record.get("name") or record.get("full_name") or f"{pending.get('table', 'record')} record"
        identifier = record.get("id", pending.get("where", ""))
        st.warning(f"Delete {label} (ID {identifier})? This action cannot be undone.")
        cascade_required = bool(pending.get("cascade_required"))
        button_label = "Confirm cascading deletion" if cascade_required else "Confirm deletion"
        if cascade_required:
            dependencies = pending.get("dependencies", [])
            st.warning(f"This will also remove related rows: {dependencies}. Confirm this additional cascade explicitly.")
        if st.button(button_label, type="primary"):
            try:
                result = _run(_delete_confirmed(pending, cascade_required))
                if result.get("requires_cascade_confirmation"):
                    pending["cascade_required"] = True
                    pending["dependencies"] = result.get("dependencies", [])
                    st.session_state.pending_delete = pending
                    st.rerun()
                st.session_state.pending_delete = None
                text = (
                    f"Deleted {label} successfully."
                    if result.get("changed")
                    else "The student was not deleted."
                )
                st.session_state.chat_display.append({"role": "assistant", "content": text})
                st.rerun()
            except Exception as exc:
                st.error(f"Could not delete the student: {_friendly_error(exc)}")

    user_text = st.chat_input("Ask about students or request a database operation")
    if user_text:
        st.session_state.chat_display.append({"role": "user", "content": user_text})
        try:
            with st.spinner("Groq is consulting the MCP database tools..."):
                history, answer, pending_delete, charts = _run(
                    _chat_turn(st.session_state.llm_messages, user_text)
                )
            st.session_state.llm_messages = history
            st.session_state.chat_display.append({"role": "assistant", "content": answer, "charts": charts})
            if pending_delete:
                st.session_state.pending_delete = pending_delete
            st.rerun()
        except Exception as exc:
            st.session_state.chat_display.append({
                "role": "assistant",
                "content": f"I could not complete that request: {_friendly_error(exc)}",
            })
            st.rerun()


def _render_students() -> None:
    st.title("Students")
    st.caption("Live records retrieved through the MCP database server")
    try:
        students = _run(_fetch_students())
    except Exception as exc:
        st.error(f"Could not load student records: {_friendly_error(exc)}")
        return

    if not students:
        st.info("No student records are available.")
        return

    branches = sorted({student.get("branch") for student in students if student.get("branch")})
    years = sorted({student.get("year") for student in students if student.get("year") is not None})
    filters = st.columns(3)
    selected_branches = filters[0].multiselect("Branch", branches)
    selected_years = filters[1].multiselect("Academic year", years)
    sort_descending = filters[2].toggle("Highest marks first", value=True)

    filtered = [
        student for student in students
        if (not selected_branches or student.get("branch") in selected_branches)
        and (not selected_years or student.get("year") in selected_years)
    ]
    filtered.sort(key=lambda student: float(student.get("marks") or 0), reverse=sort_descending)
    st.caption(f"Showing {len(filtered)} of {len(students)} students")
    st.dataframe(filtered, hide_index=True, use_container_width=True)


def main() -> None:
    with st.sidebar:
        st.title("MCP Database Assistant")
        st.caption("Groq · MCP · SQLite")
        page = st.radio("Navigate", ["Dashboard", "AI Chat", "Students"], label_visibility="collapsed")
        if st.button("Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.divider()
        st.caption("Database connection")
        st.caption("MCP server: stdio")

    if page == "Dashboard":
        _load_dashboard()
    elif page == "AI Chat":
        _render_chat()
    else:
        _render_students()


if __name__ == "__main__":
    main()

