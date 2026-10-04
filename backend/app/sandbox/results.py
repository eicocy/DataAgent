"""Untrusted container outputs: bounded archive, scalar JSON and re-encoded PNG."""
import base64
import io
import json
import math
import tarfile
import warnings
from pathlib import PurePosixPath
import pandas as pd
from PIL import Image
from app.sandbox.protocol import MAX_OUTPUT_BYTES
from app.sandbox.validator import SandboxError


def read_output_archive(chunks):
    content = bytearray()
    for chunk in chunks:
        if len(content) + len(chunk) > MAX_OUTPUT_BYTES + 1024 * 1024:
            raise SandboxError('SANDBOX_OUTPUT_LIMIT')
        content.extend(chunk)
    files = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:') as tar:
            total = 0
            for member in tar:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or len(path.parts) > 2 or member.issym() or member.islnk():
                    raise SandboxError('SANDBOX_OUTPUT_PATH')
                if member.isdir() and member.name in {'output', '.'}:
                    continue
                name = path.name
                if not member.isfile() or name in files or name not in {'complete','result.json','image-0.png','image-1.png','image-2.png','image-3.png'}:
                    raise SandboxError('SANDBOX_OUTPUT_PATH')
                if len(path.parts) == 2 and path.parts[0] != 'output':
                    raise SandboxError('SANDBOX_OUTPUT_PATH')
                total += member.size
                if len(files) >= 6 or member.size < 0 or total > MAX_OUTPUT_BYTES:
                    raise SandboxError('SANDBOX_OUTPUT_LIMIT')
                files[name] = tar.extractfile(member).read()
        if 'result.json' not in files:
            raise SandboxError('SANDBOX_RESULT_MISSING')
        if 'complete' in files and files.pop('complete') != b'1':
            raise SandboxError('SANDBOX_OUTPUT_INVALID')
        result = json.loads(files.pop('result.json'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        return dict(result=result, images=[base64.b64encode(files[name]).decode() for name in sorted(files)])
    except SandboxError:
        raise
    except (ValueError, TypeError, OSError, tarfile.TarError, RecursionError):
        raise SandboxError('SANDBOX_OUTPUT_INVALID') from None


def scalar(value):
    if type(value) not in (str, int, float, bool, type(None)) or isinstance(value, float) and not math.isfinite(value):
        raise SandboxError('SANDBOX_RESULT_VALUE')
    if isinstance(value, str) and len(value) > 65536:
        raise SandboxError('SANDBOX_RESULT_VALUE')
    return value


def safe_png(encoded):
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > 16 * 1024 * 1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != 'PNG' or image.width * image.height > 16000000:
                    raise ValueError()
                image.load()
                output = io.BytesIO()
                image.convert('RGB').save(output, format='PNG')
                if output.tell() > 16 * 1024 * 1024:
                    raise ValueError()
                return output.getvalue()
    except Exception:
        raise SandboxError('SANDBOX_IMAGE_INVALID') from None


def validate_output(payload, encoded_images=None):
    from app.analysis.models import TableResult, ColumnSpec
    from app.execution.validators import validate_value
    if not isinstance(payload, dict):
        raise SandboxError('SANDBOX_RESULT_SCHEMA')
    if set(payload) == {'columns','rows'}:
        columns, rows = payload['columns'], payload['rows']
    elif not {'columns','rows'} & set(payload):
        if not payload or len(payload) > 256:
            raise SandboxError('SANDBOX_RESULT_SCHEMA')
        columns, rows = list(payload), [payload]
    else:
        raise SandboxError('SANDBOX_RESULT_SCHEMA')
    if not isinstance(columns, list) or not 1 <= len(columns) <= 256 or any(not isinstance(c,str) or not c or len(c)>256 for c in columns) or len(set(columns)) != len(columns):
        raise SandboxError('SANDBOX_RESULT_SCHEMA')
    if not isinstance(rows, list) or len(rows) > 50000 or any(not isinstance(row,dict) or set(row) != set(columns) for row in rows):
        raise SandboxError('SANDBOX_RESULT_SCHEMA')
    for row in rows:
        for value in row.values(): scalar(value)
    if len(json.dumps(payload, allow_nan=False, ensure_ascii=False).encode()) > MAX_OUTPUT_BYTES:
        raise SandboxError('SANDBOX_OUTPUT_LIMIT')
    table = TableResult(columns=[ColumnSpec(name=c, dtype='scalar') for c in columns], rows=rows, row_count=len(rows))
    validate_value(table.model_dump())
    images = encoded_images or []
    if not isinstance(images,list) or len(images) > 4:
        raise SandboxError('SANDBOX_IMAGE_INVALID')
    decoded = [safe_png(image) for image in images]
    if sum(len(image) for image in decoded)+len(json.dumps(payload,ensure_ascii=False).encode())>MAX_OUTPUT_BYTES:
        raise SandboxError('SANDBOX_OUTPUT_LIMIT')
    return table, pd.DataFrame(rows, columns=columns), decoded
