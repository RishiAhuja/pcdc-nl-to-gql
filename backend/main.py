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
)
from agent.graph import agent_graph
from agent.state import AgentState

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
                # General text response
                history.append({"role": "assistant", "content": response_text})
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.backend_port, reload=True)
