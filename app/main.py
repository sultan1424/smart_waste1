from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

from app.api.routes import router
from app.api.auth import router as auth_router
from app.api.ml_routes import router as ml_router
from app.scheduler import start_scheduler

app = FastAPI(
    title="Smart Waste Monitoring API",
    version="0.3.0",
    description="SWE Prototype — Phase 3 (Prophet Forecasting + OR-Tools Routing)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(router,      prefix="/api/v1")
app.include_router(ml_router,   prefix="/api/v1")


@app.on_event("startup")
async def startup():
    print("✅ Smart Waste API v0.3.0 started — Prophet + OR-Tools enabled")
    start_scheduler()


@app.get("/loaderio-034eb76f20f901e3b3899f5ee3cdae9a")
async def loaderio():
    return PlainTextResponse("loaderio-034eb76f20f901e3b3899f5ee3cdae9a")