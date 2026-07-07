from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.state import CodeReviewState
from app.tools.code_search import code_search_tool
from app.tools.dependency_check import dependency_check_tool
from app.tools.env_config_check import env_config_check_tool
from app.tools.llm_review import llm_review_tool
from app.tools.readme_review import readme_review_tool
from app.tools.report_generator import report_generator_tool
from app.tools.repo_loader import repo_loader_tool
from app.tools.repo_structure import repo_structure_tool
from app.tools.security_scan import security_scan_tool
from app.tools.test_discovery import test_discovery_tool


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


def build_code_review_graph():
    graph = StateGraph(CodeReviewState)

    graph.add_node("repo_loader", repo_loader_tool)
    graph.add_node("repo_structure", repo_structure_tool)
    graph.add_node("dependency_check", dependency_check_tool)
    graph.add_node("env_config_check", env_config_check_tool)
    graph.add_node("security_scan", security_scan_tool)
    graph.add_node("code_search", code_search_tool)
    graph.add_node("test_discovery", test_discovery_tool)
    graph.add_node("readme_review", readme_review_tool)
    graph.add_node("llm_review", llm_review_tool)
    graph.add_node("report_generator", report_generator_tool)

    graph.add_edge(START, "repo_loader")

    graph.add_conditional_edges(
        "repo_loader",
        route_after_repo_loader,
        {
            "continue": "repo_structure",
            "stop": END,
        },
    )

    graph.add_edge("repo_structure", "dependency_check")
    graph.add_edge("dependency_check", "env_config_check")
    graph.add_edge("env_config_check", "security_scan")
    graph.add_edge("security_scan", "code_search")
    graph.add_edge("code_search", "test_discovery")
    graph.add_edge("test_discovery", "readme_review")
    graph.add_edge("readme_review", "llm_review")
    graph.add_edge("llm_review", "report_generator")
    graph.add_edge("report_generator", END)

    return graph.compile()


def run_code_review_graph(initial_state: CodeReviewState) -> CodeReviewState:
    app = build_code_review_graph()
    final_state = app.invoke(initial_state)
    return final_state