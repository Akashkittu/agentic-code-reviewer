from __future__ import annotations

import json
from pathlib import Path

from app.schemas import Finding, ReviewReport, ToolResult
from app.state import CodeReviewState


SEVERITY_PENALTY = {
    "critical": 20,
    "high": 12,
    "medium": 7,
    "low": 3,
    "info": 1,
}


SEVERITY_RANK = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}


def _append_log(state: CodeReviewState, message: str) -> None:
    state.setdefault("logs", [])
    state["logs"].append(message)


def _append_tool_result(state: CodeReviewState, result: ToolResult) -> None:
    state.setdefault("tool_results", [])
    state["tool_results"].append(result)


def _sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda finding: (
            SEVERITY_RANK.get(finding.severity, 0),
            finding.importance_percent,
        ),
        reverse=True,
    )


def _calculate_score(findings: list[Finding]) -> int:
    score = 100

    for finding in findings:
        penalty = SEVERITY_PENALTY.get(finding.severity, 0)

        if finding.importance_percent >= 90:
            penalty += 2

        score -= penalty

    return max(0, min(100, score))


def _count_by_severity(findings: list[Finding]) -> dict[str, int]:
    counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }

    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1

    return counts


def _build_project_summary(state: CodeReviewState, findings: list[Finding]) -> str:
    repo_type = state.get("repo_type", "unknown")
    file_count = len(state.get("repo_files", []))
    tools_count = len(state.get("tool_results", []))

    severity_counts = _count_by_severity(findings)

    return (
        f"This repository was detected as a {repo_type}. "
        f"The agent reviewed {file_count} readable files using {tools_count} tools. "
        f"It found {len(findings)} total finding(s): "
        f"{severity_counts['critical']} critical, "
        f"{severity_counts['high']} high, "
        f"{severity_counts['medium']} medium, "
        f"{severity_counts['low']} low, and "
        f"{severity_counts['info']} info."
    )


def _build_limitations(state: CodeReviewState) -> list[str]:
    limitations: list[str] = []

    if state.get("llm_status") in {"not_used", "failed"}:
        limitations.append(
            "This report is generated from static deterministic tools only. "
            "LLM-based reasoning will be added in the LangGraph step."
        )

    limitations.append(
        "The current prototype detects risky patterns using simple static rules, "
        "so it may miss deeper logical bugs."
    )

    limitations.append(
        "The current version does not execute the target application or run tests automatically."
    )

    return limitations


def _build_final_recommendation(score: int, findings: list[Finding]) -> str:
    critical_count = sum(1 for finding in findings if finding.severity == "critical")
    high_count = sum(1 for finding in findings if finding.severity == "high")

    if critical_count > 0:
        return (
            "Fix critical issues first, especially secrets or dangerous code execution patterns. "
            "After that, improve documentation and add tests before considering the repo production-ready."
        )

    if high_count > 0:
        return (
            "The repo is reviewable, but high-priority issues should be fixed before delivery. "
            "Focus on dependency setup, tests, README instructions, and security-sensitive code."
        )

    if score >= 85:
        return (
            "The repo looks healthy overall. Next improvement should be deeper LLM-assisted reasoning "
            "and optional test execution."
        )

    return (
        "The repo needs cleanup before final submission. Improve setup, tests, documentation, "
        "and code quality based on the findings."
    )


def _finding_to_markdown(finding: Finding, index: int) -> str:
    location = "N/A"

    if finding.file:
        location = finding.file
        if finding.line:
            location += f":{finding.line}"

    return f"""### {index}. [{finding.severity.upper()}] {finding.issue}

- **Category:** {finding.category}
- **Importance:** {finding.importance_percent}%
- **Location:** {location}
- **Why it matters:** {finding.why_it_matters}
- **Suggested fix:** {finding.suggested_fix}
- **Source tool:** {finding.source_tool or "N/A"}
"""


def _write_reports(report: ReviewReport, state: CodeReviewState) -> dict[str, str]:
    output_dir = Path("review_outputs")
    output_dir.mkdir(exist_ok=True)

    json_path = output_dir / "latest_report.json"
    markdown_path = output_dir / "latest_report.md"

    json_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )

    severity_counts = _count_by_severity(report.findings)

    metadata = state.get("metadata", {})
    languages = metadata.get("languages", [])
    frameworks = metadata.get("frameworks", [])
    main_files = metadata.get("main_files", [])

    llm_review = metadata.get("llm_review", {})
    llm_provider = llm_review.get("provider", "N/A")
    llm_attempted = llm_review.get("attempted_providers", [])
    llm_text = llm_review.get("text", "No LLM review generated.")

    findings_markdown = "\n".join(
        _finding_to_markdown(finding, index)
        for index, finding in enumerate(report.findings, start=1)
    )

    if not findings_markdown:
        findings_markdown = "No findings were detected."

    skipped_tools = "\n".join(f"- {tool}" for tool in report.skipped_tools) or "- None"
    not_applicable_tools = "\n".join(f"- {tool}" for tool in report.not_applicable_tools) or "- None"
    limitations = "\n".join(f"- {item}" for item in report.limitations) or "- None"

    markdown = f"""# Agentic Code Review Report

## Project Summary

{report.project_summary}

## Repo Metadata

- **Repo type:** {report.repo_type}
- **Overall score:** {report.overall_score}/100
- **LLM status:** {report.llm_status}
- **Fallback mode:** {report.fallback_mode}
- **Languages:** {", ".join(languages) if languages else "None detected"}
- **Frameworks:** {", ".join(frameworks) if frameworks else "None detected"}
- **Main files:** {", ".join(main_files) if main_files else "None detected"}

## Severity Summary

- **Critical:** {severity_counts["critical"]}
- **High:** {severity_counts["high"]}
- **Medium:** {severity_counts["medium"]}
- **Low:** {severity_counts["low"]}
- **Info:** {severity_counts["info"]}

## LLM Review

- **Provider used:** {llm_provider}
- **Attempted providers:** {", ".join(llm_attempted) if llm_attempted else "None"}

{llm_text}

## Findings

{findings_markdown}

## Skipped Tools

{skipped_tools}

## Not Applicable Tools

{not_applicable_tools}

## Limitations

{limitations}

## Final Recommendation

{report.final_recommendation}
"""

    markdown_path.write_text(markdown, encoding="utf-8")

    return {
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
    }


def report_generator_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Generates final structured ReviewReport and writes:
    - review_outputs/latest_report.json
    - review_outputs/latest_report.md
    """

    _append_log(state, "Running report_generator_tool...")

    try:
        findings = _sort_findings(state.get("findings", []))
        score = _calculate_score(findings)

        report = ReviewReport(
            project_summary=_build_project_summary(state, findings),
            repo_type=state.get("repo_type", "unknown"),
            overall_score=score,
            llm_status=state.get("llm_status", "not_used"),
            fallback_mode=state.get("fallback_mode", False),
            findings=findings,
            skipped_tools=state.get("skipped_tools", []),
            not_applicable_tools=state.get("not_applicable_tools", []),
            limitations=_build_limitations(state),
            final_recommendation=_build_final_recommendation(score, findings),
        )

        output_paths = _write_reports(report, state)

        state["final_report"] = report

        result = ToolResult(
            tool_name="report_generator_tool",
            status="passed",
            summary="Final JSON and Markdown reports generated successfully.",
            findings=[],
            raw_data={
                "overall_score": score,
                "total_findings": len(findings),
                "output_paths": output_paths,
            },
        )

        _append_tool_result(state, result)

        _append_log(state, "report_generator_tool completed.")
        return state

    except Exception as exc:
        finding = Finding(
            category="reporting",
            severity="high",
            importance_percent=85,
            file=None,
            line=None,
            issue="Report generation failed.",
            why_it_matters="The final report is required so users can read structured output from the review agent.",
            suggested_fix=str(exc),
            source_tool="report_generator_tool",
        )

        result = ToolResult(
            tool_name="report_generator_tool",
            status="failed",
            summary="Report generation failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state