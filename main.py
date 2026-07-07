import argparse
import json
import sys

from pydantic import ValidationError

from app.schemas import ReviewRequest
from app.state import CodeReviewState
from app.tools.code_search import code_search_tool
from app.tools.dependency_check import dependency_check_tool
from app.tools.readme_review import readme_review_tool
from app.tools.report_generator import report_generator_tool
from app.tools.test_discovery import test_discovery_tool
from app.tools.env_config_check import env_config_check_tool
from app.tools.repo_loader import repo_loader_tool
from app.tools.repo_structure import repo_structure_tool
from app.tools.security_scan import security_scan_tool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agentic GitHub Repository Code Review Agent"
    )

    input_group = parser.add_mutually_exclusive_group(required=True)

    input_group.add_argument(
        "--repo",
        dest="repo_path",
        help="Local repository path, example: ./sample_repo",
    )

    input_group.add_argument(
        "--repo-url",
        dest="repo_url",
        help="Public GitHub repository URL",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=4,
        help="Maximum LangGraph iterations. Default: 4",
    )

    return parser.parse_args()


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
        "tool_results": [],
        "findings": [],
        "skipped_tools": [],
        "not_applicable_tools": [],
        "final_report": None,
        "logs": [],
        "metadata": {},
    }


def print_tool_result(title: str, state: CodeReviewState) -> None:
    latest_result = state["tool_results"][-1]

    print(f"\n{title}:")
    print(latest_result.model_dump_json(indent=2))


def main() -> None:
    args = parse_args()

    try:
        request = ReviewRequest(
            repo_path=args.repo_path,
            repo_url=args.repo_url,
            max_iterations=args.max_iterations,
        )
    except ValidationError as exc:
        print("Input validation failed.")
        print(exc)
        sys.exit(422)

    print("Input validation passed.")
    print(json.dumps(request.model_dump(mode="json"), indent=2))

    state = build_initial_state(request)

    print("\nRunning repo loader...")
    state = repo_loader_tool(state)
    print_tool_result("Repo loader result", state)

    if state["tool_results"][-1].status == "failed":
        print("\nRepo loading failed. Stopping workflow.")
        sys.exit(400)

    print("\nRunning repo structure analyzer...")
    state = repo_structure_tool(state)
    print_tool_result("Repo structure result", state)

    print("\nRunning dependency checker...")
    state = dependency_check_tool(state)
    print_tool_result("Dependency check result", state)

    print("\nRunning env/config checker...")
    state = env_config_check_tool(state)
    print_tool_result("Env/config check result", state)

    print("\nRunning security scanner...")
    state = security_scan_tool(state)
    print_tool_result("Security scan result", state)

    print("\nRunning code search...")
    state = code_search_tool(state)
    print_tool_result("Code search result", state)

    print("\nRunning test discovery...")
    state = test_discovery_tool(state)
    print_tool_result("Test discovery result", state)

    print("\nRunning README review...")
    state = readme_review_tool(state)
    print_tool_result("README review result", state)

    print("\nGenerating final report...")
    state = report_generator_tool(state)
    print_tool_result("Report generator result", state)

    print("\nCurrent state summary:")
    print(f"Repo path: {state['repo_path']}")
    print(f"Repo type: {state['repo_type']}")
    print(f"Total readable files: {len(state['repo_files'])}")
    print(f"Important files found: {len(state['important_files'])}")

    print("\nLanguages:")
    for language in state["metadata"].get("languages", []):
        print(f"- {language}")

    print("\nFrameworks:")
    frameworks = state["metadata"].get("frameworks", [])
    if frameworks:
        for framework in frameworks:
            print(f"- {framework}")
    else:
        print("- None detected")

    print("\nMain files:")
    main_files = state["metadata"].get("main_files", [])
    if main_files:
        for file_path in main_files:
            print(f"- {file_path}")
    else:
        print("- No obvious main file found")

    print("\nFolder signals:")
    for key, value in state["metadata"].get("folders", {}).items():
        print(f"- {key}: {value}")

    print("\nFindings so far:")
    if state["findings"]:
        for finding in state["findings"]:
            print(f"- [{finding.severity.upper()}] {finding.issue}")
    else:
        print("- No findings yet")

    print("\nNext step will add dependency_check_tool and env_config_check_tool.")


if __name__ == "__main__":
    main()