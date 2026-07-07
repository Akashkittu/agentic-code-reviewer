from __future__ import annotations

import json
from pathlib import Path

from app.schemas import Finding, ToolResult
from app.state import CodeReviewState


PYTHON_EXTENSIONS = {".py"}
JS_TS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}


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


def _file_exists(files: list[str], file_name: str) -> bool:
    return file_name in files


def _folder_exists(files: list[str], folder_name: str) -> bool:
    prefix = folder_name.rstrip("/") + "/"
    return any(file_path.startswith(prefix) for file_path in files)


def _read_file_text(repo_root: Path, relative_path: str, max_chars: int = 30_000) -> str:
    path = repo_root / relative_path

    if not path.exists() or not path.is_file():
        return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def _detect_languages(files: list[str]) -> list[str]:
    languages: set[str] = set()

    for file_path in files:
        suffix = Path(file_path).suffix.lower()

        if suffix in PYTHON_EXTENSIONS:
            languages.add("Python")

        elif suffix in JS_TS_EXTENSIONS:
            languages.add("JavaScript/TypeScript")

        elif suffix == ".html":
            languages.add("HTML")

        elif suffix == ".css":
            languages.add("CSS")

        elif suffix == ".sql":
            languages.add("SQL")

    return sorted(languages)


def _read_package_json(repo_root: Path) -> dict:
    package_text = _read_file_text(repo_root, "package.json")

    if not package_text:
        return {}

    try:
        return json.loads(package_text)
    except json.JSONDecodeError:
        return {}


def _collect_dependency_text(repo_root: Path) -> str:
    dependency_files = [
        "requirements.txt",
        "pyproject.toml",
        "Pipfile",
        "package.json",
    ]

    combined_text = ""

    for file_name in dependency_files:
        combined_text += "\n" + _read_file_text(repo_root, file_name)

    return combined_text.lower()


def _collect_python_code_sample(repo_root: Path, files: list[str], max_files: int = 20) -> str:
    code_text = ""

    python_files = [
        file_path for file_path in files
        if Path(file_path).suffix.lower() == ".py"
    ]

    for file_path in python_files[:max_files]:
        code_text += "\n" + _read_file_text(repo_root, file_path, max_chars=5000).lower()

    return code_text


def _detect_frameworks(repo_root: Path, files: list[str]) -> list[str]:
    frameworks: set[str] = set()

    dependency_text = _collect_dependency_text(repo_root)
    python_code_text = _collect_python_code_sample(repo_root, files)
    package_json = _read_package_json(repo_root)

    package_text = json.dumps(package_json).lower() if package_json else ""

    full_text = dependency_text + "\n" + python_code_text + "\n" + package_text

    if "fastapi" in full_text or "from fastapi" in full_text:
        frameworks.add("FastAPI")

    if "flask" in full_text or "from flask" in full_text:
        frameworks.add("Flask")

    if "django" in full_text or _file_exists(files, "manage.py"):
        frameworks.add("Django")

    if "streamlit" in full_text:
        frameworks.add("Streamlit")

    if "react" in full_text:
        frameworks.add("React")

    if "next" in full_text or _file_exists(files, "next.config.js"):
        frameworks.add("Next.js")

    if "express" in full_text:
        frameworks.add("Express")

    if "langgraph" in full_text:
        frameworks.add("LangGraph")

    if "langchain" in full_text:
        frameworks.add("LangChain")

    if "pydantic" in full_text:
        frameworks.add("Pydantic")

    return sorted(frameworks)


def _detect_project_type(
    files: list[str],
    languages: list[str],
    frameworks: list[str],
) -> str:
    if "FastAPI" in frameworks:
        return "FastAPI Python API project"

    if "Flask" in frameworks:
        return "Flask Python API project"

    if "Django" in frameworks:
        return "Django Python web project"

    if "Streamlit" in frameworks:
        return "Streamlit data app"

    if "Next.js" in frameworks:
        return "Next.js frontend/full-stack project"

    if "React" in frameworks:
        return "React frontend project"

    if "Express" in frameworks:
        return "Node.js Express backend project"

    if "LangGraph" in frameworks:
        return "LangGraph agentic AI project"

    if "Python" in languages and (
        _file_exists(files, "main.py")
        or _file_exists(files, "app.py")
        or _file_exists(files, "cli.py")
    ):
        return "Python CLI/script project"

    if "Python" in languages:
        return "Python project"

    if "JavaScript/TypeScript" in languages:
        return "JavaScript/TypeScript project"

    return "Unknown project type"


def _find_main_files(files: list[str]) -> list[str]:
    main_file_names = {
        "main.py",
        "app.py",
        "server.py",
        "manage.py",
        "index.js",
        "server.js",
        "src/main.jsx",
        "src/main.tsx",
        "src/App.jsx",
        "src/App.tsx",
    }

    found: list[str] = []

    for file_path in files:
        if file_path in main_file_names or Path(file_path).name in main_file_names:
            found.append(file_path)

    return sorted(set(found))


def _detect_folders(files: list[str]) -> dict[str, bool]:
    return {
        "has_tests_folder": _folder_exists(files, "tests") or _folder_exists(files, "test"),
        "has_src_folder": _folder_exists(files, "src"),
        "has_app_folder": _folder_exists(files, "app"),
        "has_config_folder": _folder_exists(files, "config"),
        "has_github_workflows": _folder_exists(files, ".github/workflows"),
    }


def repo_structure_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Detects repo language, framework, project type, important folders,
    and main entry files.
    """

    _append_log(state, "Running repo_structure_tool...")

    try:
        files = state.get("repo_files", [])
        repo_root = _repo_root(state)

        if not files:
            finding = Finding(
                category="repo_structure",
                severity="high",
                importance_percent=90,
                file=None,
                line=None,
                issue="No files available for repo structure analysis.",
                why_it_matters="The structure tool needs repo files from repo_loader_tool.",
                suggested_fix="Run repo_loader_tool before repo_structure_tool.",
                source_tool="repo_structure_tool",
            )

            result = ToolResult(
                tool_name="repo_structure_tool",
                status="failed",
                summary="Repo structure analysis failed because no files were found.",
                findings=[finding],
                raw_data={},
            )

            _append_tool_result(state, result)
            state.setdefault("findings", [])
            state["findings"].append(finding)
            return state

        languages = _detect_languages(files)
        frameworks = _detect_frameworks(repo_root, files)
        project_type = _detect_project_type(files, languages, frameworks)
        main_files = _find_main_files(files)
        folders = _detect_folders(files)

        state["repo_type"] = project_type
        state.setdefault("metadata", {})
        state["metadata"]["languages"] = languages
        state["metadata"]["frameworks"] = frameworks
        state["metadata"]["main_files"] = main_files
        state["metadata"]["folders"] = folders

        findings: list[Finding] = []

        if project_type == "Unknown project type":
            findings.append(
                Finding(
                    category="repo_structure",
                    severity="medium",
                    importance_percent=60,
                    file=None,
                    line=None,
                    issue="Project type could not be detected.",
                    why_it_matters="If the project type is unknown, later tools may not know which checks are relevant.",
                    suggested_fix="Add common project files like requirements.txt, package.json, pyproject.toml, main.py, app.py, or README.md.",
                    source_tool="repo_structure_tool",
                )
            )

        if not main_files:
            findings.append(
                Finding(
                    category="repo_structure",
                    severity="medium",
                    importance_percent=70,
                    file=None,
                    line=None,
                    issue="No obvious main entry file found.",
                    why_it_matters="A reviewer or user may not know where the application starts.",
                    suggested_fix="Add or document an entry file such as main.py, app.py, server.py, index.js, or manage.py.",
                    source_tool="repo_structure_tool",
                )
            )

        result = ToolResult(
            tool_name="repo_structure_tool",
            status="passed",
            summary=f"Detected project type: {project_type}.",
            findings=findings,
            raw_data={
                "project_type": project_type,
                "languages": languages,
                "frameworks": frameworks,
                "main_files": main_files,
                "folders": folders,
                "file_count": len(files),
            },
        )

        _append_tool_result(state, result)

        if findings:
            state.setdefault("findings", [])
            state["findings"].extend(findings)

        _append_log(
            state,
            f"repo_structure_tool completed. Project type: {project_type}",
        )

        return state

    except Exception as exc:
        finding = Finding(
            category="repo_structure",
            severity="high",
            importance_percent=85,
            file=None,
            line=None,
            issue="Repo structure analysis crashed.",
            why_it_matters="If repo structure detection fails, the agent cannot choose the best review tools.",
            suggested_fix=str(exc),
            source_tool="repo_structure_tool",
        )

        result = ToolResult(
            tool_name="repo_structure_tool",
            status="failed",
            summary="Repo structure analysis failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        _append_log(state, f"repo_structure_tool failed: {exc}")

        return state