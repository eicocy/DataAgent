from sqlalchemy import select
from app.models import Dataset,DatasetVersion,User
from test_analysis_api import analysis_context


def test_internal_transform_keeps_original_and_is_idempotent(analysis_context,monkeypatch):
    from app.analysis.models import ToolExecutionRequest,Permission
    from app.services.tool_execution import ToolExecutionService
    from app.services.datasets import DatasetService
    from app.config import get_settings
    client,sessions,upload_dir=analysis_context
    monkeypatch.setattr(get_settings(),'artifact_dir',str(upload_dir/'artifacts'))
    identifier=client.post('/api/v1/datasets/upload',files={'file':('input.csv',b'x,label\n1,A\n,B\n3,C\n','text/csv')}).json()['data']['id']
    with sessions() as db:
        dataset=db.get(Dataset,identifier)
        old_version=dataset.current_version_id
        user=db.scalar(select(User))
        service=ToolExecutionService(db,db.get_bind(),db.get_bind())
        request=ToolExecutionRequest(tool_name='fill_missing_values',dataset_id=identifier,parameters={'columns':['x'],'value':0},request_id='fill-internal')
        record,created=service.submit(user.id,request,frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
        assert created
        service.execute(record.id)
        db.expire_all()
        dataset=db.get(Dataset,identifier)
        assert dataset.current_version_id!=old_version
        version=db.get(DatasetVersion,dataset.current_version_id)
        assert version.version_number==2
        assert version.parent_version_id==old_version
        _,columns=DatasetService(db,db.get_bind()).get(identifier,user.id)
        old=DatasetService(db,db.get_bind()).load_frame(dataset,columns,old_version)
        new=DatasetService(db,db.get_bind()).load_frame(dataset,columns,version.id)
        assert old.x.isna().sum()==1
        assert new.x.tolist()==[1,0,3]
        replay,created=service.submit(user.id,request,frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
        assert not created and replay.id==record.id
        assert version.projection_table!=db.get(DatasetVersion,old_version).projection_table
