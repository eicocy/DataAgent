from datetime import datetime, timedelta, UTC
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User, BackgroundJob
from app.services.jobs import claim_job, recover_expired_jobs


def test_expired_lease_prevents_late_record_overwrite(tmp_path):
    from app.models import Dataset, AnalysisSession, AnalysisRecord
    from app.services.analysis import execute_record
    from app.services.analysis_agent import AgentOutcome
    bind = create_engine("sqlite://")
    Base.metadata.create_all(bind)
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    now = datetime.now(UTC).replace(tzinfo=None)
    with factory() as db:
        user = User(username="fenced", password_hash="hash", created_at=now, updated_at=now)
        db.add(user)
        db.flush()
        dataset = Dataset(user_id=user.id, original_name="f.csv", stored_name="f.csv", file_type="csv", file_size=1, status="ready", created_at=now, updated_at=now)
        db.add(dataset)
        db.flush()
        session = AnalysisSession(user_id=user.id, dataset_id=dataset.id, title="fenced", created_at=now, updated_at=now)
        db.add(session)
        db.flush()
        record = AnalysisRecord(user_id=user.id, dataset_id=dataset.id, session_id=session.id, request_id="fenced", question="sum", status="pending", created_at=now)
        db.add(record)
        db.flush()
        job = BackgroundJob(kind="analysis", resource_id=record.id, user_id=user.id, status="failed", lease_token="old", created_at=now)
        db.add(job)
        db.commit()
        class LateAgent:
            def analyze(self, *_):
                return AgentOutcome([], {"value": 1}, "late", None, "succeeded")
        execute_record(db, record.id, LateAgent(), bind, bind, job_id=job.id, lease_token="old")
        assert db.get(AnalysisRecord, record.id).status == "pending"


def test_supervisor_terminates_actual_process_at_deadline(tmp_path, monkeypatch):
    import subprocess
    import sys
    import time
    from app.services.jobs import TaskSupervisor
    from app.config import Settings
    bind = create_engine("sqlite:///" + str(tmp_path / "deadline.sqlite"))
    Base.metadata.create_all(bind)
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    now = datetime.now(UTC).replace(tzinfo=None)
    with factory() as db:
        user = User(username="deadline", password_hash="hash", created_at=now, updated_at=now)
        db.add(user)
        db.flush()
        db.add(BackgroundJob(kind="test", resource_id=1, user_id=user.id, created_at=now))
        db.commit()
    real_popen = subprocess.Popen
    processes = []
    def launch_test_worker(*args, **kwargs):
        process = real_popen([sys.executable, "-c", "while True: pass"], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr("app.services.jobs.subprocess.Popen", launch_test_worker)
    settings = Settings(_env_file=None, database_url=str(bind.url), analysis_timeout_seconds=1)
    started = time.monotonic()
    TaskSupervisor(factory, settings).run_claimed(*claim_job(factory))
    assert time.monotonic() - started < 8
    assert processes[0].poll() is not None
    with factory() as db:
        assert db.query(BackgroundJob).one().error_code == "TASK_TIMEOUT"
        user_id = db.query(User).one().id
        db.add(BackgroundJob(kind="test", resource_id=2, user_id=user_id, created_at=now))
        db.commit()
    claimed = claim_job(factory)
    count = 0
    def intermittent_factory():
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("temporary database failure")
        return factory()
    import pytest
    with pytest.raises(RuntimeError, match="temporary database failure"):
        TaskSupervisor(intermittent_factory, settings).run_claimed(*claimed)
    assert processes[1].poll() is not None


def test_fixed_worker_parses_then_explicitly_fails_without_model_key(tmp_path):
    from app.models import Dataset, AnalysisRecord, AnalysisSession
    from app.services.jobs import TaskSupervisor
    from app.config import Settings
    import uuid
    bind = create_engine("sqlite:///" + str(tmp_path / "worker.sqlite"))
    Base.metadata.create_all(bind)
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    upload = tmp_path / "uploads"
    upload.mkdir()
    name = uuid.uuid4().hex + ".csv"
    (upload / name).write_text("date,product,sales\n2026-06-01,A,12\n", encoding="utf-8")
    now = datetime.now(UTC).replace(tzinfo=None)
    with factory() as db:
        user = User(username="worker", password_hash="hash", created_at=now, updated_at=now)
        db.add(user)
        db.flush()
        dataset = Dataset(user_id=user.id, original_name="sales.csv", stored_name=name, file_type="csv", file_size=50, status="parsing", created_at=now, updated_at=now)
        db.add(dataset)
        db.flush()
        dataset_id = dataset.id
        db.add(BackgroundJob(kind="parse", resource_id=dataset.id, user_id=user.id, dataset_id=dataset.id, created_at=now))
        db.commit()
    # 此用例验证独立 SQLite 子进程，不继承真实 MySQL 验收的投影连接。
    settings = Settings(_env_file=None, database_url=str(bind.url), projection_database_url="",
                        sql_readonly_database_url="", upload_dir=str(upload),
                        artifact_dir=str(tmp_path / "artifacts"), deepseek_api_key="")
    supervisor = TaskSupervisor(factory, settings)
    supervisor.run_claimed(*claim_job(factory))
    with factory() as db:
        dataset = db.get(Dataset, dataset_id)
        assert dataset.status == "ready" and dataset.row_count == 1
        session = AnalysisSession(user_id=dataset.user_id, dataset_id=dataset.id, title="test", created_at=now, updated_at=now)
        db.add(session)
        db.flush()
        record = AnalysisRecord(user_id=dataset.user_id, dataset_id=dataset.id, session_id=session.id, request_id="fixed-worker", question="总销售额", created_at=now)
        db.add(record)
        db.flush()
        record_id = record.id
        db.add(BackgroundJob(kind="analysis", resource_id=record.id, user_id=record.user_id, dataset_id=dataset.id, created_at=now))
        db.commit()
    supervisor.run_claimed(*claim_job(factory))
    with factory() as db:
        record = db.get(AnalysisRecord, record_id)
        assert record.status == "failed" and record.error_code == "MODEL_UNAVAILABLE"
        assert db.query(BackgroundJob).filter(BackgroundJob.status.in_(("pending", "running"))).count() == 0


def test_claim_is_exclusive_and_expired_lease_is_terminated():
    bind = create_engine("sqlite://")
    Base.metadata.create_all(bind)
    factory = sessionmaker(bind=bind, expire_on_commit=False)
    now = datetime.now(UTC).replace(tzinfo=None)
    with factory() as db:
        user = User(username="jobs", password_hash="hash", created_at=now, updated_at=now)
        db.add(user)
        db.flush()
        db.add(BackgroundJob(kind="test", resource_id=1, user_id=user.id, created_at=now))
        db.commit()
    claimed = claim_job(factory)
    assert claimed is not None
    assert claim_job(factory) is None
    with factory() as db:
        job = db.get(BackgroundJob, claimed[0])
        job.heartbeat_at = now - timedelta(minutes=5)
        db.commit()
    assert recover_expired_jobs(factory) == 1
    with factory() as db:
        assert db.get(BackgroundJob, claimed[0]).status == "failed"
