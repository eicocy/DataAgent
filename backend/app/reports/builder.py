from __future__ import annotations

from typing import Any

from app.reports.schemas import DocumentSection, ReportDocument, ReportSection, ReportSpec


class ReportBuilder:
    """Build one bounded document from authorized, same-version run snapshots."""

    def build(
        self,
        spec: ReportSpec,
        sources: list[dict[str, Any]],
        *,
        report_id: int | None = None,
        report_version: int = 1,
    ) -> ReportDocument:
        compatible = [source for source in sources
                      if source.get("dataset_id") == spec.dataset_id
                      and source.get("dataset_version_id") == spec.dataset_version_id
                      and source.get("status") in {"succeeded", "partial"}]
        if not compatible:
            raise ValueError("REPORT_SOURCE_NOT_FOUND")

        evidence_by_id: dict[str, dict[str, Any]] = {}
        artifacts_by_id: dict[int, dict[str, Any]] = {}
        for source in compatible:
            for evidence in source.get("evidence", []):
                evidence_id = evidence.get("evidence_id")
                if evidence_id:
                    evidence_by_id[evidence_id] = evidence
            for artifact in source.get("artifacts", []):
                artifact_id = artifact.get("artifact_id")
                if type(artifact_id) is int:
                    artifacts_by_id[artifact_id] = artifact

        requested_evidence = list(dict.fromkeys(
            evidence_id for section in spec.sections for evidence_id in section.evidence_ids
        ))
        requested_artifacts = list(dict.fromkeys(
            artifact_id for section in spec.sections for artifact_id in section.artifact_refs
        ))
        if any(reference not in evidence_by_id for reference in requested_evidence):
            raise ValueError("REPORT_EVIDENCE_NOT_FOUND")
        if any(reference not in artifacts_by_id for reference in requested_artifacts):
            raise ValueError("REPORT_ARTIFACT_NOT_FOUND")

        sections = self._sections(spec, compatible, evidence_by_id, artifacts_by_id)
        section_evidence = list(dict.fromkeys(
            evidence_id for section in sections for evidence_id in section.evidence_ids
        ))
        section_artifacts = list(dict.fromkeys(
            artifact_id for section in sections for artifact_id in section.artifact_refs
        ))
        return ReportDocument.from_spec(
            spec,
            sections=sections,
            artifacts=section_artifacts,
            evidence=[evidence_by_id[evidence_id] for evidence_id in section_evidence],
            report_id=report_id,
            report_version=report_version,
            metadata={
                "dataset_id": spec.dataset_id,
                "dataset_version_id": spec.dataset_version_id,
                "source_record_ids": [source["record_id"] for source in compatible],
                "source_analysis_count": len(compatible),
            },
        )

    @staticmethod
    def _sections(
        spec: ReportSpec,
        sources: list[dict[str, Any]],
        evidence: dict[str, dict[str, Any]],
        artifacts: dict[int, dict[str, Any]],
    ) -> list[DocumentSection]:
        if spec.sections:
            return [DocumentSection(**dict(
                section.model_dump(exclude={"data"}),
                data=ReportBuilder._section_data(section, sources, evidence, artifacts),
            )) for section in spec.sections]

        summary_text = next((source.get("answer") for source in reversed(sources)
                             if source.get("answer") and source.get("evidence")), None)
        all_evidence = list(evidence)
        result_artifacts = [artifact_id for artifact_id, item in artifacts.items()
                            if item.get("kind") in {"table", "chart"} and not item.get("expired")]
        sections = [
            ReportSection(section_id="executive_summary", title="执行摘要", content_type="insights",
                          narrative=summary_text or "当前分析没有可引用的事实结论。",
                          evidence_ids=all_evidence[:100]),
            ReportSection(section_id="data_overview", title="数据概览", content_type="overview"),
            ReportSection(section_id="key_metrics", title="关键指标", content_type="metrics"),
            ReportSection(section_id="findings", title="核心发现", content_type="insights",
                          evidence_ids=all_evidence[:100]),
            ReportSection(section_id="visualizations", title="图表与明细", content_type="chart",
                          artifact_refs=result_artifacts[:30]),
            ReportSection(section_id="methodology", title="方法与来源", content_type="methods",
                          evidence_ids=all_evidence[:100]),
        ]
        return [DocumentSection(**dict(
            section.model_dump(exclude={"data"}),
            data=ReportBuilder._section_data(section, sources, evidence, artifacts),
        )) for section in sections]

    @staticmethod
    def _section_data(
        section: ReportSection,
        sources: list[dict[str, Any]],
        evidence: dict[str, dict[str, Any]],
        artifacts: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        if section.section_id == "data_overview":
            return {"dataset_id": sources[0]["dataset_id"],
                    "dataset_version_id": sources[0]["dataset_version_id"],
                    "dataset_name": sources[0].get("dataset_name")}
        if section.content_type == "metrics":
            return {"tables": [table for source in sources
                               for table in (source.get("report") or {}).get("tables", [])][:20]}
        if section.content_type == "chart":
            return {"artifacts": [artifacts[item] for item in section.artifact_refs
                                  if item in artifacts][:30]}
        if section.content_type == "methods":
            return {"source_record_ids": [source["record_id"] for source in sources],
                    "evidence_ids": [item for item in section.evidence_ids if item in evidence]}
        if section.content_type == "insights":
            return {"evidence_ids": [item for item in section.evidence_ids if item in evidence]}
        return {}
