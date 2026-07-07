from __future__ import annotations

import re
from pathlib import Path

from app.schemas import Finding, ToolResult
from app.state import CodeReviewState


README_NAMES = [
    "README.md",
    "readme.md",
    "README.txt",
    "readme.txt",
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


def _read_text(repo_root: Path, relative_path: str, max_chars: int = 150_000) -> str:
    path = repo_root / relative_path

    if not path.exists() or not path.is_file():
        return ""

    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def _find_readme(files: list[str]) -> str | None:
    for name in README_NAMES:
        if name in files:
            return name

    for file_path in files:
        if Path(file_path).name.lower().startswith("readme"):
            return file_path

    return None


def _contains_any(text: str, patterns: list[str]) -> bool:
    lower = text.lower()

    return any(pattern.lower() in lower for pattern in patterns)


def _has_code_block(text: str) -> bool:
    return "```" in text


def _has_command_like_text(text: str) -> bool:
    command_patterns = [
        r"\bpip install\b",
        r"\bpython\b",
        r"\buvicorn\b",
        r"\bflask run\b",
        r"\bnpm install\b",
        r"\bnpm run\b",
        r"\bpytest\b",
        r"\bdocker\b",
    ]

    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in command_patterns)


def readme_review_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Reviews README quality:
    - existence
    - project description
    - setup instructions
    - run command
    - test command
    - env/config instructions
    - architecture/design explanation
    """

    _append_log(state, "Running readme_review_tool...")

    try:
        files = state.get("repo_files", [])
        repo_root = _repo_root(state)

        findings: list[Finding] = []
        readme_path = _find_readme(files)

        if not readme_path:
            finding = Finding(
                category="documentation",
                severity="high",
                importance_percent=95,
                file=None,
                line=None,
                issue="README file is missing.",
                why_it_matters="A take-home assignment must be easy for reviewers to understand and run.",
                suggested_fix="Add README.md with problem statement, architecture, setup, run command, demo steps, limitations, and future improvements.",
                source_tool="readme_review_tool",
            )

            result = ToolResult(
                tool_name="readme_review_tool",
                status="failed",
                summary="README review failed because README is missing.",
                findings=[finding],
                raw_data={"readme_path": None},
            )

            _append_tool_result(state, result)
            state.setdefault("findings", [])
            state["findings"].append(finding)
            return state

        text = _read_text(repo_root, readme_path)
        lower = text.lower()

        if len(text.strip()) < 300:
            findings.append(
                Finding(
                    category="documentation",
                    severity="medium",
                    importance_percent=75,
                    file=readme_path,
                    line=None,
                    issue="README is too short.",
                    why_it_matters="A short README may not explain the problem, architecture, setup, and demo clearly.",
                    suggested_fix="Expand README with overview, architecture, tools, run steps, example output, limitations, and future improvements.",
                    source_tool="readme_review_tool",
                )
            )

        has_project_description = _contains_any(
            lower,
            ["overview", "problem", "what it does", "agent", "code review"],
        )

        has_setup = _contains_any(
            lower,
            ["setup", "installation", "install", "requirements", "environment"],
        )

        has_run = _contains_any(
            lower,
            ["run", "usage", "demo", "python main.py", "uvicorn", "npm run"],
        )

        has_test = _contains_any(
            lower,
            ["test", "pytest", "unittest", "jest", "vitest"],
        )

        has_env = _contains_any(
            lower,
            [".env", ".env.example", "api key", "environment variable"],
        )

        has_architecture = _contains_any(
            lower,
            ["architecture", "design", "langgraph", "pydantic", "tool", "workflow"],
        )

        has_limitation = _contains_any(
            lower,
            ["limitation", "future", "improve", "next step"],
        )

        if not has_project_description:
            findings.append(
                Finding(
                    category="documentation",
                    severity="medium",
                    importance_percent=70,
                    file=readme_path,
                    line=None,
                    issue="README does not clearly explain the project/problem.",
                    why_it_matters="Reviewers should quickly understand what the agent solves.",
                    suggested_fix="Add an Overview or Problem section explaining the repo review agent.",
                    source_tool="readme_review_tool",
                )
            )

        if not has_setup:
            findings.append(
                Finding(
                    category="documentation",
                    severity="high",
                    importance_percent=85,
                    file=readme_path,
                    line=None,
                    issue="README does not clearly include setup/install instructions.",
                    why_it_matters="Reviewers may fail to run the project if setup steps are missing.",
                    suggested_fix="Add setup commands such as python -m venv .venv and pip install -r requirements.txt.",
                    source_tool="readme_review_tool",
                )
            )

        if not has_run:
            findings.append(
                Finding(
                    category="documentation",
                    severity="high",
                    importance_percent=90,
                    file=readme_path,
                    line=None,
                    issue="README does not clearly include a run/demo command.",
                    why_it_matters="The assignment requires a live demo, so the run command must be obvious.",
                    suggested_fix="Add usage command: python main.py --repo ./sample_repo.",
                    source_tool="readme_review_tool",
                )
            )

        if not has_test:
            findings.append(
                Finding(
                    category="documentation",
                    severity="medium",
                    importance_percent=65,
                    file=readme_path,
                    line=None,
                    issue="README does not mention how to run tests.",
                    why_it_matters="Test instructions help reviewers verify the project.",
                    suggested_fix="Add a Tests section, even if tests are planned for the next version.",
                    source_tool="readme_review_tool",
                )
            )

        if not has_env:
            findings.append(
                Finding(
                    category="documentation",
                    severity="medium",
                    importance_percent=70,
                    file=readme_path,
                    line=None,
                    issue="README does not explain environment variables or .env.example.",
                    why_it_matters="LLM projects often need API keys, and reviewers need to know how to configure them safely.",
                    suggested_fix="Add instructions to copy .env.example to .env and fill API keys locally.",
                    source_tool="readme_review_tool",
                )
            )

        if not has_architecture:
            findings.append(
                Finding(
                    category="documentation",
                    severity="medium",
                    importance_percent=75,
                    file=readme_path,
                    line=None,
                    issue="README does not explain architecture/design decisions.",
                    why_it_matters="The assignment asks for architecture and design decisions in the video and repo.",
                    suggested_fix="Add an Architecture section covering Pydantic validation, LangGraph workflow, tool loop, and LLM fallback.",
                    source_tool="readme_review_tool",
                )
            )

        if not has_limitation:
            findings.append(
                Finding(
                    category="documentation",
                    severity="low",
                    importance_percent=50,
                    file=readme_path,
                    line=None,
                    issue="README does not mention limitations or future improvements.",
                    why_it_matters="The assignment asks for one limitation and what to improve next.",
                    suggested_fix="Add a Limitations and Future Work section.",
                    source_tool="readme_review_tool",
                )
            )

        if not _has_code_block(text) and not _has_command_like_text(text):
            findings.append(
                Finding(
                    category="documentation",
                    severity="medium",
                    importance_percent=70,
                    file=readme_path,
                    line=None,
                    issue="README has no clear command examples.",
                    why_it_matters="Command examples make the project easier to run during review.",
                    suggested_fix="Add fenced code blocks with setup and run commands.",
                    source_tool="readme_review_tool",
                )
            )

        status = "passed" if not findings else "failed"

        result = ToolResult(
            tool_name="readme_review_tool",
            status=status,
            summary=(
                "README looks good."
                if not findings
                else f"README review found {len(findings)} issue(s)."
            ),
            findings=findings,
            raw_data={
                "readme_path": readme_path,
                "readme_length_chars": len(text),
                "has_project_description": has_project_description,
                "has_setup": has_setup,
                "has_run": has_run,
                "has_test": has_test,
                "has_env": has_env,
                "has_architecture": has_architecture,
                "has_limitation": has_limitation,
                "has_code_block": _has_code_block(text),
                "has_command_like_text": _has_command_like_text(text),
            },
        )

        _append_tool_result(state, result)

        if findings:
            state.setdefault("findings", [])
            state["findings"].extend(findings)

        _append_log(state, "readme_review_tool completed.")
        return state

    except Exception as exc:
        finding = Finding(
            category="documentation",
            severity="high",
            importance_percent=80,
            file=None,
            line=None,
            issue="README review crashed.",
            why_it_matters="README review is needed because reviewers must understand and run the assignment.",
            suggested_fix=str(exc),
            source_tool="readme_review_tool",
        )

        result = ToolResult(
            tool_name="readme_review_tool",
            status="failed",
            summary="README review failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state