from typing import Any, TypedDict

from app.schemas import Finding, ReviewReport, ToolDecision, ToolResult


class CodeReviewState(TypedDict, total=False):
    repo_path: str
    repo_url: str | None

    repo_files: list[str]
    repo_type: str
    important_files: list[str]

    current_iteration: int
    max_iterations: int

    llm_status: str
    llm_error: str | None
    fallback_mode: bool

    tool_decision: ToolDecision | None
    tool_results: list[ToolResult]
    findings: list[Finding]

    skipped_tools: list[str]
    not_applicable_tools: list[str]

    final_report: ReviewReport | None
    logs: list[str]
    metadata: dict[str, Any]