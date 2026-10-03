from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import current_user
from app.models import User
from app.profiles.catalog import profile_catalog

router = APIRouter(prefix='/analysis/profiles', tags=['profiles'])


@router.get('')
def list_profiles(category: str | None = None, user: User = Depends(current_user)):
    return {'code': 200, 'message': 'success', 'data': profile_catalog(category)}


@router.get('/{profile_id}')
def get_profile(profile_id: str, user: User = Depends(current_user)):
    item = next((p for p in profile_catalog()['items'] if p['id'] == profile_id), None)
    if item is None:
        raise HTTPException(404, detail={'code': 'PROFILE_NOT_FOUND', 'message': '分析模板不存在'})
    return {'code': 200, 'message': 'success', 'data': item}
