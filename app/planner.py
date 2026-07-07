from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.llm.fallback_manager import FallbackLLMManager
from app.schemas import ToolDecision
from app.state import CodeReviewState
from app.tools.tool_registry import (
    get_next_deterministic_tool,
    get_remaining_tool_names,
)


def _append_log(state: CodeReviewState, message: str) -> None:
    state.setdefault("logs", [])
    state["logs"].append(message)


def _severity_summary(state: CodeReviewState) -> dict[str, int]:
    summary = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }

    for finding in state.get("findings", []):
        summary[finding.severity] = summary.get(finding.severity, 0) + 1

    return summary


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)

    if not match:
        raise ValueError("No JSON object found in LLM planner response.")

    return json.loads(match.group(0))


def _build_planner_prompt(
    state: CodeReviewState,
    valid_choices: list[str],
    remaining_tools: list[str],
) -> str:
    executed_tools = [
        result.tool_name
        for result in state.get("tool_results", [])
    ]

    severity_summary = _severity_summary(state)

    return f"""
You are the planner inside an agentic code review workflow.

You do not execute code directly.
You only choose the next tool from the allowed tool list.

Repo type:
{state.get("repo_type", "unknown")}

Executed tools:
{executed_tools}

Remaining useful tools:
{remaining_tools}

Current finding count:
{len(state.get("findings", []))}

Severity summary:
{severity_summary}

Valid next_tool choices:
{valid_choices}

Tool meaning:
- repo_structure_tool: detect language, framework, main files, folders
- dependency_check_tool: check requirements.txt, pyproject.toml, package.json
- env_config_check_tool: check .env safety and hardcoded secrets
- security_scan_tool: detect eval, exec, os.system, shell=True, unsafe patterns
- code_search_tool: detect TODO, FIXME, print, breakpoint, bare except
- test_discovery_tool: detect tests, test folders, test frameworks
- readme_review_tool: check README quality, setup, run command, limitation section
- llm_review_tool: use LLM fallback chain for senior reviewer summary
- report_generator_tool: finish and generate final JSON/Markdown report

Return JSON only in this exact format:
{{
  "next_tool": "one_valid_tool_name",
  "reason": "short reason"
}}

Rules:
- Choose only from Valid next_tool choices.
- Prefer remaining useful tools before report_generator_tool.
- Choose report_generator_tool only when enough review evidence is collected or no useful tools remain.
- Do not invent tool names.
"""


def _fallback_decision(state: CodeReviewState, reason: str) -> ToolDecision:
    next_tool = get_next_deterministic_tool(state)

    return ToolDecision(
        next_tool=next_tool,
        reason=reason,
    )


def _record_planner_decision(
    state: CodeReviewState,
    decision: ToolDecision,
    source: str,
) -> None:
    state.setdefault("metadata", {})
    state["metadata"].setdefault("planner_decisions", [])

    state["metadata"]["planner_decisions"].append(
        {
            "iteration": state.get("current_iteration", 0),
            "next_tool": decision.next_tool,
            "reason": decision.reason,
            "source": source,
        }
    )


def planner_node(state: CodeReviewState) -> CodeReviewState:
    """
    Agentic planner node.

    It chooses the next tool.
    LLM can propose a tool, but the choice is validated by Pydantic
    and checked against the currently valid choices.
    """

    _append_log(state, "Running planner_node...")

    current_iteration = state.get("current_iteration", 0)
    max_iterations = state.get("max_iterations", 8)

    remaining_tools = get_remaining_tool_names(state)

    if not remaining_tools:
        decision = ToolDecision(
            next_tool="report_generator_tool",
            reason="All useful review tools have already run.",
        )
        state["tool_decision"] = decision
        _record_planner_decision(state, decision, source="rule")
        return state

    if current_iteration >= max_iterations:
        decision = ToolDecision(
            next_tool="report_generator_tool",
            reason="Maximum planner iterations reached.",
        )
        state["tool_decision"] = decision
        _record_planner_decision(state, decision, source="rule")
        return state

    valid_choices = remaining_tools + ["report_generator_tool"]

    try:
        prompt = _build_planner_prompt(
            state=state,
            valid_choices=valid_choices,
            remaining_tools=remaining_tools,
        )

        llm_result = FallbackLLMManager().generate(prompt)

        if not llm_result.success:
            decision = _fallback_decision(
                state,
                reason="LLM planner unavailable, using deterministic planner.",
            )
            source = "deterministic_fallback"

        else:
            raw_json = _extract_json_object(llm_result.text)
            decision = ToolDecision(**raw_json)

            if decision.next_tool not in valid_choices:
                decision = _fallback_decision(
                    state,
                    reason=(
                        "LLM selected a tool outside current valid choices, "
                        "using deterministic planner."
                    ),
                )
                source = "validated_fallback"

            elif (
                decision.next_tool == "report_generator_tool"
                and remaining_tools
                and current_iteration < max_iterations
            ):
                decision = _fallback_decision(
                    state,
                    reason=(
                        "LLM requested report early, but useful tools remain. "
                        "Continuing with the next deterministic tool."
                    ),
                )
                source = "guardrail_fallback"

            else:
                source = f"llm:{llm_result.provider}"

    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        decision = _fallback_decision(
            state,
            reason=f"Planner response validation failed: {exc}",
        )
        source = "validation_fallback"

    except Exception as exc:
        decision = _fallback_decision(
            state,
            reason=f"Planner crashed: {exc}",
        )
        source = "exception_fallback"

    state["tool_decision"] = decision

    if decision.next_tool != "report_generator_tool":
        state["current_iteration"] = current_iteration + 1

    _record_planner_decision(state, decision, source=source)

    _append_log(
        state,
        f"planner_node selected {decision.next_tool}: {decision.reason}",
    )

    return state