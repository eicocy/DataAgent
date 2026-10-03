from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import current_user
from app.models import User
from app.profiles.catalog import profile_catalog
from app.database import get_db
from app.profiles.service import ProfileService

router = APIRouter(prefix='/analysis/profiles', tags=['profiles'])


@router.get('')
def list_profiles(category: str | None = None, user: User = Depends(current_user), db=Depends(get_db)):
    service = ProfileService(db)
    service.seed()
    db.commit()
    return {'code': 200, 'message': 'success', 'data': service.catalog(category)}


@router.get('/{profile_id}')
def get_profile(profile_id: str, user: User = Depends(current_user), db=Depends(get_db)):
    service = ProfileService(db)
    service.seed()
    db.commit()
    item = next((p for p in service.catalog()['items'] if p['id'] == profile_id), None)
    if item is None:
        raise HTTPException(404, detail={'code': 'PROFILE_NOT_FOUND', 'message': '分析模板不存在'})
    return {'code': 200, 'message': 'success', 'data': item}
