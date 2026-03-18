"""
Pydantic models for API requests and responses.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class EventType(str, Enum):
    """SSE event types sent to the frontend."""
    TOKEN = "token"              # streaming text token
    FILTER_JSON = "filter_json"  # completed GQL filter
    CLARIFICATION = "clarification"
    ERROR = "error"
    DONE = "done"
    STATUS = "status"            # intermediate status updates
    COMPARISON = "comparison"    # cohort comparison result


# ── Request models ───────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: MessageRole
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)


# ── Response models ──────────────────────────────────────────────

class ClarificationOption(BaseModel):
    label: str
    value: str


class ClarificationPayload(BaseModel):
    question: str
    options: list[ClarificationOption] = Field(default_factory=list)


class FilterResult(BaseModel):
    gql_filter: dict[str, Any]
    explanation: str
    fields_used: list[str] = Field(default_factory=list)
    is_valid: bool = True
    validation_errors: list[str] = Field(default_factory=list)


class SSEEvent(BaseModel):
    event: EventType
    data: Any


# ── Saved filters ────────────────────────────────────────────────

class SaveFilterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    filter_json: dict[str, Any]
    nl_description: str = ""
    conversation_id: str | None = None


class SavedFilter(BaseModel):
    id: str
    name: str
    filter_json: dict[str, Any]
    nl_description: str
    fields_used: list[str] = Field(default_factory=list)
    created_at: str  # ISO 8601


class ExportFormat(str, Enum):
    JSON = "json"
    GRAPHQL = "graphql"


# ── Cohort comparison ────────────────────────────────────────────

class CompareRequest(BaseModel):
    filter_a: dict[str, Any]
    filter_b: dict[str, Any]
    name_a: str = "Cohort A"
    name_b: str = "Cohort B"


class FieldDiff(BaseModel):
    field: str
    status: str  # "added" | "removed" | "changed"
    value_a: Any | None = None
    value_b: Any | None = None


class ComparisonResult(BaseModel):
    diffs: list[FieldDiff]
    summary: str
    filter_a: dict[str, Any]
    filter_b: dict[str, Any]
    filter_a_name: str = "Filter A"
    filter_b_name: str = "Filter B"
