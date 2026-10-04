"""Owned fixed-version previews; publication belongs to ToolExecutionService."""
import hashlib
import json
from dataclasses import replace
from sqlalchemy import select
from app.models import DatasetVersion
from app.analysis.catalog import build_registry
from app.analysis.models import Permission,ToolExecutionRequest
from app.analysis.errors import ToolInputError
from app.services.datasets import DatasetService
from app.services.analysis import select_projection_bind
from app.services.tool_execution import context_for,ToolExecutionService

TRANSFORM_PERMISSIONS=frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA})


class TransformationService:
    def __init__(self,db,business_bind,projection_bind):
        self.db,self.business_bind,self.projection_bind=db,business_bind,projection_bind
        self.registry=build_registry()

    def context(self,user_id,dataset_id,version_id):
        service=DatasetService(self.db)
        dataset,columns=service.get(dataset_id,user_id)
        version=service.get_version(dataset,version_id)
        if version is None: raise ToolInputError('DATASET_VERSION_UNAVAILABLE')
        bound=DatasetService(self.db,select_projection_bind(version,self.business_bind,self.projection_bind))
        return dataset,version,context_for(bound,dataset,columns,version.id,preserve_decimal=True)

    def prepare(self,user_id,dataset_id,version_id,tool,parameters):
        parsed=self.registry.validate_input(tool,parameters)
        canonical=parsed.model_dump(mode='json')
        dataset,version,context=self.context(user_id,dataset_id,version_id)
        versions=[version]
        if tool=='publish_join':
            _,right_version,right=self.context(user_id,parsed.right_dataset_id,parsed.right_version_id)
            context=replace(context,related_inputs={'right':right});versions.append(right_version)
        identity=[{'id':v.id,'dataset_id':v.dataset_id,'checksum':v.source_checksum,'schema':v.schema_json,'profile':v.profile_json,'projection':v.projection_table,'transformations':v.transformations_json} for v in versions]
        digest=hashlib.sha256(json.dumps({'tool':tool,'inputs':identity,'parameters':canonical},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return dataset,context,canonical,digest

    def preview(self,user_id,dataset_id,version_id,tool,parameters):
        dataset,context,parameters,digest=self.prepare(user_id,dataset_id,version_id,tool,parameters)
        if dataset.current_version_id!=version_id: raise ToolInputError('DATASET_VERSION_CONFLICT')
        output=self.registry.calculate(tool,context,parameters,TRANSFORM_PERMISSIONS)
        from app.analysis.context import DatasetContext
        from app.analysis.inputs import QualityScoreInput
        from app.analysis.quality_tools import data_quality_score
        from app.analysis.serialization import records
        after=DatasetContext.from_frame(output.frame,context.dataset_id,context.dataset_version,
            max_rows=context.max_rows,max_columns=context.max_columns,max_bytes=context.max_bytes,
            preview_rows=context.preview_rows,max_cells=context.max_cells,correlation_columns=context.correlation_columns)
        def summary(ctx):
            return {'row_count':len(ctx.frame),'column_count':len(ctx.frame.columns),'schema':ctx.schema.model_dump(mode='json'),'sample':records(ctx.frame.head(min(ctx.preview_rows,max(1,ctx.max_cells//max(1,len(ctx.frame.columns)))))),'quality':data_quality_score(ctx,QualityScoreInput()).data.model_dump(mode='json')}
        return {'preview_hash':digest,'dataset_version_id':version_id,'before':summary(context),'after':summary(after),'result':output.data.model_dump(mode='json')}

    def submit(self,user_id,dataset_id,version_id,tool,parameters,preview_hash,request_id):
        _,_,canonical,digest=self.prepare(user_id,dataset_id,version_id,tool,parameters)
        if preview_hash!=digest: raise ToolInputError('TRANSFORMATION_PREVIEW_CONFLICT')
        request=ToolExecutionRequest(tool_name=tool,dataset_id=dataset_id,dataset_version=version_id,parameters=canonical,request_id=request_id)
        return ToolExecutionService(self.db,self.business_bind,self.projection_bind).submit(user_id,request,TRANSFORM_PERMISSIONS)

    def versions(self,user_id,dataset_id):
        DatasetService(self.db).get(dataset_id,user_id)
        return [version_dto(v) for v in self.db.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id==dataset_id).order_by(DatasetVersion.version_number))]


def version_dto(version):
    return {'id':version.id,'dataset_id':version.dataset_id,'version_number':version.version_number,'parent_version_id':version.parent_version_id,'status':version.status,'source_kind':version.source_kind,'schema':version.schema_json,'profile':version.profile_json,'transformations':version.transformations_json,'original_available':version.original_available}
