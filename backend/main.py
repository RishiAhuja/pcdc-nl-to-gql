"""
PCDC Cohort Discovery Chatbot — FastAPI backend.

Start:
    cd chatbot/backend
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from config import get_settings
from models import (
    ChatRequest,
    EventType,
    FilterResult,
    ClarificationPayload,
    ClarificationOption,
    SaveFilterRequest,
    SavedFilter,
    CompareRequest,
)
from agent.graph import agent_graph
from agent.state import AgentState
from utils.filter_utils import (
    diff_filters,
    format_diff_summary,
    export_as_graphql,
    export_as_aggregation,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="PCDC Cohort Discovery Chatbot",
    version="0.1.0",
    description="AI-powered GraphQL filter generation for the Pediatric Cancer Data Commons",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory conversation store (replace with Redis for prod) ───
_conversations: dict[str, list[dict]] = {}

# ── In-memory saved filters (replace with PostgreSQL for prod) ───
_saved_filters: dict[str, dict] = {}  # id → filter data


def _get_history(conv_id: str) -> list[dict]:
    return _conversations.setdefault(conv_id, [])


def _sse_event(event: str, data: Any) -> dict:
    """Format an SSE event."""
    return {"event": event, "data": json.dumps(data) if not isinstance(data, str) else data}


# ── Routes ───────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint — returns Server-Sent Events.

    Events:
      - status:        {"text": "Classifying intent..."}
      - token:         {"text": "partial response..."}
      - filter_json:   {"filter": {...}, "explanation": "...", "fields_used": [...]}
      - clarification: {"question": "...", "options": [...]}
      - error:         {"text": "Something went wrong"}
      - done:          {}
    """
    conv_id = request.conversation_id or str(uuid.uuid4())
    history = _get_history(conv_id)

    # Add new user message to history
    history.append({"role": "user", "content": request.message})

    async def event_stream() -> AsyncGenerator[dict, None]:
        try:
            # Build initial state
            initial_state: AgentState = {
                "messages": history,
                "user_query": request.message,
                "conversation_id": conv_id,
                "generation_attempts": 0,
                "needs_clarification": False,
            }

            # Check if there's pending context from a prior clarification
            if len(history) >= 3:
                # Look for a prior assistant clarification message
                for prev_msg in reversed(history[:-1]):
                    if prev_msg.get("role") == "assistant" and prev_msg.get("_pending_context"):
                        initial_state["needs_clarification"] = True
                        initial_state["pending_context"] = prev_msg["_pending_context"]
                        break

            yield _sse_event("status", {"text": "Analyzing your request..."})

            # Run the agent graph
            final_state = agent_graph.invoke(initial_state)

            event_type = final_state.get("event_type", "token")
            response_text = final_state.get("response_text", "")
            filter_result = final_state.get("filter_result")

            if event_type == "clarification":
                question = final_state.get("clarification_question", response_text)
                options = final_state.get("clarification_options", [])

                payload = ClarificationPayload(
                    question=question,
                    options=[ClarificationOption(label=o, value=o) for o in options],
                )

                # Store pending context in history for the next turn
                history.append({
                    "role": "assistant",
                    "content": question,
                    "_pending_context": final_state.get("pending_context", ""),
                })

                yield _sse_event("clarification", payload.model_dump())

            elif filter_result:
                # Send text explanation first
                history.append({
                    "role": "assistant",
                    "content": response_text,
                    "_filter": json.dumps(filter_result),
                })
                yield _sse_event("token", {"text": response_text})

                # Then send the filter JSON in the shape the frontend expects
                filter_payload = {
                    "filter": filter_result,
                    "is_valid": final_state.get("is_valid", True),
                    "errors": final_state.get("validation_errors", []),
                    "warnings": final_state.get("validation_warnings", []),
                    "fields_used": final_state.get("fields_used", []),
                }
                yield _sse_event("filter_json", filter_payload)

            else:
                # General text response (or comparison)
                history.append({"role": "assistant", "content": response_text})

                if event_type == "comparison" and final_state.get("comparison_result"):
                    yield _sse_event("token", {"text": response_text})
                    yield _sse_event("comparison", final_state["comparison_result"])
                else:
                    yield _sse_event("token", {"text": response_text})

            yield _sse_event("done", {"conversation_id": conv_id})

        except Exception as e:
            logger.exception("Agent error")
            yield _sse_event("error", {"text": str(e)})
            yield _sse_event("done", {"conversation_id": conv_id})

    return EventSourceResponse(event_stream())


@app.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Get conversation history."""
    history = _conversations.get(conv_id)
    if history is None:
        raise HTTPException(404, "Conversation not found")
    # Strip internal keys from history
    clean = [
        {"role": m["role"], "content": m["content"]}
        for m in history
    ]
    return {"conversation_id": conv_id, "messages": clean}


@app.delete("/conversations/{conv_id}")
async def clear_conversation(conv_id: str):
    """Clear a conversation."""
    _conversations.pop(conv_id, None)
    return {"status": "cleared"}


# ── Saved Filters (F1) ──────────────────────────────────────────

@app.post("/filters/save")
async def save_filter(request: SaveFilterRequest):
    """Save a generated filter with a name."""
    from datetime import datetime, timezone

    filter_id = str(uuid.uuid4())[:8]
    saved = {
        "id": filter_id,
        "name": request.name,
        "filter_json": request.filter_json,
        "nl_description": request.nl_description,
        "fields_used": list(_extract_fields_from_filter(request.filter_json)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "conversation_id": request.conversation_id,
    }
    _saved_filters[filter_id] = saved
    return saved


@app.get("/filters")
async def list_filters():
    """List all saved filters, newest first."""
    filters = sorted(
        _saved_filters.values(),
        key=lambda f: f["created_at"],
        reverse=True,
    )
    return {"filters": filters}


@app.get("/filters/{filter_id}")
async def get_filter(filter_id: str):
    """Get a saved filter by ID."""
    f = _saved_filters.get(filter_id)
    if f is None:
        raise HTTPException(404, "Filter not found")
    return f


@app.delete("/filters/{filter_id}")
async def delete_filter(filter_id: str):
    """Delete a saved filter."""
    if filter_id not in _saved_filters:
        raise HTTPException(404, "Filter not found")
    _saved_filters.pop(filter_id)
    return {"status": "deleted"}


# ── Filter Export (F3) ───────────────────────────────────────────

@app.post("/filters/export/graphql")
async def export_filter_graphql(body: dict):
    """Export a filter as a full Guppy GraphQL query string."""
    filter_json = body.get("filter")
    if not filter_json:
        raise HTTPException(400, "Missing 'filter' key in request body")
    return {"graphql": export_as_graphql(filter_json)}


@app.post("/filters/export/aggregation")
async def export_filter_aggregation(body: dict):
    """Export a filter as a Guppy aggregation query."""
    filter_json = body.get("filter")
    if not filter_json:
        raise HTTPException(400, "Missing 'filter' key in request body")
    return {"graphql": export_as_aggregation(filter_json)}


# ── Filter Comparison (F2 — direct API) ──────────────────────────

@app.post("/filters/compare")
async def compare_filters_api(request: CompareRequest):
    """Compare two filters directly (non-chat API)."""
    diffs = diff_filters(request.filter_a, request.filter_b)
    summary = format_diff_summary(diffs)
    return {
        "diffs": diffs,
        "diff_summary": summary,
        "filter_a": request.filter_a,
        "filter_b": request.filter_b,
        "filter_a_name": request.names[0] if request.names and len(request.names) > 0 else "Filter A",
        "filter_b_name": request.names[1] if request.names and len(request.names) > 1 else "Filter B",
    }


# ── Helpers ──────────────────────────────────────────────────────

def _extract_fields_from_filter(node: dict, fields: set | None = None) -> set:
    """Recursively extract field names from a Guppy filter."""
    if fields is None:
        fields = set()
    if not isinstance(node, dict):
        return fields
    for key, val in node.items():
        if key in ("AND", "OR") and isinstance(val, list):
            for item in val:
                _extract_fields_from_filter(item, fields)
        elif key == "nested" and isinstance(val, dict):
            for sub in val.get("AND", val.get("OR", [])):
                if isinstance(sub, (dict, list)):
                    _extract_fields_from_filter(sub if isinstance(sub, dict) else {}, fields)
        elif key in ("IN", "GTE", "LTE", "GT", "LT") and isinstance(val, dict):
            fields.update(val.keys())
    return fields


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.backend_port, reload=True)
