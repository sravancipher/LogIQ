from pathlib import Path

from fastapi import FastAPI, HTTPException
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


@app.get("/dashboard/assets/{asset_name:path}", tags=["dashboard"])
def dashboard_asset(asset_name: str) -> FileResponse:
    asset_path = (Path("dashboard") / asset_name).resolve()
    dashboard_root = Path("dashboard").resolve()

    # Prevent path traversal outside the dashboard directory.
    if dashboard_root not in asset_path.parents or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    return FileResponse(asset_path)
