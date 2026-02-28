"""
LangGraph node functions — each is one step of the agent pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, get_llm_json
from agent.state import AgentState
from prompts.templates import (
    INTENT_SYSTEM,
    INTENT_HUMAN,
    QUERY_GEN_SYSTEM,
    QUERY_GEN_HUMAN,
    VALIDATION_FIX_SYSTEM,
    VALIDATION_FIX_HUMAN,
    CLARIFICATION_SYSTEM,
    CLARIFICATION_HUMAN,
    EXPLANATION_SYSTEM,
    EXPLANATION_HUMAN,
    GENERAL_SYSTEM,
    GENERAL_HUMAN,
)
from retrieval.schema_retriever import SchemaRetriever
from retrieval.example_retriever import ExampleRetriever
from validation.validator import get_validator

logger = logging.getLogger(__name__)

# Lazy singletons — initialised on first use
_schema_retriever: SchemaRetriever | None = None
_example_retriever: ExampleRetriever | None = None


def _get_schema_retriever() -> SchemaRetriever:
    global _schema_retriever
    if _schema_retriever is None:
        _schema_retriever = SchemaRetriever()
    return _schema_retriever


def _get_example_retriever() -> ExampleRetriever:
    global _example_retriever
    if _example_retriever is None:
        _example_retriever = ExampleRetriever()
    return _example_retriever


def _build_conversation_history(messages: list[dict], max_turns: int = 4) -> str:
    """
    Format the last `max_turns` user+assistant pairs from the conversation
    history into a plain-text string for injection into the generation prompt.

    Strips internal keys like _pending_context that are never visible to the
    LLM.  Returns "(No prior conversation)" if messages is empty so the
    prompt section always has meaningful content.

    Example output:
        USER: Show me AML females under 5
        ASSISTANT: {"AND": [{"IN": {"sex": ["Female"]}}, ...]}
        USER: Now filter for males instead
    """
    if not messages:
        return "(No prior conversation)"

    # Take the last max_turns * 2 messages (each turn = 1 user + 1 assistant)
    recent = messages[-(max_turns * 2):]

    lines = []
    for msg in recent:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        if content:
            lines.append(f"{role}: {content}")

    return "\n".join(lines) if lines else "(No prior conversation)"


# ═══════════════════════════════════════════════════════════════════
# Node 1: Intent classification
# ═══════════════════════════════════════════════════════════════════

def classify_intent(state: AgentState) -> dict[str, Any]:
    """Classify the user's intent."""
    llm = get_llm(streaming=False)
    user_msg = state["user_query"]

    # Check if this is a short answer to a previous clarification
    history = state.get("messages", [])
    if state.get("needs_clarification") and len(user_msg.split()) <= 8:
        return {"intent": "clarification_response"}

    response = llm.invoke([
        SystemMessage(content=INTENT_SYSTEM),
        HumanMessage(content=INTENT_HUMAN.format(message=user_msg)),
    ])

    intent = response.content.strip().lower().replace(" ", "_")
    valid_intents = {"query_generation", "documentation", "clarification_response", "general"}
    if intent not in valid_intents:
        intent = "query_generation"  # default assumption

    logger.info(f"Intent classified as: {intent}")
    return {"intent": intent}


# ═══════════════════════════════════════════════════════════════════
# Node 2: Dual retrieval (schema + examples)
# ═══════════════════════════════════════════════════════════════════

def retrieve_context(state: AgentState) -> dict[str, Any]:
    """Run both retrievers in parallel and format results."""
    query = state["user_query"]

    # If this is a clarification response, merge with pending context
    if state.get("intent") == "clarification_response" and state.get("pending_context"):
        query = f"{state['pending_context']} — {query}"

    schema_ret = _get_schema_retriever()
    example_ret = _get_example_retriever()

    schema_fields = schema_ret.retrieve(query, n_results=10)
    examples = example_ret.retrieve(query, n_results=5)

    schema_context = schema_ret.format_for_prompt(schema_fields)
    example_context = example_ret.format_for_prompt(examples)

    return {
        "schema_context": schema_context,
        "example_context": example_context,
        "schema_fields": [
            {
                "field_name": f.field_name,
                "nested_path": f.nested_path,
                "field_type": f.field_type,
                "valid_values": f.valid_values,
            }
            for f in schema_fields
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# Node 3: Check if clarification is needed
# ═══════════════════════════════════════════════════════════════════

def check_clarity(state: AgentState) -> dict[str, Any]:
    """Determine if the query is clear enough to generate."""
    query = state["user_query"]
    schema_context = state.get("schema_context", "")

    # Heuristic checks for common ambiguities
    needs_clarification = False
    lower = query.lower()

    # Check if staging fields are mentioned without disease phase
    staging_terms = ["stage", "staging", "irs group", "tnm", "m0", "m1"]
    phase_terms = ["initial diagnosis", "relapse", "diagnosis", "progression"]

    has_staging = any(t in lower for t in staging_terms)
    has_phase = any(t in lower for t in phase_terms)

    if has_staging and not has_phase:
        needs_clarification = True

    if not needs_clarification:
        return {"needs_clarification": False}

    # Ask LLM what to clarify
    llm_json = get_llm_json(streaming=False)
    response = llm_json.invoke([
        SystemMessage(content=CLARIFICATION_SYSTEM),
        HumanMessage(content=CLARIFICATION_HUMAN.format(
            user_query=query,
            schema_context=schema_context,
        )),
    ])

    try:
        parsed = json.loads(response.content)
        question = parsed.get("question", "Can you clarify your query?")
        options = parsed.get("options", [])
    except (json.JSONDecodeError, AttributeError):
        question = "Can you clarify your query?"
        options = []

    return {
        "needs_clarification": True,
        "clarification_question": question,
        "clarification_options": options,
        "pending_context": query,  # stash for when user responds
        "event_type": "clarification",
        "response_text": question,
    }


# ═══════════════════════════════════════════════════════════════════
# Node 4: Generate GQL filter
# ═══════════════════════════════════════════════════════════════════

def generate_filter(state: AgentState) -> dict[str, Any]:
    """Call the LLM to generate a GQL filter JSON."""
    query = state["user_query"]
    if state.get("intent") == "clarification_response" and state.get("pending_context"):
        query = f"{state['pending_context']} — {query}"

    schema_context = state.get("schema_context", "")
    example_context = state.get("example_context", "")
    conversation_history = _build_conversation_history(state.get("messages", []))

    llm_json = get_llm_json(streaming=False)

    prompt_text = QUERY_GEN_HUMAN.format(
        schema_context=schema_context,
        example_context=example_context,
        user_query=query,
        conversation_history=conversation_history,
    )

    response = llm_json.invoke([
        SystemMessage(content=QUERY_GEN_SYSTEM),
        HumanMessage(content=prompt_text),
    ])

    raw_json = response.content.strip()

    # Strip markdown fences if present
    if raw_json.startswith("```"):
        lines = raw_json.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_json = "\n".join(lines).strip()

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON: {e}")
        return {
            "generated_json": raw_json,
            "generated_filter": {},
            "is_valid": False,
            "validation_errors": [f"Invalid JSON from LLM: {e}"],
            "generation_attempts": state.get("generation_attempts", 0) + 1,
        }

    return {
        "generated_json": raw_json,
        "generated_filter": parsed,
        "generation_attempts": state.get("generation_attempts", 0) + 1,
    }


# ═══════════════════════════════════════════════════════════════════
# Node 5: Validate the generated filter
# ═══════════════════════════════════════════════════════════════════

def validate_filter(state: AgentState) -> dict[str, Any]:
    """Validate the generated filter against the schema."""
    gql_filter = state.get("generated_filter", {})

    if not gql_filter:
        return {
            "is_valid": False,
            "validation_errors": ["Empty filter generated"],
            "fields_used": [],
        }

    validator = get_validator()
    result = validator.validate(gql_filter)

    return {
        "is_valid": result.is_valid,
        "validation_errors": result.errors,
        "validation_warnings": result.warnings,
        "fields_used": list(set(result.fields_used)),
    }


# ═══════════════════════════════════════════════════════════════════
# Node 6: Self-healing — fix validation errors
# ═══════════════════════════════════════════════════════════════════

def fix_filter(state: AgentState) -> dict[str, Any]:
    """Ask the LLM to fix validation errors."""
    llm_json = get_llm_json(streaming=False)

    errors_str = "\n".join(f"- {e}" for e in state.get("validation_errors", []))
    original = state.get("generated_json", "{}")
    schema_context = state.get("schema_context", "")

    response = llm_json.invoke([
        SystemMessage(content=VALIDATION_FIX_SYSTEM),
        HumanMessage(content=VALIDATION_FIX_HUMAN.format(
            original_json=original,
            errors=errors_str,
            schema_context=schema_context,
        )),
    ])

    raw_json = response.content.strip()
    if raw_json.startswith("```"):
        lines = raw_json.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_json = "\n".join(lines).strip()

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return {
            "generated_json": raw_json,
            "generated_filter": {},
            "is_valid": False,
            "validation_errors": [f"Fix attempt produced invalid JSON: {e}"],
        }

    return {
        "generated_json": raw_json,
        "generated_filter": parsed,
    }


# ═══════════════════════════════════════════════════════════════════
# Node 7: Generate NL explanation
# ═══════════════════════════════════════════════════════════════════

def explain_filter(state: AgentState) -> dict[str, Any]:
    """Generate a plain-English explanation of the filter."""
    gql_filter = state.get("generated_filter", {})
    if not gql_filter:
        return {"response_text": "I generated a filter but it appears to be empty."}

    llm = get_llm(streaming=False)
    filter_str = json.dumps(gql_filter, indent=2)

    response = llm.invoke([
        SystemMessage(content=EXPLANATION_SYSTEM),
        HumanMessage(content=EXPLANATION_HUMAN.format(filter_json=filter_str)),
    ])

    return {
        "response_text": response.content.strip(),
        "filter_result": gql_filter,
        "event_type": "filter_json",
    }


# ═══════════════════════════════════════════════════════════════════
# Node 8: General response (non-query)
# ═══════════════════════════════════════════════════════════════════

def general_response(state: AgentState) -> dict[str, Any]:
    """Handle general / documentation queries."""
    llm = get_llm(streaming=False)
    response = llm.invoke([
        SystemMessage(content=GENERAL_SYSTEM),
        HumanMessage(content=GENERAL_HUMAN.format(message=state["user_query"])),
    ])

    return {
        "response_text": response.content.strip(),
        "event_type": "token",
        "filter_result": None,
    }
