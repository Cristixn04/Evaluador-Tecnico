# Guía Técnica: Creación y Autoría de Problemas YAML

Esta guía describe el estándar y las reglas técnicas para crear, estructurar y validar nuevos problemas técnicos en el catálogo del **Evaluador Técnico**.

El catálogo se encuentra centralizado en el directorio raíz:

```text
problems/
```

Cada problema está representado por un único archivo YAML cuyo nombre debe coincidir exactamente con el identificador del problema: `<id>.yaml`.

---

## 1. Reglas y Restricciones Estrictas

La validación del catálogo se realiza de forma estricta mediante Pydantic v2 en `apps/api/src/problems/schemas.py` y el cargador en `apps/api/src/problems/loader.py`:

1. **Correspondencia archivo-id:** El nombre base del archivo (`stem`) DEBE ser idéntico al campo `id` declarado en el YAML.
   * *Ejemplo:* Si `id: idempotent-webhook`, el archivo DEBE llamarse `problems/idempotent-webhook.yaml`.
2. **Formato del `id`:** Debe estar en minúsculas y formato kebab-case (`^[a-z0-9]+(?:-[a-z0-9]+)*$`), entre 1 y 80 caracteres.
3. **Unicidad de tests:** Cada caso de prueba en la lista `tests` debe tener un `id` único dentro del problema.
4. **Coherencia de boilerplate:** Toda clave definida en `boilerplate` debe corresponder a un lenguaje listado en `languages`.
5. **Generación determinista de UUID:** El sistema calcula el identificador persistente en base de datos mediante UUIDv5 con el namespace estático:
   ```python
   PROBLEM_ID_NAMESPACE = uuid.UUID("a3f1c8e2-7b54-4d91-9e06-2c5b8f4a1d73")
   persistence_id = uuid.uuid5(PROBLEM_ID_NAMESPACE, problem_id)
   ```

---

## 2. Estructura y Especificación del Schema

### 2.1 Campos Obligatorios

| Campo | Tipo | Restricción / Valores Permitidos | Descripción |
| :--- | :--- | :--- | :--- |
| `id` | `string` | Regex `^[a-z0-9]+(?:-[a-z0-9]+)*$` (1-80 chars) | Identificador canónico kebab-case. |
| `title` | `string` | No vacío, máx. 255 caracteres | Título visible del ejercicio técnico. |
| `role` | `enum` | `backend`, `frontend`, `fullstack`, `data`, `devops` | Familia de rol para coincidencia de vacantes. |
| `seniority` | `enum` | `junior`, `mid`, `senior`, `lead` | Nivel de experiencia objetivo. |
| `difficulty` | `enum` | `junior`, `mid`, `senior` | Dificultad técnica del problema. |
| `tags` | `list[string]` | Mínimo 1 elemento, no vacíos | Etiquetas normalizadas (ej. `python`, `redis`, `api`). |
| `languages` | `list[string]` | `python`, `javascript`, `sql` (mínimo 1) | Lenguajes de programación soportados. |
| `statement` | `string` | Markdown no vacío | Enunciado completo, restricciones y ejemplos I/O. |
| `tests` | `list[TestCase]` | Mínimo 1 caso de prueba | Casos de prueba deterministas de entrada/salida. |

### 2.2 Campos Opcionales con Valores por Defecto

| Campo | Tipo | Default | Descripción |
| :--- | :--- | :--- | :--- |
| `limits.timeout_ms` | `int` | `2000` (1 a 30000 ms) | Tiempo máximo de ejecución en sandbox. |
| `limits.memory_mb` | `int` | `128` (1 a 512 MB) | Límite estricto de memoria RAM en sandbox. |
| `boilerplate` | `map[string, string]` | `{}` | Plantilla de código inicial por lenguaje. |

### 2.3 Estructura de un `TestCase`

Cada caso de prueba bajo la lista `tests` contiene:

- `id` (*string, obligatorio*): Identificador kebab-case (ej. `basic-flow`, `empty-input`).
- `input` (*string, obligatorio*): Datos enviados vía `stdin` al sandbox.
- `expected_output` (*string, obligatorio*): Salida exacta esperada en `stdout`.
- `timeout_ms` (*int, opcional, default: 2000*): Tiempo límite específico del test.
- `memory_mb` (*int, opcional, default: 128*): Memoria máxima específica del test.

---

## 3. Plantilla Canónica Completa

A continuación se muestra un ejemplo válido y funcional:

```yaml
id: rate-limiter-redis
title: Limitador de Tasa con Redis y Ventana Deslizante
role: backend
seniority: mid
difficulty: mid
tags:
  - python
  - redis
  - concurrency
  - rate-limiting
languages:
  - python
limits:
  timeout_ms: 2000
  memory_mb: 128
statement: |
  Implementa una función que determine si una solicitud HTTP debe ser
  admitida o rechazada bajo una política de ventana deslizante (sliding window).

  ### Entrada
  Un objeto JSON leído desde `stdin` con el siguiente formato:
  ```json
  {
    "capacity": 5,
    "window_seconds": 60,
    "timestamps": [10, 20, 30, 75]
  }
  ```

  ### Salida
  Un objeto JSON con el conteo de solicitudes aceptadas y rechazadas:
  ```json
  {"accepted": 4, "rejected": 0}
  ```
tests:
  - id: all-accepted
    input: '{"capacity": 3, "window_seconds": 10, "timestamps": [1, 2, 3]}'
    expected_output: '{"accepted":3,"rejected":0}'
  - id: exceeded-capacity
    input: '{"capacity": 2, "window_seconds": 10, "timestamps": [1, 2, 5, 8]}'
    expected_output: '{"accepted":2,"rejected":2}'
boilerplate:
  python: |
    import json
    import sys

    def evaluate_requests(payload: dict) -> dict:
        # TODO: Implementar lógica de ventana deslizante
        raise NotImplementedError

    if __name__ == "__main__":
        data = json.load(sys.stdin)
        result = evaluate_requests(data)
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
```

---

## 4. Procedimiento para Agregar y Validar un Problema

1. **Crear el archivo YAML:**
   ```bash
   touch problems/mi-nuevo-problema.yaml
   ```
2. **Escribir el contenido** asegurando que `id: mi-nuevo-problema`.
3. **Ejecutar la suite de pruebas del catálogo:**
   ```bash
   cd apps/api
   .venv/bin/pytest -v tests/test_problem_catalog.py tests/test_problem_selector.py
   ```
4. **Verificar que el validador Pydantic no arroje errores:**
   El test `test_problem_catalog.py` carga automáticamente todos los archivos en `problems/` y valida tipos, límites, unicidad de IDs y consistencia del boilerplate.

---

## 5. Errores Frecuentes y Cómo Solucionarlos

- **`ProblemCatalogInvalidError: Problem file stem must match id`:**
  El nombre del archivo no coincide con el campo `id`. Si el archivo es `problems/foo.yaml`, el id debe ser `foo`.
- **`duplicate test id: ...`:**
  Dos o más casos de prueba dentro del mismo archivo comparten el mismo `id`.
- **`boilerplate language 'xyz' is not in languages`:**
  Se incluyó código inicial en `boilerplate` para un lenguaje que no fue declarado en la lista `languages`.
- **`limits.memory_mb must be <= 512`:**
  Por seguridad contra agotamiento de recursos en el sandbox, ningún problema puede solicitar más de 512 MB de memoria RAM.
