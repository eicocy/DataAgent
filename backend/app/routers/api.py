from fastapi import APIRouter

from app.routers import analysis, analysis_runs, charts, auth, datasets, history, sessions, system


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(datasets.router)
api_router.include_router(analysis.router)
api_router.include_router(analysis_runs.router)
api_router.include_router(charts.router)
api_router.include_router(sessions.router)
api_router.include_router(history.router)
api_router.include_router(system.router)
