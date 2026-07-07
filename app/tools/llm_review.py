from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.llm.fallback_manager import FallbackLLMManager
from app.schemas import ToolResult
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


def _read_text(repo_root: Path, relative_path: str, max_chars: int = 6000) -> str:
    path = repo_root / relative_path

    if not path.exists() or not path.is_file():
        return ""

    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def _collect_file_context(state: CodeReviewState) -> str:
    repo_root = _repo_root(state)

    important_files = state.get("important_files", [])
    selected_files = important_files[: settings.MAX_FILES_SENT_TO_LLM]

    chunks: list[str] = []

    for file_path in selected_files:
        text = _read_text(repo_root, file_path)

        if not text.strip():
            continue

        chunks.append(
            f"\n--- FILE: {file_path} ---\n{text}\n--- END FILE: {file_path} ---"
        )

    return "\n".join(chunks)


def _build_prompt(state: CodeReviewState) -> str:
    findings = state.get("findings", [])

    finding_lines: list[str] = []

    for finding in findings[:30]:
        location = finding.file or "N/A"

        if finding.line:
            location += f":{finding.line}"

        finding_lines.append(
            f"- Severity: {finding.severity}; "
            f"Category: {finding.category}; "
            f"Location: {location}; "
            f"Issue: {finding.issue}; "
            f"Suggested fix: {finding.suggested_fix}"
        )

    findings_text = "\n".join(finding_lines) if finding_lines else "No findings yet."

    file_context = _collect_file_context(state)

    return f"""
You are reviewing a repository as part of an agentic code review workflow.

Repo type:
{state.get("repo_type", "unknown")}

Detected metadata:
{state.get("metadata", {})}

Static tool findings:
{findings_text}

Important file snippets:
{file_context}

Your task:
1. Give a concise senior-reviewer summary.
2. Identify the top 3 fixes in priority order.
3. Mention whether the repo is ready for take-home assignment demo.
4. Mention one limitation of this prototype and one next improvement.

Rules:
- Do not invent files that are not shown.
- Do not claim tests passed unless test output is provided.
- Keep output under 500 words.
"""


def llm_review_tool(state: CodeReviewState) -> CodeReviewState:
    """
    Runs LLM review with fallback:

    OpenAI -> Gemini -> Claude -> static fallback.

    This tool never crashes the graph.
    If all LLMs fail, it stores static fallback text and marks fallback_mode=True.
    """

    _append_log(state, "Running llm_review_tool...")

    try:
        prompt = _build_prompt(state)
        manager = FallbackLLMManager()
        llm_result = manager.generate(prompt)

        state.setdefault("metadata", {})
        state["metadata"]["llm_review"] = {
            "provider": llm_result.provider,
            "success": llm_result.success,
            "attempted_providers": llm_result.attempted_providers,
            "text": llm_result.text,
            "error": llm_result.error,
        }

        if llm_result.success:
            state["llm_status"] = "success"
            state["llm_error"] = None
            state["fallback_mode"] = False

            result = ToolResult(
                tool_name="llm_review_tool",
                status="passed",
                summary=f"LLM review completed using {llm_result.provider}.",
                findings=[],
                raw_data={
                    "provider": llm_result.provider,
                    "attempted_providers": llm_result.attempted_providers,
                },
            )

        else:
            state["llm_status"] = "failed"
            state["llm_error"] = llm_result.error
            state["fallback_mode"] = True

            result = ToolResult(
                tool_name="llm_review_tool",
                status="failed",
                summary="All LLM providers failed. Static fallback review was used.",
                findings=[],
                raw_data={
                    "provider": llm_result.provider,
                    "attempted_providers": llm_result.attempted_providers,
                    "error": llm_result.error,
                },
            )

        _append_tool_result(state, result)
        _append_log(state, "llm_review_tool completed.")

        return state

    except Exception as exc:
        state["llm_status"] = "failed"
        state["llm_error"] = str(exc)
        state["fallback_mode"] = True

        result = ToolResult(
            tool_name="llm_review_tool",
            status="failed",
            summary="LLM review crashed. Static results are still available.",
            findings=[],
            raw_data={"error": str(exc)},
        )

        _append_tool_result(state, result)
        _append_log(state, f"llm_review_tool failed: {exc}")

        return state