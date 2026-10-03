import pytest
from pydantic import ValidationError

from app.reports.schemas import ReportDocument, ReportSection, ReportSpec


def test_report_spec_preserves_evidence_and_artifact_refs_in_document():
    spec = ReportSpec(
        title="2026 年销售分析报告",
        report_type="sales",
        sections=[ReportSection(
            section_id="summary",
            title="执行摘要",
            content_type="insights",
            narrative="{region}销售额为{amount}。",
            artifact_refs=[23],
            evidence_ids=["run-5:summary:amount"],
        )],
        dataset_id=7,
        dataset_version_id=19,
    )
    document = ReportDocument.from_spec(spec, metadata={"dataset_name": "sales.xlsx"})

    assert document.title == spec.title
    assert document.sections[0].evidence_ids == ["run-5:summary:amount"]
    assert document.sections[0].artifact_refs == [23]
    assert document.metadata["dataset_version_id"] == 19


@pytest.mark.parametrize("change", [
    {"title": ""},
    {"sections": [{"section_id": "bad id", "title": "章节", "content_type": "narrative"}]},
    {"dataset_version_id": 0},
])
def test_report_spec_rejects_invalid_or_unbounded_inputs(change):
    payload = {"title": "分析报告", "dataset_id": 3, "dataset_version_id": 4, **change}

    with pytest.raises(ValidationError):
        ReportSpec.model_validate(payload)
