from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from app.chat.router import router as chat_router
from app.design.router import router as design_router
from app.localities.router import router as localities_router
from app.projects.routes import router as projects_router
from app.requirements.router import router as requirements_router

app = FastAPI(title="BuildSmart API")
app.include_router(projects_router)
app.include_router(localities_router)
app.include_router(requirements_router)
app.include_router(design_router)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
