from fastapi import Request, status
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger(__name__)

async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    logger.error("value_error", url=str(request.url), error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )

async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    logger.critical("runtime_error", url=str(request.url), error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal system error occurred. Intervention required."},
    )