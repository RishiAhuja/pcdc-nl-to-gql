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
    DOCS_SYSTEM,
    DOCS_HUMAN,
    REVERSE_EXPLAIN_SYSTEM,
    REVERSE_EXPLAIN_HUMAN,
    COMPARISON_SYSTEM,
    COMPARISON_HUMAN,
)
from retrieval.schema_retriever import SchemaRetriever
from retrieval.example_retriever import ExampleRetriever
from retrieval.docs_retriever import DocsRetriever
from validation.validator import get_validator

logger = logging.getLogger(__name__)

# Lazy singletons — initialised on first use
_schema_retriever: SchemaRetriever | None = None
_example_retriever: ExampleRetriever | None = None
_docs_retriever: DocsRetriever | None = None


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


def _get_docs_retriever() -> DocsRetriever:
    global _docs_retriever
    if _docs_retriever is None:
        _docs_retriever = DocsRetriever()
    return _docs_retriever


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

    # Heuristic: detect pasted JSON filter (F5 — reverse explanation)
    stripped = user_msg.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            # Check if it looks like a Guppy filter (has AND/OR/IN/nested keys)
            flat = json.dumps(parsed).lower()
            if any(k in flat for k in ['"and"', '"or"', '"in"', '"nested"', '"gte"', '"lte"']):
                return {"intent": "explain_filter", "pasted_filter": parsed}
        except json.JSONDecodeError:
            pass

    response = llm.invoke([
        SystemMessage(content=INTENT_SYSTEM),
        HumanMessage(content=INTENT_HUMAN.format(message=user_msg)),
    ])

    intent = response.content.strip().lower().replace(" ", "_")
    valid_intents = {"query_generation", "documentation", "clarification_response",
                     "general", "explain_filter", "compare_filters"}
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
    """Handle general conversation queries."""
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


# ═══════════════════════════════════════════════════════════════════
# Node 9: Documentation browser (data dictionary RAG)
# ═══════════════════════════════════════════════════════════════════

def documentation_response(state: AgentState) -> dict[str, Any]:
    """Answer documentation questions using the PCDC data dictionary.

    Retrieves the top-5 most relevant entries from the data-dictionary
    ChromaDB collection and injects them into a documentation-specific
    prompt so the LLM answers from authoritative sources, not guesses.
    """
    query = state["user_query"]
    docs_ret = _get_docs_retriever()

    # Retrieve relevant data dictionary entries
    entries = docs_ret.retrieve(query, n_results=5)
    docs_context = docs_ret.format_for_prompt(entries)

    llm = get_llm(streaming=False)
    response = llm.invoke([
        SystemMessage(content=DOCS_SYSTEM),
        HumanMessage(content=DOCS_HUMAN.format(
            docs_context=docs_context,
            message=query,
        )),
    ])

    return {
        "response_text": response.content.strip(),
        "event_type": "token",
        "filter_result": None,
    }


# ═══════════════════════════════════════════════════════════════════
# Node: Reverse Explanation (F5) — explain a pasted filter
# ═══════════════════════════════════════════════════════════════════

def reverse_explain_filter(state: AgentState) -> dict[str, Any]:
    """Take a pasted Guppy filter JSON and explain it in plain English."""
    pasted = state.get("pasted_filter")
    user_msg = state["user_query"]

    # If no pre-parsed filter, try extracting from the message text
    if not pasted:
        stripped = user_msg.strip()
        # Try to find JSON in the message
        start = stripped.find("{")
        end = stripped.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                pasted = json.loads(stripped[start:end])
            except json.JSONDecodeError:
                return {
                    "response_text": "I couldn't parse the filter JSON you provided. "
                                     "Please paste a valid Guppy filter JSON object.",
                    "event_type": "token",
                    "filter_result": None,
                }

    if not pasted:
        return {
            "response_text": "Please paste a Guppy filter JSON object and I'll explain what it does.",
            "event_type": "token",
            "filter_result": None,
        }

    # Validate the pasted filter
    validator = get_validator()
    result = validator.validate(pasted)

    validation_notes = ""
    if result.errors:
        validation_notes = "⚠️ Validation issues found:\n" + "\n".join(f"- {e}" for e in result.errors)
    elif result.warnings:
        validation_notes = "Note: " + "; ".join(result.warnings)

    filter_str = json.dumps(pasted, indent=2)

    llm = get_llm(streaming=False)
    response = llm.invoke([
        SystemMessage(content=REVERSE_EXPLAIN_SYSTEM),
        HumanMessage(content=REVERSE_EXPLAIN_HUMAN.format(
            filter_json=filter_str,
            validation_notes=validation_notes,
        )),
    ])

    return {
        "response_text": response.content.strip(),
        "filter_result": pasted,  # echo the filter back so frontend can display it
        "event_type": "filter_json",
        "is_valid": result.is_valid,
        "validation_errors": result.errors,
        "validation_warnings": result.warnings,
        "fields_used": list(set(result.fields_used)),
    }


# ═══════════════════════════════════════════════════════════════════
# Node: Cohort Comparison (F2) — compare two filters
# ═══════════════════════════════════════════════════════════════════

def compare_filters_node(state: AgentState) -> dict[str, Any]:
    """Compare two filter sets from conversation history or user input."""
    from utils.filter_utils import diff_filters, format_diff_summary

    user_msg = state["user_query"]
    history = state.get("messages", [])

    # Extract two most recent filters from conversation history
    filters_found: list[dict[str, Any]] = []
    for msg in reversed(history):
        filter_str = msg.get("_filter")
        if filter_str:
            try:
                filters_found.append(json.loads(filter_str))
            except (json.JSONDecodeError, TypeError):
                pass
        if len(filters_found) >= 2:
            break

    if len(filters_found) < 2:
        return {
            "response_text": "I need at least two generated filters in the conversation to compare. "
                             "Please generate two different cohort queries first, then ask me to compare them.",
            "event_type": "token",
            "filter_result": None,
        }

    # filters_found is in reverse order (most recent first)
    filter_a = filters_found[1]  # older
    filter_b = filters_found[0]  # newer

    diffs = diff_filters(filter_a, filter_b)
    diff_summary = format_diff_summary(diffs)

    llm = get_llm(streaming=False)
    response = llm.invoke([
        SystemMessage(content=COMPARISON_SYSTEM),
        HumanMessage(content=COMPARISON_HUMAN.format(
            name_a="Cohort A (earlier)",
            name_b="Cohort B (later)",
            filter_a=json.dumps(filter_a, indent=2),
            filter_b=json.dumps(filter_b, indent=2),
            diff_summary=diff_summary,
        )),
    ])

    comparison = {
        "diffs": diffs,
        "summary": response.content.strip(),
        "filter_a": filter_a,
        "filter_b": filter_b,
    }

    return {
        "response_text": response.content.strip(),
        "comparison_result": comparison,
        "event_type": "comparison",
        "filter_result": None,
    }
