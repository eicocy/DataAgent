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
    from app.sandbox.settings import get_sandbox_settings
    from app.sandbox.client import SandboxClient
    from app.sandbox.validator import SandboxError
    sandbox=get_sandbox_settings()
    sandbox_status='disabled'
    if sandbox.enabled:
        try:
            SandboxClient(sandbox).health(); sandbox_status='available'
        except SandboxError: sandbox_status='unavailable'
    return {'code': 200, 'message': 'success', 'data': {
        'file_formats': ['csv', 'tsv', 'json', 'jsonl', 'xlsx', 'xls', 'parquet'],
        'document_formats': ['txt','pdf','docx'], 'max_upload_bytes': settings.max_upload_bytes,
        'max_files': 10, 'max_dataset_rows': settings.max_dataset_rows,
        'max_dataset_columns': settings.max_dataset_columns,
        'profile_execution': True, 'multi_dataset_execution': True, 'cross_dataset_join': True,
        'cleaning_confirmation': True,
        'depth_selection': True, 'depths': ['FAST', 'STANDARD', 'DEEP'], 'model_selection': True,
        'models': [{'id': model, 'provider': provider, 'configured': configured}],
        'report_formats': ['online', 'xlsx', 'docx', 'pdf', 'html', 'markdown', 'csv', 'json', 'python', 'sql'],
        'report_templates': [{'id':key,'name':label} for key,label in [('auto','自动'),('quick','快速'),('detailed','详细'),('executive','管理层'),('technical','技术'),('data_quality','质量'),('forecast','预测')]],
        'automatic_reports': True, 'artifact_references': True, 'sandbox_available': sandbox_status=='available',
        'sandbox': {'enabled':sandbox.enabled,'status':sandbox_status,'max_seconds':60,
            'max_memory_mb':512,'max_output_mb':64,'scope':'internal_analysis_fallback'},
    }}
