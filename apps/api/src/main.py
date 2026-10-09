from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.auth import router as auth_router
from src.api.routers.vacancies import router as vacancies_router
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
app.include_router(vacancies_router)


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
