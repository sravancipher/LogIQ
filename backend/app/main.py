from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.v1.api import api_router
from app.core.config import settings
app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard", tags=["dashboard"])
def dashboard() -> FileResponse:
    return FileResponse("dashboard/app.html")
