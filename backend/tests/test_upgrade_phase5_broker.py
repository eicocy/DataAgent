import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest


def broker_module():
    path = Path(__file__).resolve().parents[2] / 'deploy/sandbox/broker.py'
    assert path.exists(), 'Independent broker is missing'
    spec = importlib.util.spec_from_file_location('phase5_broker', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class Engine:
    def __init__(self):
        self.removed = []
        self.containers = SimpleNamespace(list=lambda **kwargs: [SimpleNamespace(remove=lambda **kw:self.removed.append(kw))])
        self.images = SimpleNamespace(get=lambda _:SimpleNamespace(id='sha256:fixed',labels={'datalens.sandbox.protocol':'1.0'}))
        self.info = lambda: {'OSType':'linux','MemoryLimit':True,'SwapLimit':True,'PidsLimit':True}


def test_broker_uses_fixed_isolation_and_removes_its_orphans():
    module = broker_module(); engine = Engine()
    broker = module.Broker(engine, 'trusted-image', scope='phase5-test')
    assert len(engine.removed) == 1
    options = broker.container_options('a'*32)
    assert options['image'] == 'sha256:fixed'
    assert options['network_mode'] == 'none' and options['read_only'] is True
    assert options['user'] != 'root' and options['cap_drop'] == ['ALL']
    assert options['mem_limit'] == options['memswap_limit'] == 512 * 1024 * 1024
    assert options['nano_cpus'] == 1000000000 and options['pids_limit'] == 64
    assert not options.get('volumes') and not options.get('environment')
    assert options['log_config']['Config']['compress'] == 'false'


def test_reaper_retries_failed_container_removal():
    import time
    module = broker_module(); broker = module.Broker(Engine(), 'trusted-image')
    attempts = []
    def remove(**kwargs):
        attempts.append(True)
        if len(attempts) == 1: raise OSError('temporarily unavailable')
    job = module.Job('a'*32, 'b'*64, 0, 0)
    job.container = SimpleNamespace(remove=remove)
    broker.jobs[job.id] = job
    broker.fail(job, 'SANDBOX_CANCELLED')
    job.finished = time.monotonic() - 61
    broker.reap()
    assert len(attempts) == 2 and job.container is None and job.id not in broker.jobs


def test_successful_delete_releases_result_and_memory():
    import time
    module=broker_module(); broker=module.Broker(Engine(),'trusted-image')
    job=module.Job('a'*32,'b'*64,0,0); job.status='succeeded'; job.finished=time.monotonic()
    job.output={'result':{'x':1},'images':[]}; broker.jobs[job.id]=job
    broker.cancel(job.id)
    assert job.output is None and job.id not in broker.jobs


def test_broker_bounds_total_resident_outputs(monkeypatch):
    module=broker_module(); broker=module.Broker(Engine(),'trusted-image')
    monkeypatch.setattr(module,'MAX_RESIDENT_OUTPUT_BYTES',100)
    with pytest.raises(ValueError,match='SANDBOX_OUTPUT_LIMIT'):
        broker.store_output(module.Job('a'*32,'b'*64,0,0),{'result':{'x':'a'*500},'images':[]})


def test_http_output_preserves_utf8_without_ascii_expansion():
    import http.client,threading,time
    module=broker_module(); broker=module.Broker(Engine(),'trusted-image')
    broker.engine.ping=lambda:True
    job=module.Job('a'*32,'b'*64,0,0); job.status='succeeded'; job.finished=time.monotonic()
    job.output={'result':{'label':'中文'},'images':[]}; broker.jobs[job.id]=job
    server=module.server_for(broker,'t'*32,('127.0.0.1',0)); threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
        connection.request('GET','/jobs/'+job.id,headers={'Authorization':'Bearer '+'t'*32})
        content=connection.getresponse().read()
        assert '中文'.encode() in content and b'\\u4e2d' not in content
        connection.close()
    finally: server.shutdown(); server.server_close(); broker.close()


def test_broker_cancel_and_expired_lease_destroy_active_container():
    module = broker_module(); broker = module.Broker(Engine(), 'trusted-image',scope='phase5-test')
    removed = []
    job = module.Job('b'*32, 'c'*64, deadline=0, lease_until=0)
    job.container = SimpleNamespace(remove=lambda **kwargs:removed.append(kwargs))
    broker.jobs[job.id] = job
    broker.reap()
    assert removed and job.status == 'failed' and job.error_code == 'SANDBOX_TIMEOUT'
    other = module.Job('d'*32, 'c'*64, deadline=10**10,lease_until=0)
    other.container = SimpleNamespace(remove=lambda **kwargs:removed.append(kwargs))
    broker.jobs[other.id] = other
    broker.reap()
    assert other.error_code == 'SANDBOX_LEASE_EXPIRED'


def test_broker_refuses_unlabelled_image_or_missing_kernel_limits():
    module = broker_module()
    engine = Engine(); engine.info = lambda:{'OSType':'linux','MemoryLimit':False,'SwapLimit':True,'PidsLimit':True}
    with pytest.raises(ValueError): module.Broker(engine,'trusted-image')


def test_broker_collects_tmpfs_output_before_container_stops():
    import io,json,tarfile,time
    module=broker_module(); engine=Engine(); removed=[]
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as tar:
        content=json.dumps({'x':2}).encode(); info=tarfile.TarInfo('output/result.json'); info.size=len(content)
        tar.addfile(info,io.BytesIO(content))
    container=SimpleNamespace(attach_socket=lambda **kw:SimpleNamespace(_sock=SimpleNamespace(sendall=lambda body:None),close=lambda:None),
        start=lambda:None,reload=lambda:None,attrs={'State':{'Running':True}},
        exec_run=lambda command,**kw:SimpleNamespace(output=[stream.getvalue()]) if kw.get('stream') else (0,b''),remove=lambda **kw:removed.append(True))
    engine.containers.create=lambda **kw:container
    broker=module.Broker(engine,'trusted-image',scope='phase5-test')
    now=time.monotonic(); job=module.Job('a'*32,'b'*64,now+.7,now+2); broker.jobs[job.id]=job
    from app.sandbox.protocol import RunRequest
    request=RunRequest.model_validate({'code':'result={"x":2}','owner':'b'*64,'inputs':[{'alias':'primary','dataset_id':1,'dataset_version_id':2,'columns':['x'],'rows':[{'x':1}]}]})
    broker.run(job,request)
    assert job.status=='succeeded' and job.output['result']=={'x':2}
    assert removed
    engine = Engine(); engine.images = SimpleNamespace(get=lambda _:SimpleNamespace(id='sha256:wrong',labels={}))
    with pytest.raises(ValueError): module.Broker(engine,'trusted-image')


def test_oom_during_ready_probe_keeps_kernel_failure_code():
    import time
    module=broker_module(); engine=Engine()
    container=SimpleNamespace(attach_socket=lambda **kw:SimpleNamespace(_sock=SimpleNamespace(sendall=lambda body:None),close=lambda:None),
        start=lambda:None,reload=lambda:None,attrs={'State':{'Running':True}},remove=lambda **kw:None)
    def probe(*args,**kwargs):
        container.attrs['State']={'Running':False,'OOMKilled':True,'ExitCode':137}
        return 137,b''
    container.exec_run=probe; engine.containers.create=lambda **kw:container
    broker=module.Broker(engine,'trusted-image'); now=time.monotonic()
    job=module.Job('a'*32,'b'*64,now+10,now+10); broker.jobs[job.id]=job
    from app.sandbox.protocol import RunRequest
    request=RunRequest.model_validate({'code':'result={"x":2}','owner':'b'*64,'inputs':[{'alias':'primary','dataset_id':1,'dataset_version_id':2,'columns':['x'],'rows':[{'x':1}]}]})
    broker.run(job,request)
    assert job.error_code=='SANDBOX_OOM'
