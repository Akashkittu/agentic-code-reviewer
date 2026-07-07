from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


AllowedTool = Literal[
    "repo_loader_tool",
    "repo_structure_tool",
    "file_reader_tool",
    "code_search_tool",
    "security_scan_tool",
    "env_config_check_tool",
    "dependency_check_tool",
    "test_discovery_tool",
    "test_runner_tool",
    "lint_runner_tool",
    "format_check_tool",
    "readme_review_tool",
    "repo_hygiene_tool",
    "docker_check_tool",
    "ci_cd_check_tool",
    "api_route_review_tool",
    "database_review_tool",
    "auth_review_tool",
    "performance_review_tool",
    "llm_usage_review_tool",
    "agentic_workflow_review_tool",
    "report_generator_tool",
]


Severity = Literal["info", "low", "medium", "high", "critical"]


class ReviewRequest(BaseModel):
    repo_path: Optional[str] = None
    repo_url: Optional[HttpUrl] = None
    max_iterations: int = Field(default=4, ge=1, le=8)

    @model_validator(mode="after")
    def validate_one_input(self):
        if not self.repo_path and not self.repo_url:
            raise ValueError("Either repo_path or repo_url is required.")

        if self.repo_path and self.repo_url:
            raise ValueError("Provide only one input: repo_path or repo_url, not both.")

        return self


class ToolDecision(BaseModel):
    next_tool: AllowedTool
    reason: str = Field(min_length=3)


class Finding(BaseModel):
    category: str
    severity: Severity
    importance_percent: int = Field(ge=0, le=100)
    file: Optional[str] = None
    line: Optional[int] = None
    issue: str
    why_it_matters: str
    suggested_fix: str
    source_tool: Optional[str] = None


class ToolResult(BaseModel):
    tool_name: str
    status: Literal["passed", "failed", "skipped", "not_applicable"]
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)


class ReviewReport(BaseModel):
    project_summary: str
    repo_type: str
    overall_score: int = Field(ge=0, le=100)
    llm_status: Literal["success", "failed", "not_used"]
    fallback_mode: bool
    findings: list[Finding]
    skipped_tools: list[str] = Field(default_factory=list)
    not_applicable_tools: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    final_recommendation: str