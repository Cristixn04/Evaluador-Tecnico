from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.auth import router as auth_router
from src.api.routers.evaluation import router as evaluation_router
from src.api.routers.invitations import router as invitations_router
from src.api.routers.organizations import router as organizations_router
from src.api.routers.privacy import router as privacy_router
from src.api.routers.sessions import router as sessions_router
from src.api.routers.trajectory import router as trajectory_router
from src.api.routers.vacancies import router as vacancies_router
from src.api.routers.websocket import router as websocket_router
from src.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend y motor de evaluación de candidatos asistido por IA",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configuración de CORS para permitir peticiones desde el frontend Next.js (Cristian)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(vacancies_router)
app.include_router(invitations_router)
app.include_router(sessions_router)
app.include_router(websocket_router)
app.include_router(trajectory_router)
app.include_router(evaluation_router)
app.include_router(privacy_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Endpoint de comprobación de salud del servicio"""
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Bienvenido a {settings.PROJECT_NAME} API",
        "docs": "/docs",
        "health": "/health",
    }
