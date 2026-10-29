# Guía Técnica: Configuración y Alternancia de Proveedores LLM

Esta guía explica la arquitectura del cliente LLM en el backend del **Evaluador Técnico**, cómo configurar variables de entorno para alternar entre diferentes proveedores y las garantías de seguridad y cálculo de costos.

---

## 1. Arquitectura del Cliente LLM

El backend implementa un patrón **Factory** desacoplado en `apps/api/src/llm/factory.py`:

```text
Configuración (.env / Settings)
              ↓
    create_llm_client()
      /              \
     / (mock=True)    \ (mock=False)
    ↓                  ↓
MockLLMClient     OpenAICompatibleClient (httpx async)
```

Dado que el cliente de producción implementa el protocolo estándar de OpenAI (`OpenAICompatibleClient`), cualquier proveedor con API compatible con `/chat/completions` puede ser integrado cambiando únicamente variables de entorno, sin alterar el código fuente.

---

## 2. Variables de Entorno del LLM

Las variables se configuran en `apps/api/.env` o en las variables del contenedor/VPS:

| Variable | Tipo | Default | Descripción |
| :--- | :--- | :--- | :--- |
| `LLM_API_KEY` | `string` | `mock-llm-key` | Token de autenticación hacia la API del proveedor. |
| `LLM_BASE_URL` | `string` | `https://api.reto.pltk.mx/v1` | URL base de la API (compatible con OpenAI). |
| `LLM_MODEL` | `string` | `grok-4.6` | Identificador del modelo para generación y evaluación. |
| `LLM_TIMEOUT_SECONDS` | `float` | `30.0` | Timeout máximo para peticiones HTTP al LLM. |
| `LLM_MAX_RETRIES` | `int` | `2` | Reintentos exponenciales ante errores de red o rate limiting. |
| `USE_MOCK_LLM` | `bool` | `false` | Activa respuestas locales deterministas sin costo. |
| `ENVIRONMENT` | `string` | `development` | Entorno (`development`, `staging`, `production`). |

---

## 3. Salvaguardas Estrictas de Producción

En `src/llm/factory.py` existen guardas obligatorias en tiempo de inicialización:

```python
if env in {"production", "prod"}:
    if current.USE_MOCK_LLM:
        raise LLMConfigurationError("Mock LLM client cannot be enabled in production environment")
    if not current.LLM_API_KEY or current.LLM_API_KEY == "mock-llm-key":
        raise LLMConfigurationError("Real LLM API key must be configured in production environment")
```

Si el entorno es `production` y se intenta arrancar con cliente simulado o clave por defecto, la aplicación **aborta el inicio de inmediato**, evitando evaluaciones inválidas en entornos reales.

---

## 4. Ejemplos de Configuración por Proveedor

> [!IMPORTANT]
> Nunca versione claves reales en Git. Utilice variables de entorno o gestores de secretos.

### 4.1 Reto PLTK Gateway (Configuración por Defecto - xAI Grok)

```env
ENVIRONMENT=production
LLM_BASE_URL=https://api.reto.pltk.mx/v1
LLM_MODEL=grok-4.6
LLM_API_KEY=<YOUR_RETO_API_KEY>
LLM_TIMEOUT_SECONDS=30.0
USE_MOCK_LLM=false
```

### 4.2 xAI Directo (Grok Oficial)

```env
ENVIRONMENT=production
LLM_BASE_URL=https://api.x.ai/v1
LLM_MODEL=grok-beta
LLM_API_KEY=<YOUR_XAI_API_KEY>
LLM_TIMEOUT_SECONDS=30.0
USE_MOCK_LLM=false
```

### 4.3 OpenAI Oficial

```env
ENVIRONMENT=production
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_API_KEY=<YOUR_OPENAI_API_KEY>
LLM_TIMEOUT_SECONDS=30.0
USE_MOCK_LLM=false
```

### 4.4 OpenAI Mini (Económico / Pruebas)

```env
ENVIRONMENT=production
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=<YOUR_OPENAI_API_KEY>
LLM_TIMEOUT_SECONDS=20.0
USE_MOCK_LLM=false
```

### 4.5 DeepSeek

```env
ENVIRONMENT=production
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=<YOUR_DEEPSEEK_API_KEY>
LLM_TIMEOUT_SECONDS=30.0
USE_MOCK_LLM=false
```

### 4.6 Desarrollo Local Offline (Sin Consumo de Créditos)

Para desarrollo frontend independiente, CI/CD rápido o pruebas unitarias:

```env
ENVIRONMENT=development
USE_MOCK_LLM=true
LLM_API_KEY=mock-llm-key
```

### 4.7 Modelos Locales vía Ollama / vLLM

```env
ENVIRONMENT=development
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1
LLM_API_KEY=ollama
USE_MOCK_LLM=false
```

---

## 5. Impacto en Auditoría de Costos (`src/evaluation/pricing.py`)

El sistema registra el consumo de tokens y calcula deterministamente el coste financiero por llamada y por entrevista (`[METRICS:INTERVIEW_COST]`).

Las tarifas soportadas de forma oficial (en USD por millón de tokens) son:

| Proveedor | Modelo | Tarifa Prompt ($/1M) | Tarifa Completion ($/1M) |
| :--- | :--- | :--- | :--- |
| **xAI** | `grok-4.6` / `grok-beta` | $5.00 | $15.00 |
| **xAI** | `grok-2` / `grok-2-vision` | $2.00 | $10.00 |
| **xAI** | `grok-2-mini` | $0.20 | $1.00 |
| **OpenAI** | `gpt-4o` | $2.50 | $10.00 |
| **OpenAI** | `gpt-4o-mini` | $0.15 | $0.60 |
| **OpenAI** | `gpt-4-turbo` | $10.00 | $30.00 |
| **OpenAI** | `gpt-3.5-turbo` | $0.50 | $1.50 |

> [!NOTE]
> Si se utiliza un modelo no registrado en la tabla de tarifas (por ejemplo, `deepseek-chat` o un modelo local de Ollama), el sistema continuará funcionando correctamente y registrará los tokens reales, pero el costo estimado se reportará explícitamente como `None` en la telemetría para **evitar fabricar datos contables no auditados**.

---

## 6. Verificación Local de Conectividad

Para validar que el proveedor configurado responde correctamente:

```bash
cd apps/api
.venv/bin/pytest -v tests/test_llm.py
```
