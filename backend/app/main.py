from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from app.chat.router import router as chat_router
from app.demo.router import router as demo_router
from app.design.router import router as design_router
from app.localities.router import router as localities_router
from app.projects.routes import router as projects_router
from app.observability import failure_log
from app.requirements.router import router as requirements_router


class ClientFailure(BaseModel):
    """A failure the frontend showed the user, reported back so it lands in the same log."""

    code: str
    message: str = ""
    detail: str = ""
    where: str = ""
    context: dict = {}

app = FastAPI(title="BuildSmart API")
app.include_router(projects_router)
app.include_router(localities_router)
app.include_router(requirements_router)
app.include_router(design_router)
app.include_router(demo_router)
app.include_router(chat_router)


# ---------------------------------------------------------------- failure logging
#
# Every failure the API produces is written to one JSON file (app/data/failures.json) so we can ask
# questions of them afterwards: which refusal fires most, which briefs never reach a drawing, and
# whether a fix actually removed a failure. Both kinds are recorded — a deliberate 422 refusal is
# correct behaviour AND a person who did not get a plan, and only counting crashes would hide that.

@app.exception_handler(StarletteHTTPException)
async def _log_http_failure(request: Request, exc: StarletteHTTPException):
    """4xx/5xx raised deliberately. 404s are noise, so they are not recorded."""
    already = getattr(request.state, "failure_recorded", False)
    if exc.status_code != 404 and not already:
        detail = exc.detail
        code, message, extra = "HTTP_ERROR", str(detail), ""
        if isinstance(detail, dict):
            code = str(detail.get("code", code))
            message = str(detail.get("message", ""))
            extra = str(detail.get("detail", ""))
        failure_log.refusal(
            code, message, extra,
            where=f"{request.method} {request.url.path}",
            context={"status_code": exc.status_code})
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def _log_validation_failure(request: Request, exc: RequestValidationError):
    """A rejected payload — a real failure for whoever sent it, and usually a contract mismatch."""
    failure_log.refusal(
        "REQUEST_VALIDATION_FAILED", "the request body was rejected", str(exc.errors())[:2000],
        where=f"{request.method} {request.url.path}", context={"status_code": 422})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def _log_crash(request: Request, exc: Exception):
    """Anything unhandled. Always a defect, and the traceback is kept."""
    failure_log.crash(exc, where=f"{request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "INTERNAL_ERROR",
                            "message": "אירעה שגיאה בלתי צפויה. הפרטים נרשמו ביומן התקלות.",
                            "detail": type(exc).__name__}})


@app.get("/failures")
def failures(limit: int = 100) -> dict:
    """The recorded failures, newest last, with counts by kind and by code."""
    entries = failure_log.read_all()
    return {"summary": failure_log.summary(), "entries": entries[-limit:]}


@app.post("/failures", status_code=201)
def report_failure(body: ClientFailure) -> dict:
    """The FRONTEND reporting a failure it showed the user.

    A backend-only log misses the half of the problem the person actually experiences: a request
    that never arrived, a response the UI could not use, a crash in the browser. Those end the
    journey just as completely as a 500 does.
    """
    failure_log.record("CLIENT", code=body.code, message=body.message, detail=body.detail,
                       where=body.where, context=body.context)
    return {"recorded": True}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
