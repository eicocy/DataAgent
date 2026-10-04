"""Trusted fixed Docker-exec exporter for tmpfs, never accepts a user path."""
from pathlib import Path
import sys
import tarfile

LIMIT=64*1024*1024
ALLOWED={'complete','result.json','image-0.png','image-1.png','image-2.png','image-3.png'}


def main():
    root=Path('/output')
    if sys.argv[1:] == ['ready']:
        return 0 if (root/'complete').is_file() else 3
    if sys.argv[1:] != ['archive']: return 2
    paths=list(root.iterdir())
    if len(paths)>6 or any(p.name not in ALLOWED or p.is_symlink() or not p.is_file() for p in paths): return 2
    if sum(p.stat().st_size for p in paths)>LIMIT: return 3
    with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
        for path in paths: archive.add(path,arcname='output/'+path.name,recursive=False)
    return 0


if __name__=='__main__':
    try: code=main()
    except BaseException: code=2
    sys.exit(code)
