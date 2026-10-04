"""Trusted runner. Only copied into the non-root/no-network execution image."""
import builtins
import importlib
import json
import math
from pathlib import Path
import sys
import time
from decimal import Decimal
import pandas as pd

# -I ignores PYTHONPATH; only this image's trusted package is installed here.
from app.sandbox.validator import validate_code, MODULES, BUILTINS
from app.sandbox.protocol import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES


def main():
    line = sys.stdin.buffer.readline(MAX_INPUT_BYTES+2)
    if len(line)>MAX_INPUT_BYTES+1 or not line.endswith(b'\n'): return 2
    request=json.loads(line)
    tree=validate_code(request['code'])
    inputs={}
    for snapshot in request['inputs']:
        frame=pd.DataFrame(snapshot['rows'],columns=snapshot['columns'])
        for column, dtype in snapshot.get('dtypes',{}).items():
            if dtype=='decimal': frame[column]=frame[column].map(lambda v:Decimal(str(v)) if v is not None else None)
            elif dtype in {'datetime','date'}: frame[column]=pd.to_datetime(frame[column])
            elif dtype=='integer': frame[column]=frame[column].astype('Int64')
        inputs[snapshot['alias']]=frame
    def restricted_import(name,globals=None,locals=None,fromlist=(),level=0):
        if level or name not in MODULES: raise ValueError('IMPORT_DENIED')
        return importlib.import_module(name) if fromlist else builtins.__import__(name,globals,locals,fromlist,level)
    images=[]
    def emit_image(figure):
        if len(images)>=4: raise ValueError('IMAGE_LIMIT')
        # No path is supplied by generated code.
        path=Path('/output')/f'image-{len(images)}.png'
        figure.savefig(path,format='png',dpi=100)
        images.append(path)
    namespace={'__builtins__':{name:getattr(builtins,name) for name in BUILTINS},'inputs':inputs,'emit_image':emit_image}
    namespace['__builtins__']['__import__']=restricted_import
    exec(compile(tree,'<sandbox>','exec'),namespace,namespace)
    result=namespace.get('result')
    # The application revalidates types and image content before persistence.
    body=json.dumps(result,ensure_ascii=False,allow_nan=False).encode()
    if len(body)+sum(p.stat().st_size for p in images)>MAX_OUTPUT_BYTES: return 3
    path=Path('/output/result.part')
    path.write_bytes(body)
    path.replace('/output/result.json')
    Path('/output/complete').write_bytes(b'1')
    # tmpfs is unmounted when a container stops. The broker copies bounded
    # outputs while alive, then destroys the container; no user code runs here.
    time.sleep(65)
    return 0


if __name__=='__main__':
    try: code=main()
    except BaseException: code=1
    sys.exit(code)
