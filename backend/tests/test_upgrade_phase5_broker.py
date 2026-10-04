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
        get_archive=lambda path:([stream.getvalue()],{}),remove=lambda **kw:removed.append(True))
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
