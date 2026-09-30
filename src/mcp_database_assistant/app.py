"""Terminal chat application."""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

from .llm import LLMDatabaseAssistant
from .mcp_client import DatabaseMCPClient


async def _confirm_delete(student: dict) -> bool:
    print(f"The student is {student['name']} (ID {student['id']}, {student['branch']}). Delete this student? [y/N]")
    return (await asyncio.to_thread(input, "You: ")).strip().lower() in {"y", "yes"}


async def run_chat() -> None:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("MCP Database Assistant")
    print("Type a natural-language request, or 'quit' to exit.")
    async with DatabaseMCPClient() as mcp_client:
        assistant = LLMDatabaseAssistant(mcp_client, _confirm_delete)
        while True:
            user_text = await asyncio.to_thread(input, "\nYou: ")
            if user_text.strip().lower() in {"quit", "exit"}:
                break
            if not user_text.strip():
                continue
            try:
                print(f"Assistant: {await assistant.respond(user_text)}")
            except Exception as exc:
                print(f"Assistant error: {exc}")


def main() -> None:
    asyncio.run(run_chat())


if __name__ == "__main__":
    main()

