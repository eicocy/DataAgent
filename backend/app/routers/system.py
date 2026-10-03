from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user
from app.models import AnalysisRecord, AnalysisSession, Dataset, User


router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def dashboard_summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    dataset_count = db.scalar(select(func.count()).select_from(Dataset).where(Dataset.user_id == user.id)) or 0
    record_count = db.scalar(select(func.count()).select_from(AnalysisRecord).where(AnalysisRecord.user_id == user.id)) or 0
    session_count = db.scalar(select(func.count()).select_from(AnalysisSession).where(AnalysisSession.user_id == user.id)) or 0
    ready_count = db.scalar(
        select(func.count()).select_from(Dataset).where(Dataset.user_id == user.id, Dataset.status == "ready")
    ) or 0
    recent = db.execute(
        select(AnalysisRecord, Dataset.original_name)
        .join(Dataset, Dataset.id == AnalysisRecord.dataset_id)
        .where(AnalysisRecord.user_id == user.id)
        .order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id.desc())
        .limit(5)
    ).all()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "dataset_count": dataset_count,
            "ready_dataset_count": ready_count,
            "analysis_count": record_count,
            "session_count": session_count,
            "recent_analyses": [
                {"id": record.id, "question": record.question, "dataset_id": record.dataset_id, "dataset_name": dataset_name,
                 "status": record.status, "primary_tool_name": record.primary_tool_name, "created_at": record.created_at.isoformat()}
                for record, dataset_name in recent
            ],
        },
    }
