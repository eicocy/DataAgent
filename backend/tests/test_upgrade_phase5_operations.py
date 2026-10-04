import importlib.util
from pathlib import Path
import pytest


def backup_module():
    path=Path(__file__).resolve().parents[2]/'deploy/backup.py'
    assert path.exists(),'Backup/restore bundle tool is missing'
    spec=importlib.util.spec_from_file_location('phase5_backup',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_backup_verifies_content_and_restores_only_into_empty_directory(tmp_path):
    module=backup_module(); dump=tmp_path/'database.sql'; dump.write_text('SELECT 1;')
    data=tmp_path/'data'; (data/'uploads').mkdir(parents=True); (data/'artifacts').mkdir()
    (data/'uploads/x.csv').write_text('x\n1\n'); (data/'artifacts/result.json').write_text('{"x":1}')
    archive=module.bundle_backup(dump,data,tmp_path/'backup.zip')
    assert module.verify_backup(archive)['format']=='datalens-backup-1'
    restored=tmp_path/'restored'; module.restore_bundle(archive,restored)
    assert (restored/'database.sql').read_text()=='SELECT 1;'
    assert (restored/'data/uploads/x.csv').read_bytes()==(data/'uploads/x.csv').read_bytes()
    with pytest.raises(ValueError): module.restore_bundle(archive,restored)


def test_restore_rejects_tampering_and_archive_path_attack(tmp_path):
    import json,zipfile
    module=backup_module()
    for name in ('../database.sql','data/../../outside','/absolute'):
        path=tmp_path/'attack.zip'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr(name,'bad'); archive.writestr('manifest.json',json.dumps({'format':'datalens-backup-1','files':{name:'0'*64}}))
        with pytest.raises(ValueError): module.restore_bundle(path,tmp_path/'out')
        assert not (tmp_path/'out').exists()
