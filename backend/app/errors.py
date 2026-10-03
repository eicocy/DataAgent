from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [".".join(str(item) for item in error["loc"][1:]) for error in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数不符合要求",
            "data": {"field_errors": fields},
        },
    )
