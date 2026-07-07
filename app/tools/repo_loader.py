from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.schemas import Finding, ToolResult
from app.state import CodeReviewState


IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".idea",
    ".vscode",
}

IGNORED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".sqlite",
    ".db",
}

IMPORTANT_FILE_NAMES = {
    "README.md",
    "readme.md",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "app.py",
    "main.py",
    "server.py",
    "manage.py",
    ".env",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
}


def _append_log(state: CodeReviewState, message: str) -> None:
    state.setdefault("logs", [])
    state["logs"].append(message)


def _append_tool_result(state: CodeReviewState, result: ToolResult) -> None:
    state.setdefault("tool_results", [])
    state["tool_results"].append(result)


def _is_github_url(url: str) -> bool:
    return "github.com" in url.lower()


def _should_skip_path(path: Path, repo_root: Path) -> bool:
    relative_parts = path.relative_to(repo_root).parts

    for part in relative_parts:
        if part in IGNORED_DIRS:
            return True

    if path.is_file() and path.suffix.lower() in IGNORED_FILE_SUFFIXES:
        return True

    return False


def _scan_repo_files(repo_root: Path, max_files: int = 1000) -> list[str]:
    files: list[str] = []

    for path in repo_root.rglob("*"):
        if len(files) >= max_files:
            break

        if _should_skip_path(path, repo_root):
            continue

        if path.is_file():
            relative_path = path.relative_to(repo_root).as_posix()
            files.append(relative_path)

    return sorted(files)


def _find_important_files(files: list[str]) -> list[str]:
    important: list[str] = []

    for file_path in files:
        file_name = Path(file_path).name

        if file_name in IMPORTANT_FILE_NAMES:
            important.append(file_path)

        if file_path.startswith("tests/") or file_path.startswith("test/"):
            important.append(file_path)

        if file_path.startswith(".github/workflows/"):
            important.append(file_path)

    return sorted(set(important))


def _clone_github_repo(repo_url: str) -> Path:
    if not _is_github_url(repo_url):
        raise ValueError("Only public GitHub repository URLs are supported in this prototype.")

    temp_dir = Path(tempfile.mkdtemp(prefix="repo_review_"))

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(temp_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Git clone failed: {exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError("Git clone timed out.") from exc

    return temp_dir


def repo_loader_tool(state: CodeReviewState) -> CodeReviewState:
    """
    First tool in the workflow.

    It accepts:
    1. local repo path
    2. GitHub repo URL

    It updates state with:
    - repo_path
    - repo_files
    - important_files
    """

    _append_log(state, "Running repo_loader_tool...")

    try:
        repo_url = state.get("repo_url")
        repo_path = state.get("repo_path")

        if repo_url:
            _append_log(state, f"Cloning GitHub repo: {repo_url}")
            loaded_repo_path = _clone_github_repo(repo_url)
            state["repo_path"] = str(loaded_repo_path)

        elif repo_path:
            loaded_repo_path = Path(repo_path).resolve()

            if not loaded_repo_path.exists():
                raise FileNotFoundError(f"Repo path does not exist: {loaded_repo_path}")

            if not loaded_repo_path.is_dir():
                raise NotADirectoryError(f"Repo path is not a folder: {loaded_repo_path}")

            state["repo_path"] = str(loaded_repo_path)

        else:
            raise ValueError("No repo_path or repo_url found in state.")

        repo_root = Path(state["repo_path"])
        repo_files = _scan_repo_files(repo_root)
        important_files = _find_important_files(repo_files)

        state["repo_files"] = repo_files
        state["important_files"] = important_files

        if not repo_files:
            finding = Finding(
                category="repo_loading",
                severity="high",
                importance_percent=90,
                file=None,
                line=None,
                issue="No readable files found in the repository.",
                why_it_matters="The agent cannot review a repository if no files are available.",
                suggested_fix="Check whether the path is correct and whether the repository contains source files.",
                source_tool="repo_loader_tool",
            )

            result = ToolResult(
                tool_name="repo_loader_tool",
                status="failed",
                summary="Repository loaded, but no readable files were found.",
                findings=[finding],
                raw_data={
                    "repo_path": state["repo_path"],
                    "file_count": 0,
                    "important_file_count": 0,
                },
            )

            _append_tool_result(state, result)
            state.setdefault("findings", [])
            state["findings"].append(finding)
            return state

        result = ToolResult(
            tool_name="repo_loader_tool",
            status="passed",
            summary=f"Repository loaded successfully with {len(repo_files)} readable files.",
            findings=[],
            raw_data={
                "repo_path": state["repo_path"],
                "file_count": len(repo_files),
                "important_file_count": len(important_files),
                "important_files": important_files,
                "sample_files": repo_files[:20],
            },
        )

        _append_tool_result(state, result)

        _append_log(
            state,
            f"repo_loader_tool completed. Files found: {len(repo_files)}",
        )

        return state

    except Exception as exc:
        finding = Finding(
            category="repo_loading",
            severity="critical",
            importance_percent=100,
            file=None,
            line=None,
            issue="Repository could not be loaded.",
            why_it_matters="Without loading the repository, the agent cannot continue the review.",
            suggested_fix=str(exc),
            source_tool="repo_loader_tool",
        )

        result = ToolResult(
            tool_name="repo_loader_tool",
            status="failed",
            summary="Repository loading failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        _append_log(state, f"repo_loader_tool failed: {exc}")

        return state