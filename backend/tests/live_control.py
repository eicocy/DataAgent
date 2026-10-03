"""Explicit opt-in fault injection for the real browser acceptance suite.

Only new p3_live_* test users and their own records can be changed. No model
credentials or database passwords are needed by the browser test process.
"""
import json
import os
import subprocess
import sys


def main():
    container = os.environ.get('LIVE_E2E_CONTROL_CONTAINER')
    if not container:
        raise RuntimeError('LIVE_E2E_CONTROL_CONTAINER_REQUIRED')
    action, record_id = sys.argv[1], int(sys.argv[2])
    if action not in {'expire', 'version-unavailable', 'version-restore', 'context', 'metadata'}:
        raise ValueError('UNKNOWN_CONTROL_ACTION')
    code = f'''
import json
from datetime import datetime, UTC, timedelta
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User, AnalysisRecord, AnalysisArtifact, DatasetVersion, AnalysisSession, LLMCallRecord
with SessionLocal() as db:
    record = db.get(AnalysisRecord, {record_id})
    assert record and db.get(User,record.user_id).username.startswith('p3_live_')
    action = {action!r}
    if action == 'expire':
        artifacts=list(db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.user_id==record.user_id,AnalysisArtifact.dataset_id==record.dataset_id)))
        for artifact in artifacts: artifact.expires_at=datetime.now(UTC)-timedelta(days=1)
        result={{'expired_artifacts':len(artifacts)}}
    elif action.startswith('version-'):
        version=db.get(DatasetVersion,record.dataset_version_id)
        assert version and version.dataset_id==record.dataset_id
        version.status='ready' if action=='version-restore' else 'failed'
        result={{'version_status':version.status}}
    elif action == 'metadata':
        calls=list(db.scalars(select(LLMCallRecord).where(LLMCallRecord.record_id==record.id,LLMCallRecord.user_id==record.user_id)))
        fields=('provider','model','prompt_version','input_tokens','output_tokens','latency_ms','status','error_code')
        result={{'calls':[{{name:getattr(call,name) for name in fields}} for call in calls],
                'stored_fields':list(LLMCallRecord.__table__.columns.keys())}}
    else:
        context=db.get(AnalysisSession,record.session_id).context_json or {{}}
        result={{'filters':context.get('active_filters',[]),'metrics':context.get('active_metrics',[])}}
    db.commit()
    print(json.dumps(result))
'''
    result = subprocess.run(['docker', 'exec', '-i', container, 'python', '-'],
                            input=code, text=True, capture_output=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('LIVE_CONTROL_FAILED')
    print(result.stdout)


if __name__ == '__main__':
    main()
