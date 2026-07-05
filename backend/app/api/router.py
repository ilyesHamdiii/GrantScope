from fastapi import APIRouter

from app.api.routes import analysis, cases, imports, inventory, system


api_router = APIRouter(prefix="/api/v1")

api_router.include_router(system.router)
api_router.include_router(imports.router)
api_router.include_router(inventory.router)
api_router.include_router(analysis.router)
api_router.include_router(cases.router)