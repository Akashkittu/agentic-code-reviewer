from __future__ import annotations

from app.schemas import Finding, ToolDecision, ToolResult
from app.state import CodeReviewState
from app.tools.tool_registry import TOOL_REGISTRY


def _append_log(state: CodeReviewState, message: str) -> None:
    state.setdefault("logs", [])
    state["logs"].append(message)


def _append_tool_result(state: CodeReviewState, result: ToolResult) -> None:
    state.setdefault("tool_results", [])
    state["tool_results"].append(result)


def _get_decision(state: CodeReviewState) -> ToolDecision | None:
    decision = state.get("tool_decision")

    if decision is None:
        return None

    if isinstance(decision, ToolDecision):
        return decision

    if isinstance(decision, dict):
        return ToolDecision(**decision)

    return None


def tool_executor_node(state: CodeReviewState) -> CodeReviewState:
    """
    Executes only tools present in TOOL_REGISTRY.

    The LLM never calls a function directly.
    It only selected a tool name.
    This executor checks the registry and runs the mapped safe function.
    """

    decision = _get_decision(state)

    if decision is None:
        finding = Finding(
            category="agentic_planning",
            severity="high",
            importance_percent=80,
            file=None,
            line=None,
            issue="Tool executor did not receive a valid planner decision.",
            why_it_matters="Without a valid decision, the workflow cannot safely choose the next review action.",
            suggested_fix="Check planner_node output and ToolDecision validation.",
            source_tool="tool_executor_node",
        )

        result = ToolResult(
            tool_name="tool_executor_node",
            status="failed",
            summary="No valid tool decision found.",
            findings=[finding],
            raw_data={},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state

    tool_name = decision.next_tool

    if tool_name == "report_generator_tool":
        return state

    tool_func = TOOL_REGISTRY.get(tool_name)

    if tool_func is None:
        finding = Finding(
            category="agentic_planning",
            severity="medium",
            importance_percent=70,
            file=None,
            line=None,
            issue=f"Planner selected an unavailable tool: {tool_name}.",
            why_it_matters="The agent must only execute tools that are implemented and registered.",
            suggested_fix="Add the tool to TOOL_REGISTRY or restrict planner choices.",
            source_tool="tool_executor_node",
        )

        result = ToolResult(
            tool_name="tool_executor_node",
            status="skipped",
            summary=f"Unavailable tool skipped: {tool_name}.",
            findings=[finding],
            raw_data={"selected_tool": tool_name},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)
        state.setdefault("skipped_tools", [])
        state["skipped_tools"].append(tool_name)

        return state

    _append_log(
        state,
        f"tool_executor_node running {tool_name}. Reason: {decision.reason}",
    )

    return tool_func(state)