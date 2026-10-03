import pandas as pd
import pytest


def test_engine_trusted_permissions_and_dataset_binding():
    from app.analysis.engine import AnalysisEngine, ExecutionContext
    from app.analysis.context import DatasetContext
    from app.analysis.models import ToolExecutionRequest
    from app.analysis.errors import ToolError
    context=DatasetContext.from_frame(pd.DataFrame({'measure':[10,20]}))
    request=ToolExecutionRequest(tool_name='aggregate',dataset_id=1,parameters={'metrics':[{'column':'measure','aggregation':'sum'}]},request_id='engine-test')
    engine=AnalysisEngine()
    result=engine.execute(request,ExecutionContext(user_id=1,dataset=context))
    assert result.data.rows[0]['measure_sum']==30
    with pytest.raises(ToolError):
        engine.execute(request.model_copy(update={'dataset_id':2}),ExecutionContext(user_id=1,dataset=context))


def test_0007_migration_from_empty_database(tmp_path,monkeypatch):
    from app.config import get_settings
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine,inspect
    url=f'sqlite:///{(tmp_path / "engine.db").as_posix()}'
    monkeypatch.setattr(get_settings(),'migration_database_url',url)
    command.upgrade(Config('alembic.ini'),'head')
    engine=create_engine(url)
    assert 'tool_execution_records' in inspect(engine).get_table_names()
    assert 'tool_execution_id' in {column['name'] for column in inspect(engine).get_columns('analysis_artifacts')}
    engine.dispose()
