"""Fixed trusted worker entry point. No user executable code is accepted."""
import argparse
import os
import threading
import ctypes
from datetime import datetime, UTC
from app.database import SessionLocal, engine, projection_engine, readonly_engine
from app.models import BackgroundJob, Dataset
from app.services.analysis import execute_record
from app.services.analysis_agent import DeepSeekAgent
from app.services.datasets import process_dataset


def watch_owner(parent_pid, job_id, token):
    """An orphan worker exits even when the supervisor is killed, on Windows and Linux."""
    parent_handle = None
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        parent_handle = kernel.OpenProcess(0x00100000, False, parent_pid)
    while True:
        try:
            if os.name == "nt":
                if not parent_handle or kernel.WaitForSingleObject(parent_handle, 0) == 0:
                    os._exit(70)
            else:
                os.kill(parent_pid, 0)
            with SessionLocal() as db:
                job = db.get(BackgroundJob, job_id)
                if not job or job.lease_token != token or job.status != "running":
                    os._exit(70)
        except Exception:
            os._exit(70)
        threading.Event().wait(0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--lease", required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    threading.Thread(target=watch_owner, args=(args.parent_pid, args.job_id, args.lease), daemon=True).start()
    with SessionLocal() as db:
        job = db.get(BackgroundJob, args.job_id)
        if not job or job.status != "running" or job.lease_token != args.lease:
            return
        if job.kind == "analysis":
            execute_record(db, job.resource_id, DeepSeekAgent(), engine, projection_engine, readonly_engine, job.id, args.lease)
        elif job.kind=='tool':
            from app.services.tool_execution import ToolExecutionService
            ToolExecutionService(db,engine,projection_engine,readonly_bind=readonly_engine).execute(job.resource_id,job.id,args.lease)
        elif job.kind == "report":
            from app.reports.service import execute_report_task
            execute_report_task(db, job.resource_id, job.id, args.lease)
        elif job.kind == 'file_parse':
            from app.files.service import process_document
            from app.config import get_settings
            process_document(job.resource_id, SessionLocal, get_settings().upload_dir, job.id, args.lease)
        elif job.kind == "parse":
            resource_id = job.resource_id
            def parse_lease(db, lock):
                from sqlalchemy import select
                query = select(BackgroundJob).where(BackgroundJob.id == args.job_id).execution_options(populate_existing=True)
                if lock:
                    query = query.with_for_update()
                current = db.scalar(query)
                return bool(current and current.status == "running" and current.lease_token == args.lease)
            process_dataset(resource_id, SessionLocal, projection_engine, lease_guard=parse_lease)
            db.expire_all()
            dataset = db.get(Dataset, resource_id)
            from sqlalchemy import select
            job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == args.job_id).with_for_update().execution_options(populate_existing=True))
            if not job or job.lease_token != args.lease or job.status != "running":
                db.rollback()
                return
            job.status = "succeeded" if dataset and dataset.status == "ready" else "failed"
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()


if __name__ == "__main__":
    main()
