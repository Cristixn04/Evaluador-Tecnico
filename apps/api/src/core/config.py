from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Evaluador Técnico de Candidatos"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Base de Datos PostgreSQL
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://evaluador:evaluador_password_dev@localhost:5432/evaluador_db",
        description="URL asíncrona de conexión a PostgreSQL",
    )

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="URL de conexión a Redis para sesiones y tareas",
    )

    # LLM Gateway (Grok / OpenAI compatible)
    LLM_API_KEY: str = Field(default="mock-llm-key", description="Clave API del proveedor LLM")
    LLM_BASE_URL: str = Field(
        default="https://api.reto.pltk.mx/v1",
        description="URL base del proveedor compatible con OpenAI",
    )
    LLM_MODEL: str = Field(default="grok-4.6", description="Modelo LLM a utilizar")
    LLM_TIMEOUT_SECONDS: float = Field(default=30.0, description="Timeout de llamadas al LLM")
    LLM_MAX_RETRIES: int = Field(
        default=2,
        description="Reintentos ante errores transitorios del LLM",
    )

    # Seguridad JWT
    JWT_SECRET_KEY: str = Field(
        default="dev-insecure-secret-key-change-in-prod-32bytes",
        description="Clave secreta JWT",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
