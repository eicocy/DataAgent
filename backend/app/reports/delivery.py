"""Inline delivery in the existing supervised analysis task, with partial success."""
from datetime import UTC, datetime
from sqlalchemy import select
from app.models import AnalysisArtifact, AnalysisReportVersion, AnalysisReport
from app.artifacts.manager import ArtifactManager
from app.services.artifacts import ArtifactStore
from app.reports.schemas import ReportSpec
from app.reports.service import create_report, export_report_version


def ensure_result_charts(db,record):
    existing = db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.record_id==record.id,
        AnalysisArtifact.kind=='chart',AnalysisArtifact.storage_key.is_(None))).all()
    if existing: return
    for item in db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.record_id==record.id,
        AnalysisArtifact.kind=='table',AnalysisArtifact.storage_key.is_(None))).all():
        try: result = ArtifactStore(db).read(item).get('data') or {}
        except LookupError: continue
        spec = None
        if result.get('kind')=='forecast' and result.get('points'):
            spec = {'version':'2.0','chart_type':'line','title':'预测与经验误差范围','x':result['time_column'],
                'y':[result['target_column']], 'series':[{'name':'预测','points':[
                    {'x':p['time'],'y':p['value'],'lower':p['lower'],'upper':p['upper']} for p in result['points']]}],
                'options':{'show_legend':True}, 'warnings':['经验范围未经覆盖率校准，不能视为确定结果。']}
        elif result.get('kind')=='contribution' and result.get('groups') and len(result['groups'])<=500:
            spec = {'version':'2.0','chart_type':'bar','title':'变化贡献分解','x':result['dimension'],'y':['delta'],
                'series':[{'name':'变化额','points':[{'x':p.get('dimension') or '缺失分类','y':float(p['delta'])} for p in result['groups']]}],
                'options':{'show_legend':False},'warnings':['贡献分解不能证明因果关系。']}
        if spec:
            saved = ArtifactStore(db).write(record, f'p4_chart_{item.id}',spec,kind='chart')
            chart = db.get(AnalysisArtifact,saved['artifact_id'])
            chart.metadata_json = {'source_artifact_ids':[item.id], 'generated_from':'verified_result'}
            ArtifactManager(db).protect(item)


def deliver_record(db,record,check_lease=lambda:None,emit=lambda *_:None):
    config = record.request_config_json or {}
    delivery = config.get('delivery')
    if not delivery: return None
    check_lease()
    from app.agent.budget import LIMITS
    required = 1+len(delivery['formats'])
    if len((record.plan_json or {}).get('steps',[]))+required>LIMITS[config.get('depth','STANDARD')][0]:
        return {'status':'partial','error_code':'DELIVERY_TASK_BUDGET_EXCEEDED','formats':{}}
    original_status = record.status
    # The inline caller pins its computed source while the public run stays running.
    record.status = 'running'
    db.flush()
    ensure_result_charts(db,record)
    ArtifactManager(db).finalize_record(record)
    spec = ReportSpec(title={'forecast':'预测分析报告','executive':'经营分析报告','data_quality':'数据质量报告'}.get(delivery['template'],'数据分析报告'),
        template=delivery['template'],report_type='forecast' if delivery['template']=='forecast' else 'general',
        dataset_id=record.dataset_id,dataset_version_id=record.dataset_version_id)
    emit('delivery_started',{'formats':delivery['formats']})
    report,version = create_report(db,record.user_id,record.session_id,spec,[record.id],inline_source=(record.id,original_status))
    result = {'status':'succeeded' if original_status=='succeeded' else 'partial','report':{
        'id':report.id,'title':report.title,'session_id':report.session_id,'version':version.version_number,
        'latest_version':report.latest_version_number,'spec':version.spec_json,'document':version.document_json,
        'dataset_id':report.dataset_id,'dataset_version_id':report.dataset_version_id,'source_record_ids':version.source_records_json},
        'formats':{},'artifacts':[]}
    for format in delivery['formats']:
        check_lease()
        try:
            files = export_report_version(db,report,version,format)
            views = [ArtifactManager(db).view(item) for item in files]
            result['artifacts'].extend(views)
            result['formats'][format] = {'status':'READY','artifact_ids':[item.id for item in files]}
        except Exception as error:
            if error.__class__.__name__ == 'WorkerLeaseLost': raise
            db.rollback()
            result['status']='partial'
            result['formats'][format]={'status':'FAILED','error_code':str(error)[:64]
                if isinstance(error,(ValueError,LookupError)) else 'REPORT_FORMAT_EXPORT_FAILED'}
        emit('delivery_updated',{'format':format,**result['formats'][format]})
    check_lease()
    record.status = original_status
    return result
