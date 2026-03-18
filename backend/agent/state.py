"""
Agent state definition — TypedDict shared across all LangGraph nodes.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state passed through the LangGraph pipeline."""

    # Conversation
    messages: list[dict[str, str]]       # full chat history
    user_query: str                      # the current user message
    conversation_id: str

    # Intent
    intent: str                          # query_generation | documentation | clarification_response | general | explain_filter | compare_filters

    # Retrieval
    schema_context: str                  # formatted schema retriever output
    example_context: str                 # formatted example retriever output
    schema_fields: list[dict[str, Any]]  # raw retrieved fields

    # Generation
    generated_json: str                  # raw JSON string from LLM
    generated_filter: dict[str, Any]     # parsed filter object
    generation_attempts: int             # retry count

    # Validation
    is_valid: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    fields_used: list[str]

    # Clarification
    needs_clarification: bool
    clarification_question: str
    clarification_options: list[str]
    pending_context: str                 # stashed context from before clarification

    # Response
    response_text: str                   # final text to stream to user
    filter_result: dict[str, Any] | None # final filter JSON (if generated)
    event_type: str                      # what kind of response this is

    # Reverse explanation (F5)
    pasted_filter: dict[str, Any] | None # filter JSON pasted by user for explanation

    # Comparison (F2)
    comparison_result: dict[str, Any] | None  # cohort comparison output
