from __future__ import annotations

from pathlib import Path

from app.schemas import Finding, ToolResult
from app.state import CodeReviewState


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


def _add_finding(
    findings: list[Finding],
    *,
    severity: str,
    importance_percent: int,
    issue: str,
    why_it_matters: str,
    suggested_fix: str,
    file: str | None = None,
) -> None:
    findings.append(
        Finding(
            category="repo_hygiene",
            severity=severity,
            importance_percent=importance_percent,
            file=file,
            line=None,
            issue=issue,
            why_it_matters=why_it_matters,
            suggested_fix=suggested_fix,
            source_tool="repo_hygiene_tool",
        )
    )


def repo_hygiene_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Checks basic GitHub/repository cleanliness:
    - README
    - .gitignore
    - committed .env
    - generated folders
    - review outputs committed
    - large files
    - optional LICENSE
    """

    _append_log(state, "Running repo_hygiene_tool...")

    try:
        repo_root = _repo_root(state)
        files = set(state.get("repo_files", []))
        findings: list[Finding] = []

        if "README.md" not in files and "readme.md" not in files:
            _add_finding(
                findings,
                severity="high",
                importance_percent=95,
                issue="README file is missing.",
                why_it_matters="A GitHub repository needs a README so reviewers can understand the project, setup, and demo commands.",
                suggested_fix="Add README.md with problem statement, architecture, setup, run command, demo steps, limitations, and future improvements.",
            )

        if ".gitignore" not in files:
            _add_finding(
                findings,
                severity="medium",
                importance_percent=85,
                issue=".gitignore file is missing.",
                why_it_matters="Without .gitignore, generated files, virtual environments, logs, and secrets can be accidentally committed.",
                suggested_fix="Add .gitignore and include .env, __pycache__/, .venv/, review_outputs/, node_modules/, and cache folders.",
            )

        if ".env" in files or (repo_root / ".env").exists():
            _add_finding(
                findings,
                severity="critical",
                importance_percent=100,
                issue=".env file appears to be committed.",
                why_it_matters=".env files may contain API keys, database URLs, passwords, or tokens.",
                suggested_fix="Remove .env from Git, rotate exposed secrets, and keep only .env.example in the repository.",
                file=".env",
            )

        if (repo_root / "review_outputs").exists():
            _add_finding(
                findings,
                severity="low",
                importance_percent=60,
                issue="Generated review_outputs folder exists in the repo.",
                why_it_matters="Generated output files should usually not be committed because they can become stale and confuse reviewers.",
                suggested_fix="Delete review_outputs before pushing and keep review_outputs/ in .gitignore.",
                file="review_outputs",
            )

        if any(path.name == "__pycache__" for path in repo_root.rglob("__pycache__")):
            _add_finding(
                findings,
                severity="medium",
                importance_percent=80,
                issue="__pycache__ folder found in the repo.",
                why_it_matters="Python bytecode cache files are generated locally and should not be committed.",
                suggested_fix="Delete __pycache__ folders and keep __pycache__/ in .gitignore.",
                file="__pycache__",
            )

        if (repo_root / "node_modules").exists():
            _add_finding(
                findings,
                severity="high",
                importance_percent=90,
                issue="node_modules folder found in the repo.",
                why_it_matters="node_modules is very large and should be restored using package.json, not committed.",
                suggested_fix="Delete node_modules and keep node_modules/ in .gitignore.",
                file="node_modules",
            )

        license_files = {"LICENSE", "LICENSE.md", "license", "license.md"}
        if not any(name in files for name in license_files):
            _add_finding(
                findings,
                severity="info",
                importance_percent=35,
                issue="License file is missing.",
                why_it_matters="A license helps others understand how the repository can be used.",
                suggested_fix="Add a LICENSE file if this project will be shared publicly.",
            )

        large_files = []
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue

            if ".git" in path.parts:
                continue

            size_mb = path.stat().st_size / (1024 * 1024)

            if size_mb > 2:
                large_files.append(
                    {
                        "file": path.relative_to(repo_root).as_posix(),
                        "size_mb": round(size_mb, 2),
                    }
                )

        for item in large_files[:10]:
            _add_finding(
                findings,
                severity="low",
                importance_percent=50,
                issue="Large file found in repository.",
                why_it_matters="Large files make cloning and reviewing the repository slower.",
                suggested_fix="Remove unnecessary large files or store them outside Git.",
                file=item["file"],
            )

        status = "passed" if not findings else "failed"

        result = ToolResult(
            tool_name="repo_hygiene_tool",
            status=status,
            summary=(
                "Repository hygiene looks okay."
                if not findings
                else f"Repository hygiene check found {len(findings)} issue(s)."
            ),
            findings=findings,
            raw_data={
                "file_count": len(files),
                "large_files": large_files[:10],
            },
        )

        _append_tool_result(state, result)

        if findings:
            state.setdefault("findings", [])
            state["findings"].extend(findings)

        _append_log(state, "repo_hygiene_tool completed.")
        return state

    except Exception as exc:
        finding = Finding(
            category="repo_hygiene",
            severity="medium",
            importance_percent=70,
            file=None,
            line=None,
            issue="Repository hygiene check crashed.",
            why_it_matters="Repo hygiene checks help catch files that should not be pushed to GitHub.",
            suggested_fix=str(exc),
            source_tool="repo_hygiene_tool",
        )

        result = ToolResult(
            tool_name="repo_hygiene_tool",
            status="failed",
            summary="Repository hygiene check failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state