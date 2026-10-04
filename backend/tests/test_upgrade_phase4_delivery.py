from sqlalchemy import select, func
from test_analysis_api import analysis_context
from test_upgrade_phase4_api import setup_source
from app.models import AnalysisRecord, BackgroundJob, AnalysisArtifact


def prepare_record(db,rid,formats):
    row=db.get(AnalysisRecord,rid)
    row.request_config_json={'depth':'STANDARD','delivery':{'template':'executive','formats':formats},
        'inputs':[{'alias':'primary','dataset_id':row.dataset_id,'dataset_version_id':row.dataset_version_id}]}
    row.plan_json={'version':'3.0','inputs':row.request_config_json['inputs'],'steps':[
        {'step_id':'summary','input_alias':'primary','tool_name':'aggregate','status':'COMPLETED',
         'source_ref':'dataset','arguments':{'metrics':[{'column':'x','aggregation':'sum'}]}}]}
    db.commit(); return row


def test_inline_delivery_uses_current_record_and_no_child_queue(analysis_context):
    client,sessions,_=analysis_context
    rid,sid,aid,did,vid=setup_source(client,sessions)
    with sessions() as db:
        from app.reports.delivery import deliver_record
        row=prepare_record(db,rid,['xlsx','docx','pdf','python'])
        before=db.scalar(select(func.count()).select_from(BackgroundJob))
        result=deliver_record(db,row)
        assert result['status']=='succeeded'
        assert set(result['formats'])=={'xlsx','docx','pdf','python'}
        assert db.scalar(select(func.count()).select_from(BackgroundJob))==before
        assert all(item.expires_at is None for item in db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.report_version_id.is_not(None))))


def test_delivery_failure_keeps_successful_files_and_partial_status(analysis_context,monkeypatch):
    client,sessions,_=analysis_context
    rid,sid,aid,did,vid=setup_source(client,sessions)
    with sessions() as db:
        from app.reports.delivery import deliver_record
        row=prepare_record(db,rid,['json','sql'])
        result=deliver_record(db,row)
        assert result['status']=='partial'
        assert result['formats']['json']['status']=='READY'
        assert result['formats']['sql']['error_code']=='SQL_EXPORT_NO_VERIFIED_SELECT'
        assert result['report']['source_record_ids']==[rid]
        from app.reports import delivery
        original=delivery.export_report_version
        def export_with_disk_failure(db,report,version,format):
            if format=='docx': raise OSError('storage unavailable')
            return original(db,report,version,format)
        monkeypatch.setattr(delivery,'export_report_version',export_with_disk_failure)
        row=prepare_record(db,rid,['json','docx'])
        failed=deliver_record(db,row)
        assert failed['status']=='partial' and failed['formats']['json']['status']=='READY'
        assert failed['formats']['docx']['error_code']=='REPORT_FORMAT_EXPORT_FAILED'


def test_automatic_reporting_is_declared_and_new_formats_are_bounded():
    from app.routers.workspace import capabilities
    from types import SimpleNamespace
    value=capabilities(SimpleNamespace())['data']
    assert value['automatic_reports'] is True
    assert 'python' in value['report_formats']
    assert value['sandbox_available'] is False
