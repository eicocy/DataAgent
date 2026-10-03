"""Backfill existing projections. Default dry-run; never reparses original files."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal, engine, projection_engine
from app.models import Dataset
from app.datasets.versions import backfill_dataset
from app.services.analysis import select_projection_bind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--batch-size', type=int, default=100)
    args = parser.parse_args()
    if args.batch_size <= 0:
        parser.error('batch-size must be positive')
    last_id = 0
    failures = 0
    with SessionLocal() as db:
        while True:
            datasets = list(db.scalars(select(Dataset).where(Dataset.id > last_id, Dataset.status == 'ready').order_by(Dataset.id).limit(args.batch_size)))
            if not datasets:
                break
            for dataset in datasets:
                identifier = dataset.id
                try:
                    outcome = backfill_dataset(db, dataset, select_projection_bind(dataset, engine, projection_engine), get_settings().upload_dir, apply=args.apply)
                    print(outcome)
                except Exception:
                    db.rollback()
                    failures += 1
                    print({'dataset_id': identifier, 'status': 'failed', 'code': 'VERSION_BACKFILL_FAILED'})
                last_id = identifier
    return 1 if failures else 0

if __name__ == '__main__':
    raise SystemExit(main())
