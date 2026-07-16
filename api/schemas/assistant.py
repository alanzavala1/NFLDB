"""Request/response models for the natural-language `/ask` assistant.

The response carries three things on purpose: the written `answer`, the
structured `data` rows that back it (so the frontend can render the familiar
table), and `tools_used` (so the UI can show a "how I got this" line and the
user can see the answer is grounded in real tool calls, not invented).

Request history is deliberately text-only. Prior tool calls/results are never
replayed; each new answer must ground its figures through fresh tool calls.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class AskHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    question: str
    history: list[AskHistoryMessage] = Field(default_factory=list)


class ToolCall(BaseModel):
    tool: str
    args: dict[str, Any]


class AskResponse(BaseModel):
    answer: str
    # Heterogeneous rows — shape depends on which tool answered. The frontend
    # renders them generically (keys become columns).
    data: list[dict[str, Any]]
    tools_used: list[ToolCall]
