from fastapi import FastAPI

from app.localities.router import router as localities_router
from app.projects.routes import router as projects_router

app = FastAPI(title="sddproject API")
app.include_router(projects_router)
app.include_router(localities_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

