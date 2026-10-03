"""Versioned strategy catalog. Templates never execute tools themselves."""
from datetime import datetime, UTC
from sqlalchemy import select
from app.models import AnalysisProfileRecord
from app.profiles.catalog import profile_catalog
from app.profiles.schemas import AnalysisProfile


class ProfileService:
    def __init__(self, db):
        self.db = db

    def seed(self):
        existing = set(self.db.execute(select(AnalysisProfileRecord.profile_id, AnalysisProfileRecord.version)).all())
        for item in profile_catalog()['items']:
            if (item['id'], item['version']) not in existing:
                values = dict(profile_id=item['id'], version=item['version'], definition_json=item, created_at=datetime.now(UTC))
                dialect = self.db.get_bind().dialect.name
                if dialect == 'sqlite':
                    from sqlalchemy.dialects.sqlite import insert
                    self.db.execute(insert(AnalysisProfileRecord).values(**values).on_conflict_do_nothing(index_elements=['profile_id', 'version']))
                elif dialect == 'mysql':
                    from sqlalchemy.dialects.mysql import insert
                    self.db.execute(insert(AnalysisProfileRecord).values(**values).on_duplicate_key_update(version=item['version']))
                else:
                    self.db.add(AnalysisProfileRecord(**values))
        self.db.flush()

    def catalog(self, category=None):
        base = profile_catalog(category)
        # Disk catalog defines published versions; persisted snapshots remain immutable.
        rows = {(r.profile_id, r.version): r for r in self.db.scalars(select(AnalysisProfileRecord))}
        for i, item in enumerate(base['items']):
            row = rows.get((item['id'], item['version']))
            if row:
                base['items'][i] = dict(row.definition_json, availability=item['availability'])
            if base['items'][i]['availability'] != 'planned':
                base['items'][i]['supported_depths'] = ['FAST', 'STANDARD', 'DEEP']
        base['profile_execution'] = True
        return base

    def get(self, profile_id):
        item = next((p for p in self.catalog()['items'] if p['id'] == profile_id), None)
        if item is None:
            raise ValueError('PROFILE_NOT_FOUND')
        return AnalysisProfile.model_validate(item)

    def selected(self, ids):
        if len(ids) > 3 or len(ids) != len(set(ids)):
            raise ValueError('PROFILE_LIMIT')
        profiles = [self.get(key) for key in ids]
        if any(p.availability == 'planned' for p in profiles):
            raise ValueError('PROFILE_UNAVAILABLE')
        return profiles
