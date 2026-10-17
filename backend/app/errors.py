from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    from app.diagnostics import error_info
    fields = [".".join(str(item) for item in error["loc"][1:]) for error in exc.errors()]
    info = error_info('VALIDATION_ERROR', '请求参数没有通过校验。', stage='request', retryable=False)
    info['field_errors'] = [{'path': '.'.join(str(i) for i in e['loc'][1:]), 'rule': e['type']} for e in exc.errors()[:20]]
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数不符合要求",
            "data": {"field_errors": fields, 'error_info': info},
        },
    )
