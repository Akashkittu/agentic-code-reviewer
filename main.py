import argparse
import json
import sys

from pydantic import ValidationError

from app.graph import run_code_review_graph
from app.schemas import ReviewRequest
from app.state import CodeReviewState


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
        "tool_decision": None,
        "tool_results": [],
        "findings": [],
        "skipped_tools": [],
        "not_applicable_tools": [],
        "final_report": None,
        "logs": [],
        "metadata": {},
    }


def print_tool_trace(state: CodeReviewState) -> None:
    print("\nLangGraph tool execution trace:")

    tool_results = state.get("tool_results", [])

    if not tool_results:
        print("- No tools executed")
        return

    for index, result in enumerate(tool_results, start=1):
        print(
            f"{index}. {result.tool_name} "
            f"-> {result.status.upper()} "
            f"-> {result.summary}"
        )


def print_final_summary(state: CodeReviewState) -> None:
    print("\nFinal state summary:")
    print(f"Repo path: {state.get('repo_path')}")
    print(f"Repo type: {state.get('repo_type')}")
    print(f"Total readable files: {len(state.get('repo_files', []))}")
    print(f"Important files found: {len(state.get('important_files', []))}")
    print(f"Tools executed: {len(state.get('tool_results', []))}")
    print(f"Total findings: {len(state.get('findings', []))}")

    final_report = state.get("final_report")

    if final_report:
        print(f"Overall score: {final_report.overall_score}/100")
        print(f"LLM status: {final_report.llm_status}")
        print(f"Fallback mode: {final_report.fallback_mode}")
        print(f"Final recommendation: {final_report.final_recommendation}")

    print("\nFindings:")
    findings = state.get("findings", [])

    if findings:
        for finding in findings:
            location = ""

            if finding.file:
                location = f" ({finding.file}"

                if finding.line:
                    location += f":{finding.line}"

                location += ")"

            print(
                f"- [{finding.severity.upper()}] "
                f"{finding.issue}{location}"
            )
    else:
        print("- No findings")

    if final_report:
        print("\nGenerated files:")
        print("- review_outputs/latest_report.json")
        print("- review_outputs/latest_report.md")


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

    initial_state = build_initial_state(request)

    print("\nStarting LangGraph workflow...")
    final_state = run_code_review_graph(initial_state)

    print_tool_trace(final_state)
    print_final_summary(final_state)

    tool_results = final_state.get("tool_results", [])

    if tool_results:
        latest_result = tool_results[-1]

        if (
            latest_result.status == "failed"
            and latest_result.tool_name == "repo_loader_tool"
        ):
            print("\nRepo loading failed. Workflow stopped early.")
            sys.exit(400)

    print("\nLangGraph workflow completed.")
    print(
        "\nNext step will add LLM provider fallback: "
        "OpenAI -> Gemini -> Claude -> static fallback."
    )


if __name__ == "__main__":
    main()