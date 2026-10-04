"""Fixed broker protocol; no Docker SDK/socket and no local execution fallback."""
import hashlib
import http.client
import json
import re
import time
from urllib.parse import urlsplit
from app.sandbox.settings import get_sandbox_settings
from app.sandbox.protocol import RunRequest, MAX_OUTPUT_BYTES
from app.sandbox.validator import SandboxError


def owner_key(job_id, lease_token):
    return hashlib.sha256(f'{job_id}:{lease_token}'.encode()).hexdigest()


class SandboxClient:
    def __init__(self, settings=None):
        self.settings = settings or get_sandbox_settings()

    def _request(self, method, path, body=None):
        if not self.settings.enabled:
            raise SandboxError('SANDBOX_DISABLED')
        url=urlsplit(self.settings.broker_url)
        cls=http.client.HTTPSConnection if url.scheme=='https' else http.client.HTTPConnection
        connection=cls(url.hostname,url.port,timeout=2)
        try:
            encoded=json.dumps(body,allow_nan=False,ensure_ascii=False).encode() if body is not None else None
            connection.request(method,path,body=encoded,headers={'Authorization':'Bearer '+self.settings.broker_token,'Content-Type':'application/json'})
            response=connection.getresponse()
            maximum=MAX_OUTPUT_BYTES*4//3+4096 if method=='GET' and path.startswith('/jobs/') else 65536
            content=response.read(maximum+1)
            if len(content)>maximum: raise SandboxError('SANDBOX_OUTPUT_LIMIT')
            if response.status not in (200,202): raise SandboxError('SANDBOX_UNAVAILABLE')
            data=json.loads(content)
            if not isinstance(data,dict): raise SandboxError('SANDBOX_PROTOCOL_INVALID')
            return data
        except SandboxError: raise
        except (OSError, ValueError, http.client.HTTPException):
            raise SandboxError('SANDBOX_UNAVAILABLE') from None
        finally: connection.close()

    def health(self):
        value=self._request('GET','/health')
        if value != {'status':'ready','protocol':'1.0'}:
            raise SandboxError('SANDBOX_PROTOCOL_INVALID')
        return True

    def run(self, request, check_lease=None, deadline=None):
        check_lease=check_lease or (lambda:None)
        check_lease()
        now=time.monotonic()
        remaining=min(self.settings.timeout_seconds,60,deadline-now if deadline else 60)
        if remaining<1: raise SandboxError('SANDBOX_TIMEOUT')
        request=RunRequest.model_validate(dict(request,timeout_seconds=int(remaining)))
        job_id=None
        try:
            state=self._request('POST','/jobs',request.model_dump())
            job_id=state.get('job_id')
            if not isinstance(job_id,str) or not re.fullmatch(r'[a-f0-9]{32}',job_id):
                job_id=None
                raise SandboxError('SANDBOX_PROTOCOL_INVALID')
            expires=now+remaining
            while True:
                check_lease()
                if time.monotonic()>=expires: raise SandboxError('SANDBOX_TIMEOUT')
                state=self._request('POST',f'/jobs/{job_id}/heartbeat')
                if state.get('status')=='failed':
                    allowed={'SANDBOX_OOM','SANDBOX_TIMEOUT','SANDBOX_LEASE_EXPIRED','SANDBOX_CANCELLED','SANDBOX_EXECUTION_FAILED','SANDBOX_OUTPUT_PATH','SANDBOX_OUTPUT_LIMIT','SANDBOX_OUTPUT_INVALID','SANDBOX_RESULT_MISSING','SANDBOX_RUNTIME_UNAVAILABLE'}
                    code=state.get('error_code')
                    raise SandboxError(code if code in allowed else 'SANDBOX_EXECUTION_FAILED')
                if state.get('status')=='succeeded':
                    output=self._request('GET',f'/jobs/{job_id}').get('output')
                    if not isinstance(output,dict) or set(output)!={'result','images'}:
                        raise SandboxError('SANDBOX_PROTOCOL_INVALID')
                    check_lease()
                    return output
                if state.get('status')!='running': raise SandboxError('SANDBOX_PROTOCOL_INVALID')
                time.sleep(.25)
        finally:
            if job_id:
                try: self._request('DELETE',f'/jobs/{job_id}')
                except SandboxError: pass  # broker independently expires the lease

    def cancel_owner(self, job_id, lease_token):
        self._request('DELETE','/owners/'+owner_key(job_id,lease_token))


def cancel_job_sandbox(job_id, lease_token):
    try: settings=get_sandbox_settings()
    except ValueError: return
    if settings.enabled and lease_token:
        try: SandboxClient(settings).cancel_owner(job_id,lease_token)
        except SandboxError: pass
