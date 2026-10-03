from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ReportSection(ReportModel):
    section_id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=160)
    content_type: Literal["narrative", "insights", "metrics", "table", "chart", "overview", "methods"]
    narrative: str | None = Field(default=None, max_length=6000)
    artifact_refs: list[int] = Field(default_factory=list, max_length=30)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    children: list[ReportSection] = Field(default_factory=list, max_length=20)


class ReportSpec(ReportModel):
    title: str = Field(min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=500)
    report_type: Literal["general", "executive", "sales", "financial", "operations", "data_quality"] = "general"
    template: Literal["auto", "general", "executive", "sales", "financial", "operations", "data_quality"] = "auto"
    author: str | None = Field(default=None, max_length=120)
    sections: list[ReportSection] = Field(default_factory=list, max_length=20)
    theme: Literal["professional", "minimal"] = "professional"
    include_toc: bool = True
    include_timestamp: bool = True
    dataset_id: int = Field(gt=0)
    dataset_version_id: int = Field(gt=0)
    report_id: int | None = Field(default=None, gt=0)
    base_version: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def unique_section_ids(self):
        ids = [section.section_id for section in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("Report section IDs must be unique")
        return self


class DocumentSection(ReportSection):
    data: dict[str, Any] = Field(default_factory=dict)


class ReportDocument(ReportModel):
    version: Literal["2.0"] = "2.0"
    document_id: str = Field(default_factory=lambda: uuid4().hex)
    report_id: int | None = None
    report_version: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=255)
    subtitle: str | None = None
    report_type: str
    theme: Literal["professional", "minimal"]
    author: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    sections: list[DocumentSection] = Field(max_length=20)
    artifacts: list[int] = Field(default_factory=list, max_length=100)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    generated_at: datetime
    include_toc: bool = True

    @classmethod
    def from_spec(
        cls,
        spec: ReportSpec,
        *,
        metadata: dict[str, Any] | None = None,
        sections: list[DocumentSection] | None = None,
        artifacts: list[int] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        report_id: int | None = None,
        report_version: int = 1,
        generated_at: datetime | None = None,
    ) -> ReportDocument:
        payload = dict(metadata or {})
        payload.setdefault("dataset_id", spec.dataset_id)
        payload.setdefault("dataset_version_id", spec.dataset_version_id)
        return cls(
            report_id=report_id or spec.report_id,
            report_version=report_version,
            title=spec.title,
            subtitle=spec.subtitle,
            report_type=spec.report_type,
            theme=spec.theme,
            author=spec.author,
            metadata=payload,
            sections=sections if sections is not None else [
                DocumentSection(**dict(section.model_dump(exclude={"data"}), data={}))
                for section in spec.sections
            ],
            artifacts=list(dict.fromkeys(artifacts or [
                ref for section in spec.sections for ref in section.artifact_refs
            ])),
            evidence=evidence or [],
            generated_at=generated_at or datetime.now(UTC),
            include_toc=spec.include_toc,
        )
