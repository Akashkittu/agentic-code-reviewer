from __future__ import annotations

import re
from pathlib import Path

from app.schemas import Finding, ToolResult
from app.state import CodeReviewState


SECRET_PATTERNS = [
    "api_key",
    "apikey",
    "secret",
    "password",
    "passwd",
    "token",
    "jwt_secret",
    "database_url",
    "db_url",
    "private_key",
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


def _has_file(files: list[str], name: str) -> bool:
    return name in files


def _read_text(repo_root: Path, relative_path: str, max_chars: int = 100_000) -> str:
    path = repo_root / relative_path

    if not path.exists() or not path.is_file():
        return ""

    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def _looks_like_secret_assignment(line: str) -> bool:
    lower = line.lower().strip()

    if not lower or lower.startswith("#"):
        return False

    has_secret_word = any(pattern in lower for pattern in SECRET_PATTERNS)
    has_assignment = "=" in lower or ":" in lower

    if not has_secret_word or not has_assignment:
        return False

    fake_or_placeholder_words = [
        "your_",
        "example",
        "placeholder",
        "dummy",
        "change_me",
        "changeme",
        "xxx",
        "here",
    ]

    if any(word in lower for word in fake_or_placeholder_words):
        return False

    return True


def _find_hardcoded_secrets(repo_root: Path, files: list[str]) -> list[Finding]:
    findings: list[Finding] = []

    allowed_suffixes = {".py", ".js", ".ts", ".tsx", ".jsx", ".env", ".toml", ".yaml", ".yml"}

    for relative_path in files:
        path = Path(relative_path)

        if path.suffix.lower() not in allowed_suffixes and path.name not in {".env"}:
            continue

        text = _read_text(repo_root, relative_path)

        for line_number, line in enumerate(text.splitlines(), start=1):
            if _looks_like_secret_assignment(line):
                findings.append(
                    Finding(
                        category="env_config",
                        severity="critical",
                        importance_percent=100,
                        file=relative_path,
                        line=line_number,
                        issue="Possible hardcoded secret or sensitive config value found.",
                        why_it_matters="Secrets committed in code can leak API keys, database passwords, or tokens.",
                        suggested_fix="Move this value to environment variables and keep only a placeholder in .env.example.",
                        source_tool="env_config_check_tool",
                    )
                )

    return findings


def env_config_check_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Checks .env safety, .env.example presence, and possible hardcoded secrets.
    """

    _append_log(state, "Running env_config_check_tool...")

    try:
        files = state.get("repo_files", [])
        repo_root = _repo_root(state)

        findings: list[Finding] = []

        has_env = _has_file(files, ".env")
        has_env_example = _has_file(files, ".env.example")

        if has_env:
            findings.append(
                Finding(
                    category="env_config",
                    severity="critical",
                    importance_percent=100,
                    file=".env",
                    line=None,
                    issue=".env file appears to be committed.",
                    why_it_matters=".env often contains API keys, database URLs, JWT secrets, and passwords.",
                    suggested_fix="Remove .env from Git, add .env to .gitignore, and keep only .env.example.",
                    source_tool="env_config_check_tool",
                )
            )

        project_uses_config_words = False

        for relative_path in files:
            if Path(relative_path).suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".jsx"}:
                continue

            text = _read_text(repo_root, relative_path).lower()

            if any(word in text for word in SECRET_PATTERNS):
                project_uses_config_words = True
                break

        if project_uses_config_words and not has_env_example:
            findings.append(
                Finding(
                    category="env_config",
                    severity="high",
                    importance_percent=90,
                    file=None,
                    line=None,
                    issue="Project appears to use secrets/config values but .env.example is missing.",
                    why_it_matters="Users need .env.example to know which environment variables are required.",
                    suggested_fix="Add .env.example with placeholder keys like OPENAI_API_KEY=your_key_here.",
                    source_tool="env_config_check_tool",
                )
            )

        findings.extend(_find_hardcoded_secrets(repo_root, files))

        status = "passed" if not findings else "failed"

        result = ToolResult(
            tool_name="env_config_check_tool",
            status=status,
            summary=(
                "Environment/config safety looks okay."
                if not findings
                else f"Environment/config check found {len(findings)} issue(s)."
            ),
            findings=findings,
            raw_data={
                "has_env": has_env,
                "has_env_example": has_env_example,
                "project_uses_config_words": project_uses_config_words,
            },
        )

        _append_tool_result(state, result)

        if findings:
            state.setdefault("findings", [])
            state["findings"].extend(findings)

        _append_log(state, "env_config_check_tool completed.")
        return state

    except Exception as exc:
        finding = Finding(
            category="env_config",
            severity="high",
            importance_percent=85,
            file=None,
            line=None,
            issue="Environment/config check crashed.",
            why_it_matters="Config checks are needed because API keys and secrets are common repo risks.",
            suggested_fix=str(exc),
            source_tool="env_config_check_tool",
        )

        result = ToolResult(
            tool_name="env_config_check_tool",
            status="failed",
            summary="Environment/config check failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state