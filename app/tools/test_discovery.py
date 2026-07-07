from __future__ import annotations

import json
from pathlib import Path

from app.schemas import Finding, ToolResult
from app.state import CodeReviewState


PYTHON_TEST_PATTERNS = [
    "test_",
    "_test.py",
]

JS_TEST_PATTERNS = [
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
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


def _read_text(repo_root: Path, relative_path: str, max_chars: int = 100_000) -> str:
    path = repo_root / relative_path

    if not path.exists() or not path.is_file():
        return ""

    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def _has_tests_folder(files: list[str]) -> bool:
    return any(
        file_path.startswith("tests/")
        or file_path.startswith("test/")
        or "/tests/" in file_path
        or "/test/" in file_path
        for file_path in files
    )


def _find_python_tests(files: list[str]) -> list[str]:
    test_files: list[str] = []

    for file_path in files:
        path = Path(file_path)

        if path.suffix.lower() != ".py":
            continue

        file_name = path.name

        if file_name.startswith("test_") or file_name.endswith("_test.py"):
            test_files.append(file_path)

    return sorted(test_files)


def _find_js_tests(files: list[str]) -> list[str]:
    test_files: list[str] = []

    for file_path in files:
        lower = file_path.lower()

        if any(lower.endswith(pattern) for pattern in JS_TEST_PATTERNS):
            test_files.append(file_path)

    return sorted(test_files)


def _detect_python_test_framework(repo_root: Path, files: list[str]) -> list[str]:
    frameworks: set[str] = set()

    dependency_text = ""

    for dependency_file in ["requirements.txt", "pyproject.toml"]:
        if dependency_file in files:
            dependency_text += "\n" + _read_text(repo_root, dependency_file).lower()

    if "pytest" in dependency_text:
        frameworks.add("pytest")

    if "unittest" in dependency_text:
        frameworks.add("unittest")

    for file_path in files:
        if Path(file_path).suffix.lower() != ".py":
            continue

        text = _read_text(repo_root, file_path, max_chars=20_000).lower()

        if "import pytest" in text or "from pytest" in text:
            frameworks.add("pytest")

        if "import unittest" in text or "unittest.testcase" in text:
            frameworks.add("unittest")

    return sorted(frameworks)


def _detect_js_test_framework(repo_root: Path, files: list[str]) -> list[str]:
    frameworks: set[str] = set()

    if "package.json" not in files:
        return []

    text = _read_text(repo_root, "package.json")

    try:
        package_data = json.loads(text)
    except json.JSONDecodeError:
        return []

    combined = json.dumps(package_data).lower()

    if "jest" in combined:
        frameworks.add("jest")

    if "vitest" in combined:
        frameworks.add("vitest")

    if "mocha" in combined:
        frameworks.add("mocha")

    if "cypress" in combined:
        frameworks.add("cypress")

    if "playwright" in combined:
        frameworks.add("playwright")

    return sorted(frameworks)


def _detect_test_commands(repo_root: Path, files: list[str]) -> list[str]:
    commands: list[str] = []

    if "package.json" in files:
        text = _read_text(repo_root, "package.json")

        try:
            package_data = json.loads(text)
            scripts = package_data.get("scripts", {})

            for script_name, script_command in scripts.items():
                if "test" in script_name.lower():
                    commands.append(f"npm run {script_name}  # {script_command}")

        except json.JSONDecodeError:
            pass

    if "pytest.ini" in files or "pyproject.toml" in files:
        commands.append("pytest")

    if "requirements.txt" in files:
        req_text = _read_text(repo_root, "requirements.txt").lower()
        if "pytest" in req_text:
            commands.append("pytest")

    return sorted(set(commands))


def test_discovery_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Finds whether the repo has tests, test folders, test files,
    test frameworks, and test commands.
    """

    _append_log(state, "Running test_discovery_tool...")

    try:
        files = state.get("repo_files", [])
        repo_root = _repo_root(state)

        findings: list[Finding] = []

        python_files = [
            file_path for file_path in files
            if Path(file_path).suffix.lower() == ".py"
        ]

        js_files = [
            file_path for file_path in files
            if Path(file_path).suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}
        ]

        python_test_files = _find_python_tests(files)
        js_test_files = _find_js_tests(files)
        all_test_files = sorted(set(python_test_files + js_test_files))

        has_tests_folder = _has_tests_folder(files)

        python_test_frameworks = _detect_python_test_framework(repo_root, files)
        js_test_frameworks = _detect_js_test_framework(repo_root, files)
        test_frameworks = sorted(set(python_test_frameworks + js_test_frameworks))

        test_commands = _detect_test_commands(repo_root, files)

        is_testable_project = bool(python_files or js_files)

        if not is_testable_project:
            result = ToolResult(
                tool_name="test_discovery_tool",
                status="not_applicable",
                summary="No Python or JavaScript/TypeScript files found, so test discovery is not applicable.",
                findings=[],
                raw_data={
                    "has_tests_folder": has_tests_folder,
                    "test_files": all_test_files,
                    "test_frameworks": test_frameworks,
                    "test_commands": test_commands,
                },
            )

            _append_tool_result(state, result)
            state.setdefault("not_applicable_tools", [])
            state["not_applicable_tools"].append("test_discovery_tool")
            return state

        if not all_test_files:
            findings.append(
                Finding(
                    category="testing",
                    severity="high",
                    importance_percent=90,
                    file=None,
                    line=None,
                    issue="No test files found.",
                    why_it_matters="Without tests, future changes can break existing functionality without being noticed.",
                    suggested_fix="Add tests under tests/ using pytest for Python or Jest/Vitest for JavaScript projects.",
                    source_tool="test_discovery_tool",
                )
            )

        if not has_tests_folder:
            findings.append(
                Finding(
                    category="testing",
                    severity="medium",
                    importance_percent=70,
                    file=None,
                    line=None,
                    issue="No tests folder found.",
                    why_it_matters="A tests folder makes the project easier to verify and maintain.",
                    suggested_fix="Create a tests/ folder and place test files like test_main.py inside it.",
                    source_tool="test_discovery_tool",
                )
            )

        if all_test_files and not test_frameworks:
            findings.append(
                Finding(
                    category="testing",
                    severity="medium",
                    importance_percent=65,
                    file=None,
                    line=None,
                    issue="Test files exist but no test framework was clearly detected.",
                    why_it_matters="Users may not know whether to run pytest, unittest, jest, vitest, or another tool.",
                    suggested_fix="Document the test framework and add it to requirements.txt, pyproject.toml, or package.json.",
                    source_tool="test_discovery_tool",
                )
            )

        if all_test_files and not test_commands:
            findings.append(
                Finding(
                    category="testing",
                    severity="medium",
                    importance_percent=65,
                    file=None,
                    line=None,
                    issue="Test files exist but no test command was detected.",
                    why_it_matters="A reviewer should be able to run tests quickly during setup.",
                    suggested_fix="Add a test command in README, package.json scripts, or pyproject.toml.",
                    source_tool="test_discovery_tool",
                )
            )

        status = "passed" if not findings else "failed"

        result = ToolResult(
            tool_name="test_discovery_tool",
            status=status,
            summary=(
                "Test discovery completed successfully."
                if not findings
                else f"Test discovery found {len(findings)} issue(s)."
            ),
            findings=findings,
            raw_data={
                "has_tests_folder": has_tests_folder,
                "python_test_files": python_test_files,
                "js_test_files": js_test_files,
                "test_files_count": len(all_test_files),
                "test_frameworks": test_frameworks,
                "test_commands": test_commands,
            },
        )

        _append_tool_result(state, result)

        if findings:
            state.setdefault("findings", [])
            state["findings"].extend(findings)

        _append_log(state, "test_discovery_tool completed.")
        return state

    except Exception as exc:
        finding = Finding(
            category="testing",
            severity="high",
            importance_percent=80,
            file=None,
            line=None,
            issue="Test discovery crashed.",
            why_it_matters="Test discovery is needed to understand how reliable and maintainable the project is.",
            suggested_fix=str(exc),
            source_tool="test_discovery_tool",
        )

        result = ToolResult(
            tool_name="test_discovery_tool",
            status="failed",
            summary="Test discovery failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state