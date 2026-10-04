"""Offline database-dump + uploads/artifacts bundle; never connects to a database."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

MAX_BYTES=20*1024**3
MAX_FILES=100000


def digest(stream):
    value=hashlib.sha256()
    while chunk:=stream.read(1024*1024): value.update(chunk)
    return value.hexdigest()


def safe_member(name):
    path=PurePosixPath(name)
    if '\\' in name or path.is_absolute() or '..' in path.parts or ':' in name:
        raise ValueError('BACKUP_PATH_INVALID')
    if name!='database.sql' and not (len(path.parts)>=3 and path.parts[0]=='data' and path.parts[1] in {'uploads','artifacts'}):
        raise ValueError('BACKUP_PATH_INVALID')
    return path


def bundle_backup(database_dump,data_dir,destination):
    dump=Path(database_dump).resolve(); data=Path(data_dir).resolve(); destination=Path(destination).resolve()
    if not dump.is_file() or not data.is_dir() or destination.is_relative_to(data) or destination.exists():
        raise ValueError('BACKUP_SOURCE_OR_DESTINATION_INVALID')
    files=[('database.sql',dump)]
    for folder in ('uploads','artifacts'):
        directory=data/folder
        if not directory.exists(): continue
        if directory.is_symlink(): raise ValueError('BACKUP_SYMLINK_DENIED')
        for path in directory.rglob('*'):
            if path.is_symlink() or not path.resolve().is_relative_to(data): raise ValueError('BACKUP_SYMLINK_DENIED')
            if path.is_file(): files.append(('data/'+path.relative_to(data).as_posix(),path))
    if len(files)>MAX_FILES or sum(path.stat().st_size for _,path in files)>MAX_BYTES:
        raise ValueError('BACKUP_LIMIT')
    manifest={'format':'datalens-backup-1','files':{}}
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:
        with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
            for name,path in files:
                safe_member(name)
                value=hashlib.sha256()
                with path.open('rb') as source,archive.open(name,'w') as target:
                    while chunk:=source.read(1024*1024): target.write(chunk); value.update(chunk)
                manifest['files'][name]=value.hexdigest()
            archive.writestr('manifest.json',json.dumps(manifest,sort_keys=True))
        verify_backup(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def verify_backup(archive_path):
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members=archive.infolist(); names=[member.filename for member in members]
            if len(names)!=len(set(names)) or len(names)>MAX_FILES+1 or sum(m.file_size for m in members)>MAX_BYTES+16*1024*1024:
                raise ValueError('BACKUP_LIMIT')
            manifest_info=archive.getinfo('manifest.json')
            if manifest_info.file_size>16*1024*1024: raise ValueError('BACKUP_LIMIT')
            manifest=json.loads(archive.read('manifest.json'))
            if not isinstance(manifest,dict) or set(manifest)!={'format','files'} or manifest['format']!='datalens-backup-1' or not isinstance(manifest['files'],dict):
                raise ValueError('BACKUP_MANIFEST_INVALID')
            if set(names)!=set(manifest['files'])|{'manifest.json'} or 'database.sql' not in names:
                raise ValueError('BACKUP_MANIFEST_INVALID')
            for member in members:
                if member.filename=='manifest.json': continue
                safe_member(member.filename)
                if member.is_dir() or stat.S_ISLNK(member.external_attr>>16): raise ValueError('BACKUP_PATH_INVALID')
                with archive.open(member) as source:
                    if digest(source)!=manifest['files'][member.filename]: raise ValueError('BACKUP_CHECKSUM_INVALID')
            return manifest
    except (OSError,KeyError,TypeError,zipfile.BadZipFile,json.JSONDecodeError):
        raise ValueError('BACKUP_INVALID') from None


def restore_bundle(archive_path,target_dir):
    target=Path(target_dir)
    if target.is_symlink() or target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('BACKUP_RESTORE_TARGET_NOT_EMPTY')
    target=target.resolve()
    manifest=verify_backup(archive_path)
    target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for name in manifest['files']:
            path=target/Path(*safe_member(name).parts)
            if not path.resolve().is_relative_to(target): raise ValueError('BACKUP_PATH_INVALID')
            path.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(name) as source,path.open('xb') as out:
                while chunk:=source.read(1024*1024): out.write(chunk)
    return target


def main():
    parser=argparse.ArgumentParser(description='Offline verified DataLens backup bundle')
    sub=parser.add_subparsers(dest='operation',required=True)
    backup=sub.add_parser('bundle'); backup.add_argument('--database-dump',required=True); backup.add_argument('--data-dir',required=True); backup.add_argument('--output',required=True)
    verify=sub.add_parser('verify'); verify.add_argument('archive')
    restore=sub.add_parser('restore-files'); restore.add_argument('archive'); restore.add_argument('--target-dir',required=True)
    args=parser.parse_args()
    if args.operation=='bundle': bundle_backup(args.database_dump,args.data_dir,args.output)
    elif args.operation=='verify': verify_backup(args.archive)
    else: restore_bundle(args.archive,args.target_dir)
    print('Backup operation verified. Database restore must be performed separately against an explicitly chosen empty database.')


if __name__=='__main__': main()
