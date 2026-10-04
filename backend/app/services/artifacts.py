import json
import os
import re
import uuid
from datetime import datetime, timedelta, UTC
from pathlib import Path
from sqlalchemy import select, func
from app.config import get_settings
from app.models import AnalysisArtifact
from app.analysis.serialization import records as _records


class ArtifactStore:
    def __init__(self, db, settings=None):
        self.db, self.settings = db, settings or get_settings()
        self.root = Path(self.settings.artifact_dir).resolve()

    def _path(self, name):
        if not re.fullmatch(r"[a-f0-9]{32}\.json", name):
            raise ValueError("Invalid artifact name")
        path = (self.root / name).resolve()
        if path.parent != self.root:
            raise ValueError("Invalid artifact path")
        return path

    def write(self, record, step_id, data, frame=None, kind="table", independent=False, stored_name=None):
        columns = [str(x) for x in frame.columns] if frame is not None else list(data.get("columns") or [])
        columns = [str(column.get("name", column.get("field", ""))) if isinstance(column, dict) else str(column) for column in columns]
        schema = {"columns": columns, "types": {str(k): str(v) for k, v in frame.dtypes.items()} if frame is not None else {}, "version": "1.0"}
        rows = _records(frame) if frame is not None else data.get("rows", data.get("preview_rows", data.get("sorted_rows", [])))
        payload = {"schema": schema, "rows": rows, "data": data if kind == "chart" or frame is None else {k: v for k, v in data.items() if k not in {"rows", "preview_rows", "sorted_rows"}}}
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")
        owner = AnalysisArtifact.tool_execution_id if independent else AnalysisArtifact.record_id
        used = self.db.scalar(select(func.coalesce(func.sum(AnalysisArtifact.size_bytes), 0)).where(owner == record.id)) or 0
        if len(encoded) > self.settings.artifact_max_bytes or used + len(encoded) > self.settings.artifact_task_max_bytes:
            raise ValueError("Artifact budget exceeded")
        from app.artifacts.manager import ArtifactManager
        ArtifactManager(self.db, self.settings).check_quota(record.user_id, len(encoded))
        self.root.mkdir(parents=True, exist_ok=True)
        name = stored_name or uuid.uuid4().hex + ".json"
        path = self._path(name)
        temp = path.with_suffix(".part")
        try:
            temp.write_bytes(encoded)
            os.replace(temp, path)
            now = datetime.now(UTC).replace(tzinfo=None)
            from app.models import AnalysisRecord
            owner_record = self.db.get(AnalysisRecord, record.id) if not independent else None
            artifact = AnalysisArtifact(session_id=owner_record.session_id if owner_record else None, record_id=None if independent else record.id, tool_execution_id=record.id if independent else None, user_id=record.user_id, dataset_id=record.dataset_id, step_id=step_id, kind=kind,
                                        stored_name=name, size_bytes=len(encoded), row_count=len(rows), schema_json=schema, created_at=now,
                                        expires_at=now + timedelta(days=self.settings.artifact_retention_days))
            self.db.add(artifact)
            self.db.flush()
        except Exception:
            temp.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            raise
        from app.agent.executor import clip_context
        preview = clip_context(dict(data, columns=columns, rows=rows[:100]), max_rows=100)
        # An overview's row_count describes the dataset, while total describes
        # result-table rows. Empty result rows must not overwrite that fact.
        if frame is not None: preview['row_count'] = len(rows)
        else: preview.setdefault('row_count',len(rows))
        return dict(preview, artifact_id=artifact.id, total=len(rows))

    def read(self, artifact):
        if artifact.purged_at or (artifact.expires_at is not None and artifact.expires_at <= datetime.now(UTC).replace(tzinfo=None)):
            raise LookupError("ARTIFACT_EXPIRED")
        try:
            return json.loads(self._path(artifact.stored_name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise LookupError("ARTIFACT_EXPIRED") from None
