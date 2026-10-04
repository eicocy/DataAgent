import importlib.util
import io
import json
import tarfile
import pytest


def api():
    assert importlib.util.find_spec('app.sandbox'), 'Phase 5 sandbox module is missing'
    from app.sandbox.validator import validate_code, SandboxError
    return validate_code, SandboxError


def test_sandbox_is_disabled_by_default(monkeypatch):
    api()
    from app.sandbox.settings import SandboxSettings
    monkeypatch.delenv('SANDBOX_ENABLED', raising=False)
    assert SandboxSettings().enabled is False


@pytest.mark.parametrize('code', [
    'import os', 'import socket', 'import subprocess', 'import pickle',
    'import importlib', 'from numpy import load', 'from pandas import read_pickle',
    'eval("1+1")', 'exec("pass")', '__import__("os")',
    'getattr(inputs["primary"], "__class__")', 'inputs["primary"].__class__',
    'import pandas as pd\npd.read_csv("/etc/passwd")',
    'inputs["primary"].to_pickle("/output/x")',
    'inputs["primary"].query("x > 1")',
    'import numpy as np\nnp.ctypeslib.load_library("x", "/tmp")',
    'import pandas as pd\npd.set_option("io.excel.xlsx.writer", "x")',
    'inputs["primary"].apply("to_pickle", args=("/tmp/probe.pkl",))',
    'inputs["primary"].agg(["eval"])',
    'method="query"\ninputs["primary"].transform(method)',
])
def test_ast_rejects_escape_and_io(code):
    validate, error = api()
    with pytest.raises(error): validate(code)


def test_ast_accepts_in_memory_analysis():
    validate, _ = api()
    validate('import pandas as pd\nimport numpy as np\ndf = inputs["primary"]\nresult = {"columns": ["median"], "rows": [{"median": float(np.median(df["x"]))}]}')


def test_outputs_reject_traversal_links_nonfinite_and_fake_png():
    api()
    from app.sandbox.results import read_output_archive, validate_output
    from app.sandbox.validator import SandboxError
    for name, type_ in [('../result.json', tarfile.REGTYPE), ('result.json', tarfile.SYMTYPE)]:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            info = tarfile.TarInfo(name); info.type = type_; info.size = 0
            tar.addfile(info, io.BytesIO())
        with pytest.raises(SandboxError): read_output_archive([stream.getvalue()])
    with pytest.raises(SandboxError): validate_output({'columns':['x'], 'rows':[{'x':float('nan')}]})
    with pytest.raises(SandboxError): read_output_archive([b'not a tar'])


def test_valid_output_enters_typed_result_with_complete_rows():
    api()
    from app.sandbox.results import validate_output
    table, frame, images = validate_output({'columns':['x'], 'rows':[{'x':1},{'x':2}]})
    assert table.kind == 'table' and table.row_count == 2
    assert frame['x'].tolist() == [1,2] and images == []


def test_protocol_forbids_paths_credentials_and_docker_options():
    api()
    from app.sandbox.protocol import RunRequest
    from pydantic import ValidationError
    request = dict(code='result = {"x": 1}', owner='a'*64,
        inputs=[{'alias':'primary','dataset_id':1,'dataset_version_id':2,'columns':['x'],'rows':[{'x':1}]}])
    RunRequest.model_validate(request)
    for extra in ('image', 'volumes', 'environment', 'host_path', 'privileged'):
        with pytest.raises(ValidationError): RunRequest.model_validate(dict(request, **{extra:'untrusted'}))
