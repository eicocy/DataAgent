from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import current_user
from app.models import User, AnalysisArtifact, AnalysisRecord, ToolExecutionRecord
from app.services.artifacts import ArtifactStore
from app.services.analysis import domain_error
from app.charts.renderer import ChartRenderer, chart_spec_from_legacy
from app.artifacts.storage import LocalArtifactStorage
from app.config import get_settings
from app.artifacts.manager import ArtifactManager

router = APIRouter(prefix="/charts", tags=["charts"])


def _owned_chart_artifact(db: Session, artifact_id: int, user_id: int):
    artifact = db.get(AnalysisArtifact, artifact_id)
    if not artifact or artifact.user_id != user_id:
        raise domain_error(404, "ARTIFACT_NOT_FOUND", "结果不存在")
    owner = (db.get(AnalysisRecord, artifact.record_id) if artifact.record_id else
             db.get(ToolExecutionRecord, artifact.tool_execution_id) if artifact.tool_execution_id else None)
    if not owner or owner.user_id != user_id:
        raise domain_error(404, "ARTIFACT_NOT_FOUND", "结果不存在")
    if artifact.kind != "chart":
        raise domain_error(404, "CHART_NOT_FOUND", "图表不存在")
    return artifact


class ChartResponse(BaseModel):
    code: int
    message: str
    data: dict


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chart_type: str | None = Field(default=None, max_length=20)
    formats: list[str] = Field(default_factory=lambda: ["svg", "png", "thumbnail"], min_length=1, max_length=3)


@router.get("/{artifact_id}", response_model=ChartResponse)
def chart(artifact_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artifact = _owned_chart_artifact(db, artifact_id, user.id)
    try:
        payload = ArtifactStore(db).read(artifact)
    except LookupError:
        raise domain_error(410, "ARTIFACT_EXPIRED", "图表完整结果已过期") from None
    return {"code": 200, "message": "success", "data": dict(payload["data"], artifact_id=artifact.id)}


@router.post("/{artifact_id}/render", status_code=201)
def render_chart(artifact_id: int, request: RenderRequest,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    source = _owned_chart_artifact(db, artifact_id, user.id)
    try:
        payload = ArtifactStore(db).read(source).get("data") or {}
        spec_payload = chart_spec_from_legacy(payload, chart_type=request.chart_type)
        if request.chart_type:
            spec_payload["chart_type"] = request.chart_type
        rendered = ChartRenderer().render(spec_payload)
    except LookupError:
        raise domain_error(410, "ARTIFACT_EXPIRED", "图表源数据已过期") from None
    except Exception as error:
        code = str(error) if str(error).startswith("CHART_") else "CHART_RENDER_FAILED"
        raise domain_error(422, code, "高清图表生成失败") from None

    owner_record = db.get(AnalysisRecord, source.record_id) if source.record_id else None
    owner_tool = db.get(ToolExecutionRecord, source.tool_execution_id) if source.tool_execution_id else None
    if (source.record_id and not owner_record) or (source.tool_execution_id and not owner_tool):
        raise domain_error(404, "CHART_NOT_FOUND", "图表不存在")
    storage = LocalArtifactStorage(get_settings().artifact_dir)
    content_by_format = {"svg": ("svg", rendered.svg), "png": ("png", rendered.png),
                         "thumbnail": ("png", rendered.thumbnail_png)}
    if any(item not in content_by_format for item in request.formats):
        raise domain_error(422, "CHART_FORMAT_UNSUPPORTED", "图表格式不支持")
    now = datetime.now(UTC).replace(tzinfo=None)
    manager = ArtifactManager(db)
    try: manager.check_quota(user.id,sum(len(content_by_format[name][1]) for name in dict.fromkeys(request.formats)))
    except ValueError as error: raise domain_error(409,str(error),'成果容量不足，请删除不再需要的成果后重试') from None
    created = []
    for format_name in dict.fromkeys(request.formats):
        extension, content = content_by_format[format_name]
        row = AnalysisArtifact(session_id=manager.session_id(source), retention_class='final', record_id=source.record_id,
            tool_execution_id=source.tool_execution_id, report_version_id=None,
            user_id=source.user_id, dataset_id=source.dataset_id, step_id=f"chart_render_{format_name}",
            kind="chart", stored_name=f"{uuid4().hex}.json", size_bytes=len(content), row_count=0,
            schema_json={"columns": [], "types": {}, "version": "2.0"}, created_at=now,
            expires_at=None,
            status="READY", metadata_json={"source_artifact_id": source.id, 'source_artifact_ids':[source.id],
                'dataset_versions':(source.metadata_json or {}).get('dataset_versions',[]), "chart_type": request.chart_type or payload.get("chart_type") or payload.get("type"),
                "width": rendered.width if format_name != "thumbnail" else 600,
                "height": rendered.height if format_name != "thumbnail" else 360,
                "dpi": rendered.dpi if format_name == "png" else None})
        db.add(row); db.flush()
        saved = storage.save(user_id=user.id, conversation_id=owner_record.session_id if owner_record else owner_tool.analysis_record_id or owner_tool.id,
            task_id=owner_record.id if owner_record else owner_tool.id,
            artifact_id=row.id, file_name=f"{payload.get('title') or 'chart'}_{format_name}.{extension}", content=content)
        row.storage_key, row.file_name = saved.storage_key, saved.file_name
        row.mime_type = "image/svg+xml" if extension == "svg" else "image/png"
        created.append(row)
    manager.protect(source)
    db.commit()
    return {"code": 201, "message": "created", "data": [{
        "artifact_id": row.id, "artifact_type": "CHART", "file_name": row.file_name,
        "mime_type": row.mime_type, "size_bytes": row.size_bytes,
        "preview_url": f"/api/v1/artifacts/{row.id}/preview",
        "download_url": f"/api/v1/artifacts/{row.id}/download"} for row in created]}
