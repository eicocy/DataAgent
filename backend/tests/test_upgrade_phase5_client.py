import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import pytest


def client_api():
    assert importlib.util.find_spec('app.sandbox.client'), 'Sandbox client is missing'
    from app.sandbox.client import SandboxClient
    return SandboxClient


def test_unavailable_runtime_fails_without_host_execution():
    Client = client_api()
    from app.sandbox.settings import SandboxSettings
    from app.sandbox.validator import SandboxError
    client=Client(SandboxSettings(enabled=True,broker_token='t'*32,broker_url='http://127.0.0.1:1'))
    with pytest.raises(SandboxError,match='SANDBOX_UNAVAILABLE'): client.health()


def test_worker_cancellation_calls_broker_delete():
    Client = client_api()
    from app.sandbox.settings import SandboxSettings
    paths=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length',0)))
            body=json.dumps({'job_id':'a'*32,'status':'running'}).encode()
            self.send_response(202); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_DELETE(self):
            paths.append(self.path); self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        client=Client(SandboxSettings(enabled=True,broker_token='t'*32,broker_url=f'http://127.0.0.1:{server.server_port}'))
        checks=[0]
        def check():
            checks[0]+=1
            if checks[0]>1: raise RuntimeError('cancelled by owner')
        with pytest.raises(RuntimeError,match='cancelled by owner'):
            client.run({'code':'result={"x":1}','owner':'b'*64,'inputs':[{'alias':'primary','dataset_id':1,'dataset_version_id':2,'columns':['x'],'rows':[{'x':1}]}]},check_lease=check)
        assert paths == ['/jobs/'+'a'*32]
    finally: server.shutdown(); server.server_close()


def test_code_tool_has_no_public_registry_entry():
    from app.tools.registry import tool_registry
    from app.analysis.catalog import build_registry
    assert 'python_sandbox' not in tool_registry()
    assert not build_registry(include_legacy=True).exists('python_sandbox')
