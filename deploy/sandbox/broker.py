"""Trusted Docker owner. No caller-provided Docker flags, mounts or image names."""
import hmac
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from app.sandbox.protocol import RunRequest, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES
from app.sandbox.results import read_output_archive

LABEL = 'datalens.sandbox.scope'
LEASE_SECONDS = 5


class Job:
    def __init__(self, id, owner, deadline, lease_until):
        self.id, self.owner = id, owner
        self.deadline, self.lease_until = deadline, lease_until
        self.status, self.error_code = 'running', None
        self.container, self.output = None, None
        self.finished = None


class Broker:
    def __init__(self, engine, image, scope='datalens'):
        info = engine.info()
        if info.get('OSType') != 'linux' or not all(info.get(key) for key in ('MemoryLimit','SwapLimit','PidsLimit')):
            raise ValueError('SANDBOX_KERNEL_LIMITS_UNAVAILABLE')
        resolved = engine.images.get(image)
        if resolved.labels.get('datalens.sandbox.protocol') != '1.0':
            raise ValueError('SANDBOX_IMAGE_PROTOCOL_INVALID')
        self.engine, self.image, self.scope = engine, resolved.id, scope
        self.jobs, self.lock = {}, threading.RLock()
        self.stopping = threading.Event()
        # Only this broker scope; never enumerate/delete application containers.
        for container in engine.containers.list(all=True, filters={'label':f'{LABEL}={scope}'}):
            container.remove(force=True)

    def container_options(self, job_id):
        return dict(image=self.image, command=['python','-I','/opt/runtime.py'],
            name=f'datalens-sandbox-{job_id}', labels={LABEL:self.scope},
            user='65532:65532', read_only=True, network_mode='none',
            cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
            nano_cpus=1000000000, mem_limit=512*1024*1024, memswap_limit=512*1024*1024,
            pids_limit=64, stdin_open=True, working_dir='/output',
            tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=32m,mode=1777',
                   '/output':'rw,noexec,nosuid,nodev,size=64m,mode=1777'},
            ulimits=[{'Name':'fsize','Soft':MAX_OUTPUT_BYTES,'Hard':MAX_OUTPUT_BYTES},{'Name':'nofile','Soft':128,'Hard':128}],
            log_config={'Type':'local','Config':{'max-size':'64k','max-file':'1'}})

    def submit(self, request):
        request = RunRequest.model_validate(request)
        with self.lock:
            if self.stopping.is_set() or any(j.status == 'running' for j in self.jobs.values()):
                raise ValueError('SANDBOX_BUSY')
            self.reap()
            if len(self.jobs) >= 16:
                raise ValueError('SANDBOX_BUSY')
            now = time.monotonic()
            job = Job(uuid.uuid4().hex,request.owner,now+request.timeout_seconds,now+LEASE_SECONDS)
            self.jobs[job.id] = job
            threading.Thread(target=self.run,args=(job,request),daemon=True).start()
            return self.view(job.id)

    def view(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError('SANDBOX_JOB_NOT_FOUND')
            return dict(job_id=job.id,status=job.status,error_code=job.error_code,**({'output':job.output} if job.status=='succeeded' else {}))

    def heartbeat(self, job_id):
        with self.lock:
            self.reap()
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError('SANDBOX_JOB_NOT_FOUND')
            if job.status == 'running':
                job.lease_until = time.monotonic() + LEASE_SECONDS
            return {key:value for key,value in self.view(job_id).items() if key!='output'}

    def fail(self, job, code):
        if job.status != 'running':
            return
        job.status, job.error_code, job.finished = 'failed', code, time.monotonic()
        if job.container:
            try: job.container.remove(force=True)
            except Exception: pass  # retry removal in runner finally and reaper

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job: self.fail(job,'SANDBOX_CANCELLED')

    def cancel_owner(self, owner):
        with self.lock:
            for job in list(self.jobs.values()):
                if job.owner == owner: self.fail(job,'SANDBOX_CANCELLED')

    def reap(self):
        with self.lock:
            now = time.monotonic()
            for job in list(self.jobs.values()):
                if job.status == 'running' and now >= job.deadline:
                    self.fail(job,'SANDBOX_TIMEOUT')
                elif job.status == 'running' and now >= job.lease_until:
                    self.fail(job,'SANDBOX_LEASE_EXPIRED')
                if job.finished and now-job.finished > 60:
                    self.jobs.pop(job.id,None)

    def run(self, job, request):
        container = None
        stream = None
        try:
            with self.lock:
                if job.status != 'running': return
                container = self.engine.containers.create(**self.container_options(job.id))
                job.container = container
                stream = container.attach_socket(params={'stdin':1,'stream':1})
                container.start()
                # Fixed line protocol, no host files/credentials in the container.
                body = json.dumps(request.model_dump(exclude={'owner'}),allow_nan=False,ensure_ascii=False).encode()+b'\n'
                stream._sock.sendall(body)
                stream.close(); stream = None
            while not self.stopping.wait(.2):
                with self.lock:
                    self.reap()
                    if job.status != 'running': return
                container.reload()
                state = container.attrs['State']
                if not state['Running']:
                    if state.get('OOMKilled'): raise ValueError('SANDBOX_OOM')
                    if state.get('ExitCode')==3: raise ValueError('SANDBOX_OUTPUT_LIMIT')
                    raise ValueError('SANDBOX_EXECUTION_FAILED')
                try:
                    marker, _ = container.get_archive('/output/complete')
                    # Consume the tiny probe so its HTTP connection is closed.
                    if sum(len(chunk) for chunk in marker) > 16384:
                        raise ValueError('SANDBOX_OUTPUT_LIMIT')
                except Exception as probe_error:
                    if probe_error.__class__.__name__ == 'NotFound': continue
                    raise
                chunks, _ = container.get_archive('/output')
                output = read_output_archive(chunks)
                with self.lock:
                    self.reap()
                    if job.status != 'running': return
                    job.output, job.status, job.finished = output, 'succeeded', time.monotonic()
                return
        except Exception as exc:
            code = getattr(exc,'code',str(exc))
            allowed = {'SANDBOX_OOM','SANDBOX_EXECUTION_FAILED','SANDBOX_OUTPUT_LIMIT','SANDBOX_OUTPUT_PATH','SANDBOX_OUTPUT_INVALID','SANDBOX_RESULT_MISSING'}
            with self.lock:
                self.fail(job,code if code in allowed else 'SANDBOX_RUNTIME_UNAVAILABLE')
        finally:
            if stream:
                try: stream.close()
                except Exception: pass
            if container:
                try: container.remove(force=True)
                except Exception: pass

    def close(self):
        self.stopping.set()
        with self.lock:
            for job in self.jobs.values(): self.fail(job,'SANDBOX_INTERRUPTED')


def server_for(broker, token, address=('0.0.0.0',8090)):
    if len(token) < 32:
        raise ValueError('SANDBOX_TOKEN_REQUIRED')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def response(self,status,value):
            body=json.dumps(value,allow_nan=False).encode()
            self.send_response(status); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def handle_request(self):
            if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                return self.response(401,{'error_code':'SANDBOX_UNAUTHORIZED'})
            try:
                self.connection.settimeout(5)
                if self.command == 'GET' and self.path == '/health':
                    broker.engine.ping()
                    return self.response(200,{'status':'ready','protocol':'1.0'})
                if self.command == 'POST' and self.path == '/jobs':
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=MAX_INPUT_BYTES or self.headers.get('Transfer-Encoding'):
                        raise ValueError('SANDBOX_INPUT_LIMIT')
                    body=self.rfile.read(length)
                    if len(body)!=length: raise ValueError('SANDBOX_INPUT_LIMIT')
                    return self.response(202,broker.submit(json.loads(body)))
                match=re.fullmatch(r'/jobs/([a-f0-9]{32})(/heartbeat)?',self.path)
                if match:
                    id, action = match.groups()
                    if self.command=='GET' and not action: return self.response(200,broker.view(id))
                    if self.command=='POST' and action: return self.response(200,broker.heartbeat(id))
                    if self.command=='DELETE' and not action:
                        broker.cancel(id); return self.response(200,{'status':'cancelled'})
                owner=re.fullmatch(r'/owners/([a-f0-9]{64})',self.path)
                if self.command=='DELETE' and owner:
                    broker.cancel_owner(owner.group(1)); return self.response(200,{'status':'cancelled'})
                return self.response(404,{'error_code':'SANDBOX_ROUTE_NOT_FOUND'})
            except Exception as exc:
                code=str(exc)
                safe = code if code in {'SANDBOX_BUSY','SANDBOX_JOB_NOT_FOUND','SANDBOX_INPUT_LIMIT'} else 'SANDBOX_REQUEST_INVALID'
                return self.response(400,{'error_code':safe})
        do_GET=do_POST=do_DELETE=handle_request
    server=ThreadingHTTPServer(address,Handler)
    server.daemon_threads=True
    return server


def main():
    import docker
    import signal
    engine = docker.from_env(timeout=5)
    broker = Broker(engine,os.environ.get('SANDBOX_IMAGE','datalens-sandbox:2.0.5'))
    server = server_for(broker,os.environ.get('SANDBOX_BROKER_TOKEN',''))
    def stop(*args):
        broker.close()
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    def maintenance():
        while not broker.stopping.wait(.25): broker.reap()
    threading.Thread(target=maintenance,daemon=True).start()
    try: server.serve_forever()
    finally: broker.close(); server.server_close()


if __name__=='__main__': main()
