"""Authorized internal submissions; this service is not a public execution API."""
import time
import uuid
from datetime import UTC,datetime
from dataclasses import replace
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from app.models import Dataset,DatasetVersion,DatasetColumn,User,ToolExecutionRecord,BackgroundJob,CleanupTask,AnalysisArtifact
from app.config import get_settings
from app.services.datasets import DatasetService,write_projection,profile_frame
from app.services.analysis import select_projection_bind
from app.services.artifacts import ArtifactStore
from app.analysis.models import ToolExecutionRequest,Permission
from app.analysis.engine import AnalysisEngine,ExecutionContext
from app.analysis.context import DatasetContext
from app.analysis.errors import ToolError,ToolInputError,ToolExecutionError
from app.datasets.profiler import build_profile


def context_for(service,dataset,columns,version_id=None):
    version=service.get_version(dataset,version_id)
    frame=service.load_frame(dataset,columns,version_id)
    settings=get_settings()
    budgets=dict(max_rows=settings.tool_max_rows,max_columns=settings.tool_max_columns,max_cells=settings.tool_max_cells,preview_rows=settings.tool_preview_rows,correlation_columns=settings.tool_correlation_columns,max_bytes=settings.dataframe_max_bytes)
    if version:
        from app.datasets.schemas import DatasetSchema,DatasetProfile
        return DatasetContext(dataset.id,version.id,frame,DatasetSchema.model_validate(version.schema_json),DatasetProfile.model_validate(version.profile_json),**budgets)
    return DatasetContext.from_frame(frame,dataset.id,**budgets)


class ToolExecutionService:
    def __init__(self,db,business_bind,projection_bind,settings=None,readonly_bind=None):
        self.db,self.business_bind,self.projection_bind=db,business_bind,projection_bind
        self.settings=settings or get_settings()
        self.readonly_bind=readonly_bind
        self.engine=AnalysisEngine()

    def submit(self,user_id,request,permissions=frozenset({Permission.READ_DATA})):
        db=self.db
        db.scalar(select(User).where(User.id==user_id).with_for_update())
        tool=self.engine.registry.get(request.tool_name)
        if not tool.metadata.permissions<=permissions: raise ToolInputError('TOOL_PERMISSION_DENIED')
        typed=self.engine.registry.validate_input(request.tool_name,request.parameters)
        from app.analysis.inputs import DataInput
        if isinstance(typed,DataInput) and 'limit' not in request.parameters:typed.limit=self.settings.tool_preview_rows
        parameters=typed.model_dump(mode='json')
        existing=db.scalar(select(ToolExecutionRecord).where(ToolExecutionRecord.user_id==user_id,ToolExecutionRecord.request_id==request.request_id))
        if existing:
            if existing.dataset_id!=request.dataset_id or existing.tool_name!=request.tool_name or existing.parameters_json!=parameters or request.dataset_version not in (None,existing.dataset_version_id):
                raise ToolInputError('TOOL_REQUEST_ID_CONFLICT')
            return existing,False
        dataset=db.scalar(select(Dataset).where(Dataset.id==request.dataset_id,Dataset.user_id==user_id).with_for_update())
        if not dataset or dataset.status!='ready': raise ToolInputError('DATASET_UNAVAILABLE')
        service=DatasetService(db,select_projection_bind(dataset,self.business_bind,self.projection_bind))
        version=service.get_version(dataset,request.dataset_version)
        if tool.metadata.modifies_dataset and version is None:
            from app.datasets.versions import backfill_dataset
            backfill_dataset(db,dataset,service.projection_bind,self.settings.upload_dir,True)
            version=service.get_version(dataset)
        pending=db.scalar(select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status.in_(('pending','running')))) or 0
        active=db.scalar(select(func.count()).select_from(ToolExecutionRecord).where(ToolExecutionRecord.user_id==user_id,ToolExecutionRecord.status.in_(('pending','running')))) or 0
        if pending>=self.settings.max_pending_jobs or active>=self.settings.max_user_active_runs: raise ToolInputError('TASK_QUEUE_FULL')
        now=datetime.now(UTC)
        record=ToolExecutionRecord(user_id=user_id,dataset_id=dataset.id,dataset_version_id=version.id if version else None,tool_name=request.tool_name,tool_version=tool.metadata.version,request_id=request.request_id,parameters_json=parameters,permissions_json=[p.value for p in permissions],status='pending',created_at=now)
        try:
            db.add(record); db.flush()
            db.add(BackgroundJob(kind='tool',resource_id=record.id,user_id=user_id,dataset_id=dataset.id,status='pending',created_at=now))
            db.commit()
        except IntegrityError:
            db.rollback()
            existing=db.scalar(select(ToolExecutionRecord).where(ToolExecutionRecord.user_id==user_id,ToolExecutionRecord.request_id==request.request_id))
            if existing and existing.dataset_id==request.dataset_id and existing.tool_name==request.tool_name and existing.parameters_json==parameters and request.dataset_version in (None,existing.dataset_version_id):
                return existing,False
            raise ToolInputError('TOOL_REQUEST_ID_CONFLICT') from None
        return record,True

    def get(self,user_id,identifier):
        record=self.db.get(ToolExecutionRecord,identifier)
        if not record or record.user_id!=user_id: raise ToolInputError('TOOL_EXECUTION_NOT_FOUND')
        return record

    def read_artifact(self,user_id,identifier):
        record=self.get(user_id,identifier)
        artifact=self.db.scalar(select(AnalysisArtifact).where(AnalysisArtifact.tool_execution_id==record.id,AnalysisArtifact.user_id==user_id))
        if not artifact: raise ToolInputError('TOOL_ARTIFACT_NOT_FOUND')
        return ArtifactStore(self.db,self.settings).read(artifact)

    def execute(self,identifier,job_id=None,lease_token=None):
        db=self.db
        record=db.get(ToolExecutionRecord,identifier)
        if not record or record.status!='pending': return record
        def check():
            if lease_token:
                job=db.scalar(select(BackgroundJob).where(BackgroundJob.id==job_id).with_for_update().execution_options(populate_existing=True))
                if not job or job.status!='running' or job.lease_token!=lease_token: raise ToolExecutionError('WORKER_LEASE_LOST')
        started=time.monotonic()
        check()
        record.status='running'; record.started_at=datetime.now(UTC); db.commit()
        staging_task=None
        try:
            dataset,columns=DatasetService(db).get(record.dataset_id,record.user_id)
            version=DatasetService(db).get_version(dataset,record.dataset_version_id)
            location=version if version else dataset
            bind=select_projection_bind(location,self.business_bind,self.projection_bind)
            service=DatasetService(db,bind)
            context=context_for(service,dataset,columns,record.dataset_version_id)
            if self.engine.registry.get(record.tool_name).output_schema.__name__ in {'LegacyResult','LegacyChartResult'}:
                from app.services.analysis_tools import DatasetTools
                from app.datasets.schemas import column_storage_type
                from types import SimpleNamespace
                bound_columns=[SimpleNamespace(name=c.name,original_name=c.original_name,data_type=column_storage_type(c),nullable=bool(context.frame[c.name].isna().any()),missing_count=int(context.frame[c.name].isna().sum()),unique_count=int(context.frame[c.name].nunique()),sample_values_json=[]) for c in context.schema.columns]
                calculator=DatasetTools(dataset,bound_columns,bind,self.readonly_bind)
                calculator.frame=context.frame;calculator.projection_table=location.projection_table
                calculator._execution_context=context
                context=replace(context,legacy_calculator=calculator)
            artifact_name=uuid.uuid4().hex+'.json'
            artifact_task=CleanupTask(payload_json={'artifacts':[artifact_name],'tool_execution_id':record.id},status='reserved',created_at=datetime.now(UTC))
            db.add(artifact_task);db.commit()
            request=ToolExecutionRequest(tool_name=record.tool_name,dataset_id=record.dataset_id,dataset_version=record.dataset_version_id,parameters=record.parameters_json,request_id=record.request_id,task_id=job_id)
            def stage(budget):
                if job_id:
                    check(); job=db.get(BackgroundJob,job_id)
                    job.active_stage='tool';job.stage_started_at=datetime.now(UTC).replace(tzinfo=None);job.stage_timeout_seconds=budget;db.commit()
            def publish(frame,parameters,operation):
                nonlocal staging_task
                name=f'dataset_{dataset.id}_v_{uuid.uuid4().hex}'
                record.staging_projection=name
                staging_task=CleanupTask(payload_json={'projections':[{'table':name,'schema':location.projection_schema}],'tool_execution_id':record.id},status='reserved',created_at=datetime.now(UTC))
                db.add(staging_task);db.commit()
                write_projection(frame,dataset.id,bind,name)
                check()
                current=db.scalar(select(Dataset).where(Dataset.id==dataset.id,Dataset.user_id==record.user_id).with_for_update().execution_options(populate_existing=True))
                if not current or current.current_version_id!=record.dataset_version_id: raise ToolExecutionError('DATASET_VERSION_CONFLICT')
                schema,profile=build_profile(frame)
                number=(db.scalar(select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id==dataset.id)) or 0)+1
                output=DatasetVersion(dataset_id=dataset.id,version_number=number,parent_version_id=record.dataset_version_id,status='ready',source_kind='tool_transform',projection_schema=location.projection_schema,projection_table=name,schema_json=schema.model_dump(mode='json'),profile_json=profile.model_dump(mode='json'),transformations_json=[{'operation':operation,'parameters':parameters,'source_version':record.dataset_version_id,'created_at':datetime.now(UTC).isoformat()}],original_available=version.original_available,source_checksum=version.source_checksum,created_at=datetime.now(UTC))
                db.add(output);db.flush()
                current.current_version_id=output.id;current.projection_table=name;current.projection_schema=location.projection_schema
                current.row_count=len(frame);current.column_count=len(frame.columns);current.quality_warnings_json=profile.warnings;current.updated_at=datetime.now(UTC)
                db.query(DatasetColumn).filter(DatasetColumn.dataset_id==dataset.id).delete()
                db.add_all(profile_frame(frame,dataset.id))
                staging_task.status='succeeded';record.staging_projection=None
                return output.id
            def persist(result,frame):
                artifact=ArtifactStore(db,self.settings).write(record,record.tool_name,result.data.model_dump(mode='json'),frame,'chart' if result.data.kind in {'chart','legacy_chart'} else 'table',True,artifact_name)
                result.artifact_ref=artifact['artifact_id']
                artifact_task.status='succeeded'
                return result
            result=self.engine.execute(request,ExecutionContext(record.user_id,context,frozenset(Permission(p) for p in record.permissions_json),started+self.settings.analysis_timeout_seconds,check,publish,persist,stage=stage))
            check()
            record.status=result.status;record.result_json=result.model_dump(mode='json')
            job=db.get(BackgroundJob,job_id) if job_id else db.scalar(select(BackgroundJob).where(BackgroundJob.kind=='tool',BackgroundJob.resource_id==record.id))
            if job: job.status='succeeded';job.completed_at=datetime.now(UTC)
            record.finished_at=datetime.now(UTC);record.duration_ms=int((time.monotonic()-started)*1000)
            db.commit()
        except Exception as exc:
            db.rollback()
            record=db.get(ToolExecutionRecord,identifier)
            try: check()
            except ToolError:
                db.rollback();return record
            error=exc if isinstance(exc,ToolError) else ToolExecutionError('TOOL_EXECUTION_FAILED')
            record.status='failed';record.error_json=error.structured();record.finished_at=datetime.now(UTC)
            for task in db.scalars(select(CleanupTask).where(CleanupTask.status=='reserved')):
                if task.payload_json.get('tool_execution_id')==record.id: task.status='pending'
            job=db.get(BackgroundJob,job_id) if job_id else db.scalar(select(BackgroundJob).where(BackgroundJob.kind=='tool',BackgroundJob.resource_id==record.id))
            if job: job.status='failed';job.error_code=error.code;job.completed_at=datetime.now(UTC)
            db.commit()
        return record
