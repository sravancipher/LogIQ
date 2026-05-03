from fastapi import APIRouter

from app.api.v1.routes.alerts import router as alerts_router
from app.api.v1.routes.insights import router as insights_router
from app.api.v1.routes.integrations import router as integrations_router
from app.api.v1.routes.logs import router as logs_router
from app.api.v1.routes.projects import router as projects_router

api_router = APIRouter()
api_router.include_router(projects_router)
api_router.include_router(logs_router)
api_router.include_router(insights_router)
api_router.include_router(alerts_router)
api_router.include_router(integrations_router)
