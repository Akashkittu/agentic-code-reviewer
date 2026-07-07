from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.planner import planner_node
from app.state import CodeReviewState
from app.tool_executor import tool_executor_node
from app.tools.report_generator import report_generator_tool
from app.tools.repo_loader import repo_loader_tool


def route_after_repo_loader(state: CodeReviewState) -> str:
    tool_results = state.get("tool_results", [])

    if not tool_results:
        return "stop"

    latest_result = tool_results[-1]

    if (
        latest_result.tool_name == "repo_loader_tool"
        and latest_result.status == "failed"
    ):
        return "stop"

    return "continue"


def route_after_planner(state: CodeReviewState) -> str:
    decision = state.get("tool_decision")

    if decision is None:
        return "report"

    if isinstance(decision, dict):
        next_tool = decision.get("next_tool")
    else:
        next_tool = decision.next_tool

    if next_tool == "report_generator_tool":
        return "report"

    return "execute"


def build_code_review_graph():
    graph = StateGraph(CodeReviewState)

    graph.add_node("repo_loader", repo_loader_tool)
    graph.add_node("planner", planner_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("report_generator", report_generator_tool)

    graph.add_edge(START, "repo_loader")

    graph.add_conditional_edges(
        "repo_loader",
        route_after_repo_loader,
        {
            "continue": "planner",
            "stop": END,
        },
    )

    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "execute": "tool_executor",
            "report": "report_generator",
        },
    )

    graph.add_edge("tool_executor", "planner")
    graph.add_edge("report_generator", END)

    return graph.compile()


def run_code_review_graph(initial_state: CodeReviewState) -> CodeReviewState:
    app = build_code_review_graph()
    final_state = app.invoke(initial_state)
    return final_state