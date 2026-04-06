from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.auth import router as auth_router
from starlette.responses import PlainTextResponse
app = FastAPI(
    title="Smart Waste Monitoring API",
    version="0.2.0",
    description="SWE Prototype — Phase 2 (Auth + RBAC + AES-256)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False with "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(router,      prefix="/api/v1")

@app.on_event("startup")
async def startup():
    print("✅ Smart Waste API v0.2.0 started — Auth + RBAC enabled")
    
@app.get("/loaderio-034eb76f20f901e3b3899f5ee3cdae9a")
async def loaderio():
    return PlainTextResponse("loaderio-034eb76f20f901e3b3899f5ee3cdae9a")