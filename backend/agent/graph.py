"""
LangGraph agent graph — orchestrates the full pipeline.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.nodes import (
    classify_intent,
    retrieve_context,
    check_clarity,
    generate_filter,
    validate_filter,
    fix_filter,
    explain_filter,
    general_response,
    documentation_response,
    reverse_explain_filter,
    compare_filters_node,
)

MAX_RETRIES = 3


# ── Routing functions ────────────────────────────────────────────

def route_after_intent(state: AgentState) -> str:
    """Route based on classified intent."""
    intent = state.get("intent", "general")
    if intent in ("query_generation", "clarification_response"):
        return "retrieve_context"
    if intent == "documentation":
        return "documentation_response"
    if intent == "explain_filter":
        return "reverse_explain_filter"
    if intent == "compare_filters":
        return "compare_filters"
    return "general_response"


def route_after_clarity(state: AgentState) -> str:
    """Route after clarity check."""
    if state.get("needs_clarification"):
        return END  # respond with clarification question
    return "generate_filter"


def route_after_validation(state: AgentState) -> str:
    """Route after validation — pass, fix, or give up."""
    if state.get("is_valid"):
        return "explain_filter"
    attempts = state.get("generation_attempts", 0)
    if attempts < MAX_RETRIES:
        return "fix_filter"
    # Max retries — return what we have with errors
    return "explain_filter"


# ── Build the graph ──────────────────────────────────────────────

def build_agent_graph() -> StateGraph:
    """Construct and compile the LangGraph agent."""

    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("check_clarity", check_clarity)
    builder.add_node("generate_filter", generate_filter)
    builder.add_node("validate_filter", validate_filter)
    builder.add_node("fix_filter", fix_filter)
    builder.add_node("explain_filter", explain_filter)
    builder.add_node("general_response", general_response)
    builder.add_node("documentation_response", documentation_response)
    builder.add_node("reverse_explain_filter", reverse_explain_filter)
    builder.add_node("compare_filters", compare_filters_node)

    # Entry point
    builder.set_entry_point("classify_intent")

    # Edges
    builder.add_conditional_edges("classify_intent", route_after_intent)
    builder.add_edge("retrieve_context", "check_clarity")
    builder.add_conditional_edges("check_clarity", route_after_clarity)
    builder.add_edge("generate_filter", "validate_filter")
    builder.add_conditional_edges("validate_filter", route_after_validation)
    builder.add_edge("fix_filter", "validate_filter")  # re-validate after fix
    builder.add_edge("explain_filter", END)
    builder.add_edge("general_response", END)
    builder.add_edge("documentation_response", END)
    builder.add_edge("reverse_explain_filter", END)
    builder.add_edge("compare_filters", END)

    return builder.compile()


# Module-level compiled graph (singleton)
agent_graph = build_agent_graph()
