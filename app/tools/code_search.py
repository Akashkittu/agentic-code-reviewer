from __future__ import annotations

import re
from pathlib import Path

from app.schemas import Finding, ToolResult
from app.state import CodeReviewState


SCAN_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".php",
    ".rb",
}


CODE_SEARCH_RULES = [
    {
        "id": "todo",
        "pattern": r"\bTODO\b",
        "severity": "info",
        "importance_percent": 30,
        "issue": "TODO comment found.",
        "why": "TODO comments may indicate incomplete work or unfinished cleanup.",
        "fix": "Resolve the TODO or convert it into a tracked issue.",
    },
    {
        "id": "fixme",
        "pattern": r"\bFIXME\b",
        "severity": "low",
        "importance_percent": 45,
        "issue": "FIXME comment found.",
        "why": "FIXME comments usually indicate known broken or risky logic.",
        "fix": "Fix the issue or document why it is safe to keep.",
    },
    {
        "id": "hack",
        "pattern": r"\bHACK\b",
        "severity": "low",
        "importance_percent": 45,
        "issue": "HACK comment found.",
        "why": "HACK comments often mark shortcuts that may become technical debt.",
        "fix": "Replace the shortcut with a cleaner implementation if possible.",
    },
    {
        "id": "print_debug",
        "pattern": r"\bprint\s*\(",
        "severity": "info",
        "importance_percent": 25,
        "issue": "print() statement found.",
        "why": "print() is fine for small scripts, but production projects should usually use logging.",
        "fix": "Use the logging module instead of print() where appropriate.",
    },
    {
        "id": "breakpoint",
        "pattern": r"\bbreakpoint\s*\(",
        "severity": "medium",
        "importance_percent": 80,
        "issue": "breakpoint() found in code.",
        "why": "A committed breakpoint can stop execution unexpectedly.",
        "fix": "Remove breakpoint() before committing production/demo code.",
    },
    {
        "id": "pdb",
        "pattern": r"\bpdb\.set_trace\s*\(",
        "severity": "medium",
        "importance_percent": 80,
        "issue": "pdb.set_trace() found in code.",
        "why": "A committed debugger statement can pause the application unexpectedly.",
        "fix": "Remove pdb.set_trace() before committing production/demo code.",
    },
    {
        "id": "bare_except",
        "pattern": r"^\s*except\s*:",
        "severity": "medium",
        "importance_percent": 70,
        "issue": "Bare except block found.",
        "why": "Bare except catches every exception, including unexpected system-level errors.",
        "fix": "Catch specific exceptions such as ValueError, FileNotFoundError, or RuntimeError.",
    },
]


def _append_log(state: CodeReviewState, message: str) -> None:
    state.setdefault("logs", [])
    state["logs"].append(message)


def _append_tool_result(state: CodeReviewState, result: ToolResult) -> None:
    state.setdefault("tool_results", [])
    state["tool_results"].append(result)


def _repo_root(state: CodeReviewState) -> Path:
    repo_path = state.get("repo_path")
    if not repo_path:
        raise ValueError("repo_path missing in state.")
    return Path(repo_path)


def _read_text(repo_root: Path, relative_path: str, max_chars: int = 200_000) -> str:
    path = repo_root / relative_path

    if not path.exists() or not path.is_file():
        return ""

    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def _should_scan(relative_path: str) -> bool:
    path = Path(relative_path)
    return path.suffix.lower() in SCAN_SUFFIXES


def code_search_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Searches code for review signals:
    - TODO
    - FIXME
    - HACK
    - print debugging
    - breakpoint / pdb
    - bare except
    """

    _append_log(state, "Running code_search_tool...")

    try:
        files = state.get("repo_files", [])
        repo_root = _repo_root(state)

        findings: list[Finding] = []
        matches: list[dict] = []
        scanned_files = 0

        compiled_rules = [
            {
                **rule,
                "compiled": re.compile(rule["pattern"], re.IGNORECASE),
            }
            for rule in CODE_SEARCH_RULES
        ]

        for relative_path in files:
            if not _should_scan(relative_path):
                continue

            scanned_files += 1
            text = _read_text(repo_root, relative_path)

            for line_number, line in enumerate(text.splitlines(), start=1):
                for rule in compiled_rules:
                    if rule["compiled"].search(line):
                        matches.append(
                            {
                                "rule_id": rule["id"],
                                "file": relative_path,
                                "line": line_number,
                                "text": line.strip()[:200],
                            }
                        )

                        findings.append(
                            Finding(
                                category="code_quality",
                                severity=rule["severity"],
                                importance_percent=rule["importance_percent"],
                                file=relative_path,
                                line=line_number,
                                issue=rule["issue"],
                                why_it_matters=rule["why"],
                                suggested_fix=rule["fix"],
                                source_tool="code_search_tool",
                            )
                        )

        result = ToolResult(
            tool_name="code_search_tool",
            status="passed",
            summary=(
                "Code search completed with no review signals found."
                if not findings
                else f"Code search found {len(findings)} review signal(s)."
            ),
            findings=findings,
            raw_data={
                "scanned_files": scanned_files,
                "matches": matches[:50],
            },
        )

        _append_tool_result(state, result)

        if findings:
            state.setdefault("findings", [])
            state["findings"].extend(findings)

        _append_log(state, "code_search_tool completed.")
        return state

    except Exception as exc:
        finding = Finding(
            category="code_quality",
            severity="medium",
            importance_percent=70,
            file=None,
            line=None,
            issue="Code search crashed.",
            why_it_matters="Code search helps identify incomplete work, debug code, and basic quality issues.",
            suggested_fix=str(exc),
            source_tool="code_search_tool",
        )

        result = ToolResult(
            tool_name="code_search_tool",
            status="failed",
            summary="Code search failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state