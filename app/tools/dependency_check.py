from __future__ import annotations

import json
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


def _has_file(files: list[str], name: str) -> bool:
    return name in files


def _read_text(repo_root: Path, relative_path: str) -> str:
    path = repo_root / relative_path

    if not path.exists() or not path.is_file():
        return ""

    return path.read_text(encoding="utf-8", errors="ignore")


def _check_requirements_txt(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    text = _read_text(repo_root, "requirements.txt")

    if not text.strip():
        findings.append(
            Finding(
                category="dependencies",
                severity="medium",
                importance_percent=70,
                file="requirements.txt",
                line=None,
                issue="requirements.txt is empty.",
                why_it_matters="An empty dependency file does not help users install the project.",
                suggested_fix="Add required packages such as langgraph, pydantic, python-dotenv, rich, GitPython, openai, google-generativeai, and anthropic.",
                source_tool="dependency_check_tool",
            )
        )
        return findings

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    unpinned = []

    for line in lines:
        if "==" not in line and ">=" not in line and "~=" not in line:
            unpinned.append(line)

    if unpinned:
        findings.append(
            Finding(
                category="dependencies",
                severity="low",
                importance_percent=55,
                file="requirements.txt",
                line=None,
                issue="Some Python dependencies are not version pinned.",
                why_it_matters="Unpinned dependencies can make the project work today but fail later if package versions change.",
                suggested_fix="Pin important packages, for example: pydantic>=2.0.0 or langgraph>=0.2.0.",
                source_tool="dependency_check_tool",
            )
        )

    return findings


def _check_package_json(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    text = _read_text(repo_root, "package.json")

    if not text.strip():
        return findings

    try:
        package_data = json.loads(text)
    except json.JSONDecodeError:
        findings.append(
            Finding(
                category="dependencies",
                severity="high",
                importance_percent=85,
                file="package.json",
                line=None,
                issue="package.json is invalid JSON.",
                why_it_matters="Node.js tools cannot install or run the project if package.json is broken.",
                suggested_fix="Fix the JSON syntax in package.json.",
                source_tool="dependency_check_tool",
            )
        )
        return findings

    dependencies = package_data.get("dependencies", {})
    dev_dependencies = package_data.get("devDependencies", {})
    scripts = package_data.get("scripts", {})

    if not dependencies and not dev_dependencies:
        findings.append(
            Finding(
                category="dependencies",
                severity="medium",
                importance_percent=70,
                file="package.json",
                line=None,
                issue="package.json has no dependencies or devDependencies.",
                why_it_matters="A Node/React project usually needs dependencies to install and run.",
                suggested_fix="Add required dependencies or remove package.json if it is not needed.",
                source_tool="dependency_check_tool",
            )
        )

    if not scripts:
        findings.append(
            Finding(
                category="dependencies",
                severity="medium",
                importance_percent=75,
                file="package.json",
                line=None,
                issue="package.json has no scripts section.",
                why_it_matters="Users may not know how to start, test, or build the project.",
                suggested_fix="Add scripts like start, dev, test, or build.",
                source_tool="dependency_check_tool",
            )
        )

    return findings


def dependency_check_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Checks whether dependency/setup files exist and look usable.
    """

    _append_log(state, "Running dependency_check_tool...")

    try:
        files = state.get("repo_files", [])
        repo_root = _repo_root(state)
        repo_type = state.get("repo_type", "unknown")

        findings: list[Finding] = []

        has_requirements = _has_file(files, "requirements.txt")
        has_pyproject = _has_file(files, "pyproject.toml")
        has_package_json = _has_file(files, "package.json")

        is_python_project = "Python" in repo_type or any(
            Path(file_path).suffix == ".py" for file_path in files
        )

        is_js_project = "JavaScript" in repo_type or "React" in repo_type or has_package_json

        if is_python_project and not has_requirements and not has_pyproject:
            findings.append(
                Finding(
                    category="dependencies",
                    severity="high",
                    importance_percent=95,
                    file=None,
                    line=None,
                    issue="No Python dependency file found.",
                    why_it_matters="Without requirements.txt or pyproject.toml, users may not know how to install the project.",
                    suggested_fix="Add requirements.txt or pyproject.toml with all required Python packages.",
                    source_tool="dependency_check_tool",
                )
            )

        if is_js_project and not has_package_json:
            findings.append(
                Finding(
                    category="dependencies",
                    severity="high",
                    importance_percent=90,
                    file=None,
                    line=None,
                    issue="No package.json found for JavaScript/React project.",
                    why_it_matters="Without package.json, users cannot install Node dependencies or run npm scripts.",
                    suggested_fix="Add package.json with dependencies and scripts.",
                    source_tool="dependency_check_tool",
                )
            )

        if has_requirements:
            findings.extend(_check_requirements_txt(repo_root))

        if has_package_json:
            findings.extend(_check_package_json(repo_root))

        status = "passed" if not findings else "failed"

        result = ToolResult(
            tool_name="dependency_check_tool",
            status=status,
            summary=(
                "Dependency files look okay."
                if not findings
                else f"Dependency check found {len(findings)} issue(s)."
            ),
            findings=findings,
            raw_data={
                "has_requirements_txt": has_requirements,
                "has_pyproject_toml": has_pyproject,
                "has_package_json": has_package_json,
                "repo_type": repo_type,
            },
        )

        _append_tool_result(state, result)

        if findings:
            state.setdefault("findings", [])
            state["findings"].extend(findings)

        _append_log(state, "dependency_check_tool completed.")
        return state

    except Exception as exc:
        finding = Finding(
            category="dependencies",
            severity="high",
            importance_percent=85,
            file=None,
            line=None,
            issue="Dependency check crashed.",
            why_it_matters="Dependency checks are needed to understand whether the project can be installed.",
            suggested_fix=str(exc),
            source_tool="dependency_check_tool",
        )

        result = ToolResult(
            tool_name="dependency_check_tool",
            status="failed",
            summary="Dependency check failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state