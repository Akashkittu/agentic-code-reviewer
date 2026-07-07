from __future__ import annotations

from collections.abc import Callable

from app.state import CodeReviewState
from app.tools.code_search import code_search_tool
from app.tools.dependency_check import dependency_check_tool
from app.tools.env_config_check import env_config_check_tool
from app.tools.llm_review import llm_review_tool
from app.tools.readme_review import readme_review_tool
from app.tools.repo_structure import repo_structure_tool
from app.tools.security_scan import security_scan_tool
from app.tools.test_discovery import test_discovery_tool


ToolFunction = Callable[[CodeReviewState], CodeReviewState]


TOOL_REGISTRY: dict[str, ToolFunction] = {
    "repo_structure_tool": repo_structure_tool,
    "dependency_check_tool": dependency_check_tool,
    "env_config_check_tool": env_config_check_tool,
    "security_scan_tool": security_scan_tool,
    "code_search_tool": code_search_tool,
    "test_discovery_tool": test_discovery_tool,
    "readme_review_tool": readme_review_tool,
    "llm_review_tool": llm_review_tool,
}


DEFAULT_PLANNER_TOOL_ORDER = [
    "repo_structure_tool",
    "dependency_check_tool",
    "env_config_check_tool",
    "security_scan_tool",
    "code_search_tool",
    "test_discovery_tool",
    "readme_review_tool",
    "llm_review_tool",
]


def get_executed_tool_names(state: CodeReviewState) -> set[str]:
    return {
        result.tool_name
        for result in state.get("tool_results", [])
    }


def get_remaining_tool_names(state: CodeReviewState) -> list[str]:
    executed = get_executed_tool_names(state)

    return [
        tool_name
        for tool_name in DEFAULT_PLANNER_TOOL_ORDER
        if tool_name not in executed
    ]


def get_next_deterministic_tool(state: CodeReviewState) -> str:
    remaining_tools = get_remaining_tool_names(state)

    if remaining_tools:
        return remaining_tools[0]

    return "report_generator_tool"