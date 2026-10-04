from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request,BackgroundTasks,Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import current_user
from app.models import User,DatasetVersion
from app.analysis.models import StrictModel
from app.analysis.inputs import CleaningPlanInput,JoinInput
from app.analysis.errors import ToolError
from app.services.transformations import TransformationService,version_dto
from app.services.tool_execution import ToolExecutionService
from pydantic import Field,field_validator

router=APIRouter(prefix='/datasets',tags=['transformations'])


class CleaningPreview(CleaningPlanInput):
    dataset_version_id: int=Field(gt=0,strict=True)


class JoinPreview(StrictModel):
    dataset_version_id: int=Field(gt=0,strict=True)
    right_dataset_id: int=Field(gt=0,strict=True)
    right_version_id: int=Field(gt=0,strict=True)
    left_on: list[str]=Field(min_length=1,max_length=10)
    right_on: list[str]=Field(min_length=1,max_length=10)
    how: Literal['inner','left']
    relationship: Literal['one_to_one','many_to_one','one_to_many']


class CleaningConfirm(CleaningPreview):
    confirmed: Literal[True]
    preview_hash: str=Field(pattern='^[a-f0-9]{64}$')
    request_id: str=Field(min_length=1,max_length=64)
    @field_validator('confirmed',mode='before')
    @classmethod
    def explicit_true(cls,value):
        if value is not True: raise ValueError('explicit boolean confirmation required')
        return value


class JoinConfirm(JoinPreview):
    confirmed: Literal[True]
    preview_hash: str=Field(pattern='^[a-f0-9]{64}$')
    request_id: str=Field(min_length=1,max_length=64)
    @field_validator('confirmed',mode='before')
    @classmethod
    def explicit_true(cls,value):
        if value is not True: raise ValueError('explicit boolean confirmation required')
        return value


def service(db):
    # The embedded TestClient path and production path both use the configured
    # dataset router business bind; projection choice remains version-driven.
    from app.routers.datasets import engine
    from app.database import projection_engine
    return TransformationService(db,engine,projection_engine)


def call(function):
    try: return function()
    except ToolError as exc:
        status=409 if 'CONFLICT' in exc.code else 422
        raise HTTPException(status_code=status,detail=exc.structured()) from None


def parameters(body):
    return body.model_dump(mode='json',exclude={'dataset_version_id','confirmed','preview_hash','request_id'})


@router.get('/{dataset_id}/quality')
def quality(dataset_id:int,dataset_version_id:int=Query(gt=0),user:User=Depends(current_user),db:Session=Depends(get_db)):
    def calculate():
        svc=service(db);_,_,context=svc.context(user.id,dataset_id,dataset_version_id)
        return svc.registry.execute('data_quality_score',context,{}).data.model_dump(mode='json')
    return {'code':200,'message':'success','data':call(calculate)}


@router.get('/{dataset_id}/versions')
def versions(dataset_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return {'code':200,'message':'success','data':call(lambda:service(db).versions(user.id,dataset_id))}


@router.post('/{dataset_id}/transformations/preview')
def cleaning_preview(dataset_id:int,body:CleaningPreview,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return {'code':200,'message':'success','data':call(lambda:service(db).preview(user.id,dataset_id,body.dataset_version_id,'cleaning_plan',parameters(body)))}


@router.post('/{dataset_id}/joins/preview')
def join_preview(dataset_id:int,body:JoinPreview,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return {'code':200,'message':'success','data':call(lambda:service(db).preview(user.id,dataset_id,body.dataset_version_id,'publish_join',parameters(body)))}


def submit(dataset_id,body,tool,user,db,request,background_tasks):
    svc=service(db)
    record,created=call(lambda:svc.submit(user.id,dataset_id,body.dataset_version_id,tool,parameters(body),body.preview_hash,body.request_id))
    if created and not getattr(request.app.state,'task_supervisor',None):
        from app.routers.datasets import SessionLocal
        def execute():
            with SessionLocal() as session:
                ToolExecutionService(session,svc.business_bind,svc.projection_bind).execute(record.id)
        background_tasks.add_task(execute)
    return {'code':202,'message':'accepted','data':{'execution_id':record.id,'status':record.status,'created':created}}


@router.post('/{dataset_id}/transformations',status_code=202)
def cleaning_submit(dataset_id:int,body:CleaningConfirm,request:Request,background_tasks:BackgroundTasks,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return submit(dataset_id,body,'cleaning_plan',user,db,request,background_tasks)


@router.post('/{dataset_id}/joins',status_code=202)
def join_submit(dataset_id:int,body:JoinConfirm,request:Request,background_tasks:BackgroundTasks,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return submit(dataset_id,body,'publish_join',user,db,request,background_tasks)


def status(dataset_id,execution_id,tool,user,db):
    from app.routers.datasets import engine
    from app.database import projection_engine
    record=call(lambda:ToolExecutionService(db,engine,projection_engine).get(user.id,execution_id))
    if record.dataset_id!=dataset_id or record.tool_name!=tool: raise HTTPException(404,detail={'code':'TOOL_EXECUTION_NOT_FOUND'})
    result=record.result_json
    identifier=(result or {}).get('data',{}).get('output_version')
    version=db.get(DatasetVersion,identifier) if identifier else None
    return {'code':200,'message':'success','data':{'execution_id':record.id,'status':record.status,'result':result,'error':record.error_json,'output_version':version_dto(version) if version else None}}


@router.get('/{dataset_id}/transformations/{execution_id}')
def cleaning_status(dataset_id:int,execution_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return status(dataset_id,execution_id,'cleaning_plan',user,db)


@router.get('/{dataset_id}/joins/{execution_id}')
def join_status(dataset_id:int,execution_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return status(dataset_id,execution_id,'publish_join',user,db)
