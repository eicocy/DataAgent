"""Copy legacy projections without reparsing or deleting source tables.

Run from backend/: python scripts/migrate_projections.py [--apply]
Stop API/task execution and take a database backup before --apply. A preexisting
destination is never overwritten: inspect/resolve it before retrying.
"""
import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import MetaData, Table, create_engine, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AnalysisRecord, Dataset


def migrate(apply: bool = False) -> None:
    settings = get_settings()
    if not settings.projection_database_url:
        raise SystemExit("Configure PROJECTION_DATABASE_URL before migrating")
    source = create_engine(settings.migration_database_url or settings.database_url, hide_parameters=True)
    target = create_engine(settings.projection_database_url, hide_parameters=True)
    if source.url.get_backend_name() != 'mysql' or target.url.get_backend_name() != 'mysql':
        raise SystemExit("Projection migration requires MySQL source and destination")
    if (source.url.host, source.url.port, source.url.database) == (target.url.host, target.url.port, target.url.database):
        raise SystemExit("Source and destination must be different databases")
    from sqlalchemy import inspect
    try:
        with Session(source) as db:
            datasets = db.scalars(select(Dataset).order_by(Dataset.id)).all()
            for dataset in datasets:
                schema = dataset.projection_schema
                if schema == target.url.database:
                    print(f"dataset={dataset.id}: already points to destination; skipped")
                    continue
                if schema not in {None, '', source.url.database}:
                    raise RuntimeError(f"dataset={dataset.id}: unknown projection schema")
                if dataset.status != 'ready':
                    print(f"dataset={dataset.id}: not ready; skipped")
                    continue
                active = db.scalar(select(AnalysisRecord.id).where(AnalysisRecord.dataset_id == dataset.id, AnalysisRecord.status.in_(['pending', 'running'])).limit(1))
                if active:
                    raise RuntimeError(f"dataset={dataset.id}: active analysis; stop and finish tasks first")
                name = dataset.projection_table or f'dataset_{int(dataset.id)}'
                if not re.fullmatch(r'dataset_\d+', name):
                    raise RuntimeError(f"dataset={dataset.id}: invalid server projection identifier")
                if inspect(target).has_table(name):
                    raise RuntimeError(f"dataset={dataset.id}: destination already exists; never overwritten")
                original = Table(name, MetaData(), autoload_with=source)
                with source.connect() as connection:
                    count = connection.scalar(select(func.count()).select_from(original))
                print(f"dataset={dataset.id}: copy {count} rows with reflected SQL types" + (' [apply]' if apply else ' [dry-run]'))
                if not apply:
                    continue
                copied = original.to_metadata(MetaData(), schema=None)
                copied.create(target, checkfirst=False)
                # Each destination table is atomic for inserted rows. DDL is
                # intentionally not claimed transactional on MySQL.
                with source.connect() as src, target.begin() as dst:
                    rows = src.execute(select(original)).mappings()
                    for partition in rows.partitions(5000):
                        dst.execute(copied.insert(), [dict(row) for row in partition])
                    actual = dst.scalar(select(func.count()).select_from(copied))
                    if actual != count:
                        raise RuntimeError(f"dataset={dataset.id}: row count mismatch; metadata unchanged")
                dataset.projection_schema = target.url.database
                dataset.projection_table = name
                db.commit()
                print(f"dataset={dataset.id}: verified count and switched metadata; source retained")
    finally:
        source.dispose()
        target.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='copy and switch metadata; default is dry-run')
    args = parser.parse_args()
    try:
        migrate(args.apply)
    except Exception:
        # Never print driver exceptions, connection URLs or SQL/user values.
        print('Migration stopped. Source retained; inspect the destination and server logs before retrying.', file=sys.stderr)
        raise SystemExit(1)
