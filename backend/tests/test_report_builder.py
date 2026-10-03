import pytest

from app.reports.schemas import ReportSection, ReportSpec
from app.reports.builder import ReportBuilder


def source(record_id=31, *, version=19):
    return {
        "record_id": record_id,
        "dataset_id": 7,
        "dataset_version_id": version,
        "status": "succeeded",
        "answer": "华南销售额为 40。",
        "report": {"tables": [{"artifact_id": 23, "columns": ["region", "sales"]}]},
        "evidence": [{"evidence_id": "run-31:summary:sales", "dataset_version_id": version}],
        "artifacts": [{"artifact_id": 23, "kind": "table", "expired": False}],
    }


def spec(sections=None):
    return ReportSpec(title="销售报告", dataset_id=7, dataset_version_id=19, sections=sections or [])


def test_report_builder_creates_default_sections_from_same_version_evidence_and_artifacts():
    document = ReportBuilder().build(spec(), [source()], report_id=9, report_version=2)

    summary = document.sections[0]
    assert document.report_id == 9
    assert document.report_version == 2
    assert summary.narrative == "华南销售额为 40。"
    assert summary.evidence_ids == ["run-31:summary:sales"]
    assert document.metadata["source_record_ids"] == [31]
    assert 23 in document.artifacts


def test_report_builder_ignores_sources_from_a_different_dataset_version():
    with pytest.raises(ValueError, match="REPORT_SOURCE_NOT_FOUND"):
        ReportBuilder().build(spec(), [source(version=20)])


def test_report_builder_rejects_evidence_or_artifacts_outside_authorized_sources():
    request = spec([ReportSection(
        section_id="summary", title="摘要", content_type="insights",
        artifact_refs=[999], evidence_ids=["forged"],
    )])

    with pytest.raises(ValueError, match="REPORT_EVIDENCE_NOT_FOUND"):
        ReportBuilder().build(request, [source()])
