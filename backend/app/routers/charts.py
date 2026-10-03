from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import current_user
from app.models import User
from app.routers.analysis_runs import owned_artifact
from app.services.artifacts import ArtifactStore
from app.services.analysis import domain_error

router = APIRouter(prefix="/charts", tags=["charts"])


class ChartResponse(BaseModel):
    code: int
    message: str
    data: dict


@router.get("/{artifact_id}", response_model=ChartResponse)
def chart(artifact_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    artifact = owned_artifact(db, artifact_id, user.id)
    if artifact.kind != "chart":
        raise domain_error(404, "CHART_NOT_FOUND", "图表不存在")
    try:
        payload = ArtifactStore(db).read(artifact)
    except LookupError:
        raise domain_error(410, "ARTIFACT_EXPIRED", "图表完整结果已过期") from None
    return {"code": 200, "message": "success", "data": dict(payload["data"], artifact_id=artifact.id)}
