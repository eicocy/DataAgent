from fastapi import APIRouter, Depends

from app.config import get_settings
from app.dependencies import current_user
from app.models import User

router = APIRouter(prefix='/workspace', tags=['workspace'])


@router.get('/capabilities')
def capabilities(user: User = Depends(current_user)):
    settings = get_settings()
    provider = settings.llm_provider
    model = settings.deepseek_model if provider == 'deepseek' else settings.openai_model
    configured = bool(settings.deepseek_api_key if provider == 'deepseek' else settings.openai_api_key)
    return {'code': 200, 'message': 'success', 'data': {
        'file_formats': ['csv', 'tsv', 'json', 'xlsx', 'xls', 'parquet'],
        'document_formats': [], 'max_upload_bytes': settings.max_upload_bytes,
        'max_files': 10, 'max_dataset_rows': settings.max_dataset_rows,
        'max_dataset_columns': settings.max_dataset_columns,
        'profile_execution': True, 'multi_dataset_execution': True, 'cross_dataset_join': False,
        'depth_selection': True, 'depths': ['FAST', 'STANDARD', 'DEEP'], 'model_selection': True,
        'models': [{'id': model, 'provider': provider, 'configured': configured}],
        'report_formats': ['online', 'xlsx', 'docx', 'pdf', 'html', 'markdown', 'csv', 'json'],
        'automatic_reports': False, 'sandbox_available': False,
    }}
