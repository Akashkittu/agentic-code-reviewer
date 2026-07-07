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
    ".yaml",
    ".yml",
    ".toml",
}


SECURITY_RULES = [
    {
        "id": "python_eval",
        "pattern": r"\beval\s*\(",
        "severity": "critical",
        "importance_percent": 100,
        "issue": "Use of eval() detected.",
        "why": "eval() can execute arbitrary code if user-controlled input reaches it.",
        "fix": "Avoid eval(). Use safe parsing like json.loads(), ast.literal_eval(), or explicit logic.",
    },
    {
        "id": "python_exec",
        "pattern": r"\bexec\s*\(",
        "severity": "critical",
        "importance_percent": 100,
        "issue": "Use of exec() detected.",
        "why": "exec() can run arbitrary code and is dangerous with dynamic input.",
        "fix": "Remove exec() and replace it with explicit function calls or safe parsing.",
    },
    {
        "id": "os_system",
        "pattern": r"\bos\.system\s*\(",
        "severity": "high",
        "importance_percent": 90,
        "issue": "Use of os.system() detected.",
        "why": "os.system() can create command injection risk if user input is included.",
        "fix": "Use subprocess.run() with a list of arguments and shell=False.",
    },
    {
        "id": "subprocess_shell_true",
        "pattern": r"subprocess\.(run|call|Popen|check_output)\s*\(.*shell\s*=\s*True",
        "severity": "high",
        "importance_percent": 95,
        "issue": "subprocess is called with shell=True.",
        "why": "shell=True can allow command injection when input is not strictly controlled.",
        "fix": "Use shell=False and pass command arguments as a list.",
    },
    {
        "id": "flask_debug_true",
        "pattern": r"debug\s*=\s*True",
        "severity": "high",
        "importance_percent": 85,
        "issue": "Debug mode appears to be enabled.",
        "why": "Debug mode can expose stack traces, environment details, and interactive debugger access.",
        "fix": "Disable debug mode in production and use environment-based config.",
    },
    {
        "id": "cors_open",
        "pattern": r"CORS\s*\(.*\*|allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]",
        "severity": "medium",
        "importance_percent": 75,
        "issue": "CORS appears to allow all origins.",
        "why": "Open CORS can expose APIs to unwanted browser-based access.",
        "fix": "Restrict CORS origins to trusted frontend domains.",
    },
    {
        "id": "pickle_usage",
        "pattern": r"\bpickle\.(load|loads)\s*\(",
        "severity": "high",
        "importance_percent": 90,
        "issue": "pickle load/loads detected.",
        "why": "Loading untrusted pickle data can execute arbitrary code.",
        "fix": "Use safer formats like JSON for untrusted data.",
    },
    {
        "id": "yaml_unsafe_load",
        "pattern": r"yaml\.load\s*\(",
        "severity": "high",
        "importance_percent": 85,
        "issue": "yaml.load() detected.",
        "why": "yaml.load() can be unsafe with untrusted YAML input.",
        "fix": "Use yaml.safe_load() instead.",
    },
    {
        "id": "requests_verify_false",
        "pattern": r"verify\s*=\s*False",
        "severity": "medium",
        "importance_percent": 75,
        "issue": "TLS certificate verification appears disabled.",
        "why": "Disabling TLS verification can allow man-in-the-middle attacks.",
        "fix": "Remove verify=False and fix certificate configuration properly.",
    },
    {
        "id": "weak_hash_md5",
        "pattern": r"hashlib\.md5\s*\(",
        "severity": "medium",
        "importance_percent": 70,
        "issue": "MD5 hashing detected.",
        "why": "MD5 is cryptographically weak and should not be used for security-sensitive hashing.",
        "fix": "Use SHA-256 or a password hashing algorithm like bcrypt/argon2 where appropriate.",
    },
    {
        "id": "weak_hash_sha1",
        "pattern": r"hashlib\.sha1\s*\(",
        "severity": "medium",
        "importance_percent": 70,
        "issue": "SHA1 hashing detected.",
        "why": "SHA1 is cryptographically weak for security-sensitive use cases.",
        "fix": "Use SHA-256 or stronger alternatives.",
    },
    {
        "id": "sql_string_format",
        "pattern": r"\.execute\s*\(.*(%|\.format\(|f[\"'])",
        "severity": "high",
        "importance_percent": 90,
        "issue": "Possible SQL query built using string formatting.",
        "why": "String-formatted SQL can lead to SQL injection if variables come from user input.",
        "fix": "Use parameterized queries instead of string formatting.",
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


def security_scan_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Static security scanner.

    It checks risky patterns such as:
    - eval / exec
    - os.system
    - subprocess shell=True
    - debug=True
    - open CORS
    - pickle load
    - unsafe yaml.load
    - verify=False
    - weak hashing
    - simple SQL string formatting
    """

    _append_log(state, "Running security_scan_tool...")

    try:
        files = state.get("repo_files", [])
        repo_root = _repo_root(state)

        findings: list[Finding] = []
        scanned_files = 0

        compiled_rules = [
            {
                **rule,
                "compiled": re.compile(rule["pattern"], re.IGNORECASE),
            }
            for rule in SECURITY_RULES
        ]

        for relative_path in files:
            if not _should_scan(relative_path):
                continue

            scanned_files += 1
            text = _read_text(repo_root, relative_path)

            for line_number, line in enumerate(text.splitlines(), start=1):
                for rule in compiled_rules:
                    if rule["compiled"].search(line):
                        findings.append(
                            Finding(
                                category="security",
                                severity=rule["severity"],
                                importance_percent=rule["importance_percent"],
                                file=relative_path,
                                line=line_number,
                                issue=rule["issue"],
                                why_it_matters=rule["why"],
                                suggested_fix=rule["fix"],
                                source_tool="security_scan_tool",
                            )
                        )

        status = "passed" if not findings else "failed"

        result = ToolResult(
            tool_name="security_scan_tool",
            status=status,
            summary=(
                "Security scan completed with no risky patterns found."
                if not findings
                else f"Security scan found {len(findings)} issue(s)."
            ),
            findings=findings,
            raw_data={
                "scanned_files": scanned_files,
                "rules_count": len(SECURITY_RULES),
            },
        )

        _append_tool_result(state, result)

        if findings:
            state.setdefault("findings", [])
            state["findings"].extend(findings)

        _append_log(state, "security_scan_tool completed.")
        return state

    except Exception as exc:
        finding = Finding(
            category="security",
            severity="high",
            importance_percent=85,
            file=None,
            line=None,
            issue="Security scan crashed.",
            why_it_matters="Security scanning is needed to catch risky code patterns before review completion.",
            suggested_fix=str(exc),
            source_tool="security_scan_tool",
        )

        result = ToolResult(
            tool_name="security_scan_tool",
            status="failed",
            summary="Security scan failed.",
            findings=[finding],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        state.setdefault("findings", [])
        state["findings"].append(finding)

        return state