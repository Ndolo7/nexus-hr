from fastapi import APIRouter
from app.api.routes.endpoints import router as endpoints_router

api_router = APIRouter()
api_router.include_router(endpoints_router, tags=["nexus-hr"])
