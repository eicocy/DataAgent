from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalysisStep(StrictModel):
    step_id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    name: str = ""
    description: str = ""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    source_ref: str = "dataset"
    required: bool = True
    status: Literal["PENDING", "READY", "RUNNING", "COMPLETED", "FAILED", "SKIPPED", "WAITING", "CANCELLED"] = "PENDING"
    result_ref: str | None = None
    error: str | None = None
    retry_count: int = Field(default=0, ge=0)


class AnalysisPlan(StrictModel):
    """Persisted v2 plan. ExecutionPlan remains a reader for historical v1 plans."""
    version: Literal["2.0"] = "2.0"
    plan_id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    goal: str
    intent: str
    dataset_id: int
    dataset_version_id: int
    steps: list[AnalysisStep]
    expected_outputs: list[str] = Field(default_factory=list)
    status: Literal["PENDING", "READY", "RUNNING", "COMPLETED", "PARTIAL_SUCCESS", "FAILED", "WAITING", "CANCELLED"] = "PENDING"
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExecutionPlan(StrictModel):
    version: Literal["1.0"] = "1.0"
    intent: str = Field(max_length=500)
    steps: list[AnalysisStep] = Field(min_length=1, max_length=8)
    completion_requirements: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_dependencies(self):
        from app.tools.registry import tool_registry
        allowed = set(tool_registry())
        seen = set()
        for step in self.steps:
            if step.step_id in seen or step.tool_name not in allowed:
                raise ValueError("Duplicate step or unknown tool")
            if any(ref not in seen for ref in step.depends_on):
                raise ValueError("Dependencies must reference earlier steps")
            if step.source_ref != "dataset" and step.source_ref not in seen:
                raise ValueError("Source must reference an earlier result")
            if step.source_ref != "dataset" and step.source_ref not in step.depends_on:
                raise ValueError("Source must be an explicit dependency")
            seen.add(step.step_id)
        if any(ref not in seen for ref in self.completion_requirements):
            raise ValueError("Unknown completion requirement")
        return self


class FinalReport(StrictModel):
    version: Literal["1.0"] = "1.0"
    status: Literal["succeeded", "partial", "failed"]
    answer: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    incomplete_steps: list[str] = Field(default_factory=list)


class Evidence(StrictModel):
    evidence_id: str
    source_type: Literal['tool_artifact'] = 'tool_artifact'
    dataset_id: int
    dataset_version_id: int
    step_id: str
    tool_name: str | None = None
    artifact_id: int
    result_ref: str
    fact_path: list[str | int]
    key: str


class Insight(StrictModel):
    title: str
    description: str
    importance: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    dimensions: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None


class AgentResponse(StrictModel):
    task_id: str
    conversation_id: str
    status: str
    intent: str | None = None
    answer: str = ''
    summary: str | None = None
    insights: list[Insight] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    files: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    plan_summary: dict[str, Any] | None = None
    clarification: dict[str, Any] | None = None


class AgentState(StrictModel):
    record_id: int | None = None
    session_id: int | None = None
    dataset_id: int
    query: str
    metadata: dict[str, Any]
    plan: ExecutionPlan | None = None
    current_step: str | None = None
    result_refs: dict[str, str] = Field(default_factory=dict)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    deadline: float


class ToolCall(StrictModel):
    call_id: str
    step_id: str
    attempt: int = Field(ge=1, le=12)
    tool_name: str
    schema_version: str = "2.0"
    parameters: dict[str, Any]
    source_ref: str
    status: Literal["running", "succeeded", "failed", "skipped"]
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int = 0
    result_summary: str = ""
    artifact_id: int | None = None
    error_code: str | None = None
