"""
workflow.py — LangGraph state machine for the fraud investigation agent.

Graph topology:
  trigger → investigate → assess_uncertainty
                              ↓ (should_stop=True)
                             act → explain → write_to_graph → END
                              ↑ (should_stop=False, loop back)
                         investigate ←──────────────────────┘
"""

from langgraph.graph import StateGraph, END
from agent.state import InvestigationState
from agent.nodes import (
    node_trigger,
    node_investigate,
    node_assess_uncertainty,
    node_act,
    node_explain,
    node_write_to_graph,
)


def should_continue(state: InvestigationState) -> str:
    """Routing function: after assess_uncertainty, decide to loop or proceed."""
    if state.get("should_stop", False):
        return "act"
    return "investigate"


def build_graph() -> StateGraph:
    graph = StateGraph(InvestigationState)

    graph.add_node("trigger", node_trigger)
    graph.add_node("investigate", node_investigate)
    graph.add_node("assess_uncertainty", node_assess_uncertainty)
    graph.add_node("act", node_act)
    graph.add_node("explain", node_explain)
    graph.add_node("write_to_graph", node_write_to_graph)

    graph.set_entry_point("trigger")
    graph.add_edge("trigger", "investigate")
    graph.add_edge("investigate", "assess_uncertainty")
    graph.add_conditional_edges(
        "assess_uncertainty",
        should_continue,
        {"investigate": "investigate", "act": "act"},
    )
    graph.add_edge("act", "explain")
    graph.add_edge("explain", "write_to_graph")
    graph.add_edge("write_to_graph", END)

    return graph.compile()


# Compile once at import time
investigation_graph = build_graph()
