from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.channels import router as channels_router
from app.api.v1.endpoints.pipelines import router as pipelines_router
from app.api.v1.endpoints.scripts import router as scripts_router
from app.api.v1.endpoints.videos import router as videos_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(channels_router)
api_router.include_router(videos_router)
api_router.include_router(scripts_router)
api_router.include_router(pipelines_router)
