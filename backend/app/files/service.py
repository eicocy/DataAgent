from datetime import UTC, datetime
from pathlib import Path
import hashlib
from sqlalchemy import select
from fastapi import HTTPException
from app.models import UploadedFile, Dataset, AnalysisSession, BackgroundJob
from app.files.parsers import parse_document, FileParseError


def error(status, code, message):
    return HTTPException(status, detail={'code':code,'message':message})


def owned(db, file_id, user_id, lock=False):
    query=select(UploadedFile).where(UploadedFile.id==file_id)
    if lock: query=query.with_for_update().execution_options(populate_existing=True)
    file=db.scalar(query)
    if not file: raise error(404,'FILE_NOT_FOUND','文件不存在')
    if file.user_id!=user_id: raise error(403,'FILE_FORBIDDEN','没有权限访问文件')
    return file


def bind_session(db, session_id, user_id, file_id, dataset_id=None):
    if session_id is None: return
    session=db.scalar(select(AnalysisSession).where(AnalysisSession.id==session_id).with_for_update().execution_options(populate_existing=True))
    if not session or session.user_id!=user_id: raise error(403,'SESSION_FORBIDDEN','无权访问该会话')
    from app.agent.context import ConversationContext
    context=dict(session.context_json or {})
    context.update(ConversationContext.from_session(session).model_dump(mode='json'))
    files=list(context.get('uploaded_file_ids',[])); datasets=list(context.get('attached_dataset_ids',[]))
    if file_id not in files: files.append(file_id)
    if dataset_id and dataset_id not in datasets: datasets.append(dataset_id)
    if len(files)>10 or len(datasets)>10: raise error(400,'ATTACHMENT_LIMIT','会话最多 10 个附件')
    context.update(uploaded_file_ids=files,attached_dataset_ids=datasets)
    session.context_json=context


def register_dataset_file(db, dataset, path, mime=None):
    file=db.scalar(select(UploadedFile).where(UploadedFile.stored_name==dataset.stored_name))
    if not file:
        now=datetime.now(UTC)
        file=UploadedFile(user_id=dataset.user_id,original_name=dataset.original_name,stored_name=dataset.stored_name,
            file_type=dataset.file_type,file_size=dataset.file_size,mime_type=mime,checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
            status='ready',created_at=now,updated_at=now)
        db.add(file);db.flush()
    dataset.uploaded_file_id=file.id
    dataset.origin_metadata_json={'source_kind':'table_file','file_id':file.id,'checksum':file.checksum}
    return file


def summary(file, db=None):
    result={'id':file.id,'name':file.original_name,'type':file.file_type,'size':file.file_size,'status':file.status,
        'error_code':file.error_code,'error_message':file.error_message,'created_at':file.created_at.isoformat()}
    if db is not None:
        datasets=list(db.scalars(select(Dataset).where(Dataset.uploaded_file_id==file.id)))
        result['dataset_ids']=[d.id for d in datasets]
        if file.file_type not in {'txt','pdf','docx'} and datasets:
            result.update(status=datasets[0].status,error_code=datasets[0].parse_error_code,error_message=datasets[0].parse_error_message)
    return result


def detail(file, db):
    parsed=file.parsed_json or {}
    text=parsed.get('text','')
    return dict(summary(file,db),preview=text[:8000]+('\n[预览已截断；原文保留]' if len(text)>8000 else ''),
        preview_truncated=len(text)>8000,candidates=[{k:v for k,v in c.items() if k!='rows'}|{'row_count':len(c['rows']),'column_count':len(c['rows'][0])} for c in parsed.get('candidates',[])])


def candidate(file, candidate_id):
    if file.status!='ready': raise error(409,'FILE_NOT_READY','文件尚未解析完成')
    item=next((c for c in (file.parsed_json or {}).get('candidates',[]) if c['id']==candidate_id),None)
    if not item: raise error(404,'EXTRACTION_NOT_FOUND','候选表格不存在')
    return item


def process_document(file_id, factory, upload_dir, job_id=None, token=None):
    with factory() as db:
        file=db.get(UploadedFile,file_id)
        if not file or file.status!='parsing': return
        if job_id:
            job=db.get(BackgroundJob,job_id)
            if not job or job.status!='running' or job.lease_token!=token: return
        try:
            parsed=parse_document(Path(upload_dir)/file.stored_name,file.file_type)
            status,code,message='ready',None,None
        except FileParseError as exc:
            parsed=None;status,code,message='failed',exc.code,exc.message
        except Exception:
            parsed=None;status,code,message='failed','FILE_PARSE_FAILED','文档无法读取，请重新上传'
        db.expire_all()
        file=db.scalar(select(UploadedFile).where(UploadedFile.id==file_id).with_for_update().execution_options(populate_existing=True))
        if job_id:
            job=db.scalar(select(BackgroundJob).where(BackgroundJob.id==job_id).with_for_update().execution_options(populate_existing=True))
            if not job or job.status!='running' or job.lease_token!=token: return
            job.status='succeeded' if status=='ready' else 'failed';job.error_code=code;job.completed_at=datetime.now(UTC)
        if not file or file.status!='parsing': return
        file.status,file.error_code,file.error_message,file.parsed_json=status,code,message,parsed
        file.updated_at=datetime.now(UTC);db.commit()
