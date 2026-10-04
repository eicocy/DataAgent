from datetime import UTC, datetime
from pathlib import Path
import csv
import hashlib
import uuid
from fastapi import APIRouter, Depends, File, Form, UploadFile, BackgroundTasks, Request, Query
from pydantic import BaseModel, Field, ConfigDict, StrictBool
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.dependencies import current_user
from app.models import User, UploadedFile, Dataset, BackgroundJob, AnalysisSession
from app.files.service import owned, summary, detail, candidate, bind_session, process_document, error
from app.files.parsers import validate_signature, FileParseError
from app.routers import datasets as legacy

router=APIRouter(prefix='/files',tags=['files'])
TABLE_TYPES={'csv','tsv','json','jsonl','xls','xlsx','parquet'}
MIMES={'txt':{'text/plain'},'pdf':{'application/pdf'},'docx':{'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
       'csv':{'text/csv','application/csv','text/plain'},'tsv':{'text/tab-separated-values','text/plain'},
       'json':{'application/json','text/plain'},'jsonl':{'application/json','application/x-ndjson','application/jsonl','text/plain'},
       'xls':{'application/vnd.ms-excel'},'xlsx':{'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},'parquet':{'application/vnd.apache.parquet'}}


def response(data,code=200): return {'code':code,'message':'success','data':data}


@router.post('/upload',status_code=202)
def upload(request:Request,background_tasks:BackgroundTasks,file:UploadFile=File(...),sheet_name:str|None=Form(None),session_id:int|None=Form(None),user:User=Depends(current_user),db:Session=Depends(get_db)):
    name=legacy._safe_original_name(file.filename);kind=Path(name).suffix.lower().lstrip('.')
    if kind not in TABLE_TYPES|{'txt','pdf','docx'}: raise error(415,'FILE_TYPE_UNSUPPORTED','不支持此文件格式；旧 DOC 请转为 DOCX')
    mime=(file.content_type or '').split(';')[0].lower()
    if mime and mime!='application/octet-stream' and mime not in MIMES[kind]: raise error(415,'FILE_MIME_INVALID','MIME 与扩展名不一致')
    # Validate binding before persisting uploads, including legacy uploads.
    if session_id is not None:
        # Advisory prevalidation takes no row lock; bind_session rechecks the
        # current row under resource_lock -> Session FOR UPDATE below.
        session=db.scalar(select(AnalysisSession).where(AnalysisSession.id==session_id))
        if not session or session.user_id!=user.id: raise error(403,'SESSION_FORBIDDEN','无权访问该会话')
        if len((session.context_json or {}).get('uploaded_file_ids',[]))>=10: raise error(400,'ATTACHMENT_LIMIT','会话最多 10 个附件')
    if kind in TABLE_TYPES:
        result=legacy.upload_dataset(request,background_tasks,file,sheet_name,user,db,session_id)
        dataset=db.get(Dataset,result['data']['id']);uploaded=db.get(UploadedFile,dataset.uploaded_file_id)
        return response({'file':summary(uploaded,db),'dataset':result['data']},202)
    settings=get_settings();directory=Path(settings.upload_dir);directory.mkdir(parents=True,exist_ok=True)
    name_on_disk=f'{uuid.uuid4().hex}.{kind}';path=directory/name_on_disk
    try:
        content=file.file.read(settings.max_upload_bytes+1)
        if len(content)>settings.max_upload_bytes: raise error(413,'FILE_TOO_LARGE','文件超过 20 MiB 限制')
        if not content: raise error(400,'FILE_EMPTY','请选择非空文件')
        path.write_bytes(content);validate_signature(path,kind)
        from app.services.analysis import resource_lock
        with resource_lock:
            now=datetime.now(UTC)
            uploaded=UploadedFile(user_id=user.id,original_name=name,stored_name=name_on_disk,file_type=kind,file_size=len(content),mime_type=mime,
                checksum=hashlib.sha256(content).hexdigest(),status='parsing',created_at=now,updated_at=now)
            db.add(uploaded);db.flush();bind_session(db,session_id,user.id,uploaded.id)
            supervised=bool(getattr(request.app.state,'task_supervisor',None))
            if supervised:
                count=db.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status.in_(('pending','running')))) or 0
                if count>=settings.max_pending_jobs: raise error(429,'TASK_QUEUE_FULL','任务队列已满')
                db.add(BackgroundJob(kind='file_parse',resource_id=uploaded.id,user_id=user.id,status='pending',created_at=now))
            db.commit();result=summary(uploaded,db)
        if not supervised: background_tasks.add_task(process_document,uploaded.id,legacy.SessionLocal,settings.upload_dir)
        return response({'file':result},202)
    except FileParseError as exc:
        db.rollback();path.unlink(missing_ok=True);raise error(400,exc.code,exc.message)
    except Exception:
        db.rollback();path.unlink(missing_ok=True);raise
    finally: file.file.close()


@router.get('')
def list_files(session_id:int|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50),user:User=Depends(current_user),db:Session=Depends(get_db)):
    query=select(UploadedFile).where(UploadedFile.user_id==user.id)
    if session_id is not None:
        session=db.get(AnalysisSession,session_id)
        if not session or session.user_id!=user.id: raise error(403,'SESSION_FORBIDDEN','无权访问该会话')
        query=query.where(UploadedFile.id.in_((session.context_json or {}).get('uploaded_file_ids',[])))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    items=db.scalars(query.order_by(UploadedFile.id.desc()).offset((page-1)*page_size).limit(page_size))
    return response({'items':[summary(f,db) for f in items],'total':total,'page':page,'page_size':page_size})


@router.get('/{file_id}')
def get_file(file_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    uploaded=owned(db,file_id,user.id)
    result=detail(uploaded,db)
    if uploaded.file_type in TABLE_TYPES and result['status']=='ready' and result['dataset_ids']:
        result['table_preview']=legacy.preview_dataset(result['dataset_ids'][0],0,20,None,user,db)['data']
    return response(result)


@router.get('/{file_id}/extractions/{candidate_id}')
def get_extraction(file_id:int,candidate_id:str,offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),user:User=Depends(current_user),db:Session=Depends(get_db)):
    item=candidate(owned(db,file_id,user.id),candidate_id)
    return response({'id':item['id'],'location':item['location'],'rows':item['rows'][offset:offset+limit],'total':len(item['rows']),
        'columns':[f'column_{i+1}' for i in range(len(item['rows'][0]))],'requires_header_confirmation':True})


class ConfirmExtraction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirmed:StrictBool
    request_id:str=Field(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')
    has_header:StrictBool=True
    name:str|None=Field(default=None,max_length=255)
    session_id:int|None=None


@router.delete('/{file_id}')
def delete_file(file_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from app.services.analysis import resource_lock
    with resource_lock:
        uploaded=owned(db,file_id,user.id,True)
        if uploaded.status=='parsing' or db.scalar(select(Dataset.id).where(Dataset.uploaded_file_id==file_id).limit(1)):
            raise error(409,'FILE_IN_USE','文件正在解析或仍有数据集引用，请先删除数据集')
        name=uploaded.stored_name
        for session in db.scalars(select(AnalysisSession).where(AnalysisSession.user_id==user.id).with_for_update()):
            context=dict(session.context_json or {})
            if file_id in context.get('uploaded_file_ids',[]):
                context['uploaded_file_ids']=[i for i in context['uploaded_file_ids'] if i!=file_id];session.context_json=context
        from app.models import CleanupTask
        cleanup=CleanupTask(payload_json={'file_stored_name':name},status='pending',created_at=datetime.now(UTC))
        db.add(cleanup);db.delete(uploaded);db.commit()
        from app.services.jobs import perform_cleanup
        perform_cleanup(db,cleanup,legacy.engine,legacy.engine)
        return response({'deleted_id':file_id})


@router.post('/{file_id}/extractions/{candidate_id}/datasets',status_code=202)
def confirm(file_id:int,candidate_id:str,body:ConfirmExtraction,request:Request,background_tasks:BackgroundTasks,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not body.confirmed: raise error(400,'EXTRACTION_CONFIRMATION_REQUIRED','请先核对并确认候选表格')
    from app.services.analysis import resource_lock
    with resource_lock:
        uploaded=owned(db,file_id,user.id,True);item=candidate(uploaded,candidate_id)
        options=body.model_dump(exclude={'confirmed','request_id'})
        for existing in db.scalars(select(Dataset).where(Dataset.uploaded_file_id==file_id)):
            origin=existing.origin_metadata_json or {}
            if origin.get('request_id')==body.request_id:
                if origin.get('candidate_id')!=candidate_id or origin.get('options')!=options: raise error(409,'EXTRACTION_REQUEST_CONFLICT','请求编号已用于其他确认选项')
                return response({'dataset':legacy._summary(existing),'file':summary(uploaded,db)},202)
        rows=item['rows'];directory=Path(get_settings().upload_dir)
        stored_name=f'{uuid.uuid4().hex}.csv';path=directory/stored_name
        try:
            with path.open('w',encoding='utf-8',newline='') as output:
                writer=csv.writer(output)
                if not body.has_header: writer.writerow([f'column_{i+1}' for i in range(len(rows[0]))])
                writer.writerows(rows)
            now=datetime.now(UTC)
            dataset=Dataset(user_id=user.id,uploaded_file_id=uploaded.id,original_name=body.name or f'{uploaded.original_name}-table-{candidate_id}.csv',stored_name=stored_name,
                file_type='csv',file_size=path.stat().st_size,status='parsing',created_at=now,updated_at=now,
                origin_metadata_json={'source_kind':'document_table','file_id':file_id,'candidate_id':candidate_id,'location':item['location'],
                    'checksum':uploaded.checksum,'candidate_checksum':hashlib.sha256(__import__('json').dumps(rows,ensure_ascii=False).encode()).hexdigest(),'request_id':body.request_id,'options':options})
            db.add(dataset);db.flush();bind_session(db,body.session_id,user.id,file_id,dataset.id)
            supervised=bool(getattr(request.app.state,'task_supervisor',None))
            if supervised:
                count=db.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status.in_(('pending','running')))) or 0
                if count>=get_settings().max_pending_jobs: raise error(429,'TASK_QUEUE_FULL','任务队列已满')
                db.add(BackgroundJob(kind='parse',resource_id=dataset.id,dataset_id=dataset.id,user_id=user.id,status='pending',created_at=now))
            db.commit();result=legacy._summary(dataset)
        except Exception:
            db.rollback();path.unlink(missing_ok=True);raise
        if not supervised: background_tasks.add_task(legacy.process_dataset,dataset.id,legacy.SessionLocal,legacy.engine,get_settings().upload_dir)
        return response({'dataset':result,'file':summary(uploaded,db)},202)
