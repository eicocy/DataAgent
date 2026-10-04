"""Opt-in Linux Docker acceptance; ordinary CI uses deterministic broker tests."""
import importlib.util
from pathlib import Path
import os
import threading
import time
import uuid
import pytest

pytestmark=pytest.mark.skipif(os.environ.get('TEST_SANDBOX_DOCKER')!='1',reason='requires dedicated Linux Docker acceptance')


@pytest.fixture(scope='module')
def sandbox():
    import docker
    path=Path(__file__).resolve().parents[2]/'deploy/sandbox/broker.py'
    spec=importlib.util.spec_from_file_location('phase5_docker_broker',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    scope='acceptance-'+uuid.uuid4().hex
    engine=docker.from_env(timeout=5)
    broker=module.Broker(engine,'datalens-sandbox:2.0.5',scope=scope)
    server=module.server_for(broker,'test-only-broker-token-'+uuid.uuid4().hex,('127.0.0.1',0))
    # Handler's token closure is matched by this dedicated test settings only.
    server.server_close()
    token='test-only-broker-token-'+uuid.uuid4().hex
    server=module.server_for(broker,token,('127.0.0.1',0))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def maintenance():
        while not broker.stopping.wait(.1): broker.reap()
    threading.Thread(target=maintenance,daemon=True).start()
    from app.sandbox.client import SandboxClient
    from app.sandbox.settings import SandboxSettings
    client=SandboxClient(SandboxSettings(enabled=True,broker_url=f'http://127.0.0.1:{server.server_port}',broker_token=token))
    yield module,broker,client,engine,scope
    broker.close(); server.shutdown(); server.server_close()
    assert not engine.containers.list(all=True,filters={'label':f'{module.LABEL}={scope}'})
    engine.close()


def request(code,timeout=60):
    return dict(code=code,timeout_seconds=timeout,owner='a'*64,
        inputs=[{'alias':'primary','dataset_id':1,'dataset_version_id':2,'columns':['x'],'rows':[{'x':1},{'x':3}]}])


def test_real_container_computes_table_and_png(sandbox):
    _,broker,client,_,_=sandbox
    output=client.run(request('import numpy as np\nimport matplotlib.pyplot as plt\ndf=inputs["primary"]\nresult={"median":float(np.median(df["x"]))}\nfig, ax=plt.subplots()\nax.plot(df["x"])\nemit_image(fig)'))
    from app.sandbox.results import validate_output
    table,frame,images=validate_output(output['result'],output['images'])
    assert table.rows==[{'median':2.0}] and images[0].startswith(b'\x89PNG')


def test_real_container_kernel_isolation(sandbox):
    module,broker,_,engine,scope=sandbox
    container=engine.containers.create(**broker.container_options(uuid.uuid4().hex))
    try:
        # Trusted acceptance probe, never reachable from submitted user code.
        # Empty ENV evidence is checked without logging or returning any values.
        container.start(); container.reload()
        config=container.attrs['HostConfig']
        assert config['ReadonlyRootfs'] and config['NetworkMode']=='none'
        assert config['Memory']==config['MemorySwap']==512*1024*1024
        assert config['NanoCpus']==1000000000 and config['PidsLimit']==64
        assert config['CapDrop']==['ALL'] and 'no-new-privileges:true' in config['SecurityOpt']
        probe='import os,socket; assert os.getuid()!=0; assert not any(x in os.environ for x in ["DEEPSEEK_API_KEY","OPENAI_API_KEY","DATABASE_URL","SECRET_KEY","SANDBOX_BROKER_TOKEN"]); assert not os.path.exists("/var/run/docker.sock"); assert not os.path.exists("/data/uploads"); assert not os.path.exists("/input"); s=socket.socket(); s.settimeout(.5); blocked=False\ntry: s.connect(("1.1.1.1",443))\nexcept OSError: blocked=True\nassert blocked\nblocked=False\ntry: open("/etc/phase5-write-probe","w").write("x")\nexcept OSError: blocked=True\nassert blocked\nprint("ISOLATION_OK")'
        code,out=container.exec_run(['python','-c',probe])
        assert code==0 and b'ISOLATION_OK' in out
    finally: container.remove(force=True)


def test_real_oom_timeout_and_output_budget(sandbox):
    _,broker,client,_,_=sandbox
    from app.sandbox.validator import SandboxError
    with pytest.raises(SandboxError,match='SANDBOX_OOM'):
        client.run(request('import numpy as np\nx=np.ones(90000000)\nresult={"x":float(x.sum())}'))
    client.settings.timeout_seconds=2
    try:
        with pytest.raises(SandboxError,match='SANDBOX_TIMEOUT'):
            client.run(request('while True: pass'))
    finally: client.settings.timeout_seconds=60
    with pytest.raises(SandboxError,match='SANDBOX_OUTPUT_LIMIT'):
        client.run(request('result={"large":"a"*70000000}'))


def test_real_cancel_expiry_and_broker_restart_remove_orphans(sandbox):
    module,broker,client,engine,scope=sandbox
    from app.sandbox.protocol import RunRequest
    running=broker.submit(RunRequest.model_validate(request('while True: pass')))
    jid=running['job_id']; client._request('DELETE',f'/jobs/{jid}')
    assert broker.view(jid)['error_code']=='SANDBOX_CANCELLED'
    orphan=engine.containers.create(**broker.container_options(uuid.uuid4().hex)); orphan.start()
    restarted=module.Broker(engine,'datalens-sandbox:2.0.5',scope=scope)
    assert not engine.containers.list(all=True,filters={'label':f'{module.LABEL}={scope}'})
    restarted.close()
    expired=broker.submit(RunRequest.model_validate(request('while True: pass')))
    deadline=time.monotonic()+8
    while broker.view(expired['job_id'])['status']=='running' and time.monotonic()<deadline: time.sleep(.1)
    assert broker.view(expired['job_id'])['error_code']=='SANDBOX_LEASE_EXPIRED'
