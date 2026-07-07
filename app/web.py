from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.graph import run_code_review_graph
from app.schemas import ReviewRequest
from app.state import CodeReviewState


app = FastAPI(
    title="Agentic Code Review Agent",
    description="LangGraph based repository review workflow",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


def build_initial_state(request: ReviewRequest) -> CodeReviewState:
    return {
        "repo_path": request.repo_path or "",
        "repo_url": str(request.repo_url) if request.repo_url else None,
        "repo_files": [],
        "important_files": [],
        "repo_type": "unknown",
        "current_iteration": 0,
        "max_iterations": request.max_iterations,
        "llm_status": "not_used",
        "llm_error": None,
        "fallback_mode": False,
        "tool_decision": None,
        "tool_results": [],
        "findings": [],
        "skipped_tools": [],
        "not_applicable_tools": [],
        "final_report": None,
        "logs": [],
        "metadata": {},
    }


def _serialize_finding(finding: Any) -> dict[str, Any]:
    if hasattr(finding, "model_dump"):
        return finding.model_dump()

    return dict(finding)


def _serialize_tool_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump()

    return dict(result)


def _serialize_final_report(report: Any) -> dict[str, Any] | None:
    if report is None:
        return None

    if hasattr(report, "model_dump"):
        return report.model_dump()

    return dict(report)


def _build_api_response(final_state: CodeReviewState) -> dict[str, Any]:
    final_report = final_state.get("final_report")

    metadata = final_state.get("metadata", {})
    planner_decisions = metadata.get("planner_decisions", [])
    llm_review = metadata.get("llm_review", {})

    return {
        "repo_path": final_state.get("repo_path"),
        "repo_type": final_state.get("repo_type"),
        "repo_files_count": len(final_state.get("repo_files", [])),
        "important_files_count": len(final_state.get("important_files", [])),
        "important_files": final_state.get("important_files", []),
        "llm_status": final_state.get("llm_status"),
        "fallback_mode": final_state.get("fallback_mode"),
        "llm_error": final_state.get("llm_error"),
        "overall_score": final_report.overall_score if final_report else None,
        "final_recommendation": (
            final_report.final_recommendation if final_report else None
        ),
        "project_summary": final_report.project_summary if final_report else None,
        "findings": [
            _serialize_finding(finding)
            for finding in final_state.get("findings", [])
        ],
        "tool_results": [
            _serialize_tool_result(result)
            for result in final_state.get("tool_results", [])
        ],
        "planner_decisions": planner_decisions,
        "llm_review": llm_review,
        "final_report": _serialize_final_report(final_report),
        "report_files": {
            "json": "review_outputs/latest_report.json",
            "markdown": "review_outputs/latest_report.md",
        }
        if final_report
        else None,
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
        },
    )


@app.post("/api/review")
def review_repo(payload: dict[str, Any]):
    repo_path = payload.get("repo_path") or None
    repo_url = payload.get("repo_url") or None
    max_iterations = int(payload.get("max_iterations") or 8)

    try:
        review_request = ReviewRequest(
            repo_path=repo_path,
            repo_url=repo_url,
            max_iterations=max_iterations,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(),
        ) from exc

    initial_state = build_initial_state(review_request)
    final_state = run_code_review_graph(initial_state)

    return JSONResponse(_build_api_response(final_state))


@app.post("/api/review-upload")
async def review_uploaded_zip(
    file: UploadFile = File(...),
    max_iterations: int = Form(8),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a .zip file.",
        )

    temp_root = Path(tempfile.mkdtemp(prefix="uploaded_repo_review_"))
    zip_path = temp_root / file.filename

    try:
        with zip_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        extract_dir = temp_root / "repo"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

        children = [
            child
            for child in extract_dir.iterdir()
            if child.is_dir() and not child.name.startswith("__MACOSX")
        ]

        if len(children) == 1:
            repo_path = children[0]
        else:
            repo_path = extract_dir

        review_request = ReviewRequest(
            repo_path=str(repo_path),
            repo_url=None,
            max_iterations=max_iterations,
        )

        initial_state = build_initial_state(review_request)
        final_state = run_code_review_graph(initial_state)

        return JSONResponse(_build_api_response(final_state))

    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid zip file.",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc