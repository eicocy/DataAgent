import logging
import re
import traceback
import uuid
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException


class SafeFormatter(logging.Formatter):
    def formatException(self, exc_info):
        # Exception values and source lines can contain SQL literals, prompts or secrets.
        frames = traceback.extract_tb(exc_info[2])
        return "\n".join([f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in frames] + [exc_info[0].__name__])

    def format(self, record):
        message = record.getMessage()
        if any(marker in message.lower() for marker in ("[sql:", "[parameters:", "password", "api_key", "://", "authorization", "prompt", "bearer", "broker_token", "generated_code")):
            record = logging.makeLogRecord(dict(record.__dict__, msg="[sensitive log message omitted]", args=()))
        return super().format(record)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().handlers[:] = [handler]
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True


class BodyTooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, detail={"code": "REQUEST_TOO_LARGE", "message": "请求体超过限制"})


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        try:
            oversized = length is not None and (int(length) < 0 or int(length) > self.max_bytes)
        except ValueError:
            oversized = True
        if oversized:
            return await JSONResponse(status_code=413, content={"code": "REQUEST_TOO_LARGE", "message": "请求体超过限制", "data": None})(scope, receive, send)
        total = 0
        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                raise BodyTooLarge()
            return message
        try:
            return await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            return await JSONResponse(status_code=413, content={"code": "REQUEST_TOO_LARGE", "message": "请求体超过限制", "data": None})(scope, receive, send)
