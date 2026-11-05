# H-01 — Reporte de Remediación de Contrato WebSocket y Ejecución Aislada (Fase 3)

**Estado:** **`CERRADO Y VERIFICADO (PASS)`**  

---

## 1. Diagnóstico de Causa Raíz (H-01)

Durante la Fase 2 de auditoría forense se identificó el hallazgo P0 **H-01**:
1. Cuando Judge0 CE (`http://localhost:2358`) no estaba disponible en tiempo de ejecución, [`CodeExecutionService.execute_code()`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/execution/service.py) devolvía:
   ```python
   {
       "status": "unavailable",
       "stdout": None,
       "stderr": "Judge0 CE sandbox is currently unavailable...",
       "execution_time_ms": 0,
       "tests_passed": None,
       "total_tests": len(problem_spec.tests),
       "test_details": [],
   }
   ```
2. Sin embargo, [`ServerCodeExecutionResultMessage`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/schemas/websocket.py) definía:
   - `ExecutionStatus` sin el literal `"unavailable"`.
   - `stdout: str`, `stderr: str` y `tests_passed: int` como campos no nulos obligatorios.
3. Al construir `ServerCodeExecutionResultMessage(**result)` dentro de `_handle_code_execution` en el router WebSocket (`apps/api/src/api/routers/websocket.py`), Pydantic lanzaba un `ValidationError` no controlado en lugar de emitir el mensaje estructurado `code_execution_result` con `status="unavailable"`.

---

## 2. Cambios Implementados

### 2.1. Esquema WebSocket Backend ([`apps/api/src/api/schemas/websocket.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/api/schemas/websocket.py))
- Se añadió `"unavailable"` al tipo `ExecutionStatus`:
  ```python
  ExecutionStatus = Literal[
      "success",
      "test_failure",
      "compile_error",
      "timeout",
      "runtime_error",
      "unavailable",
  ]
  ```
- Se actualizaron los campos de `ServerCodeExecutionResultMessage` para reflejar honestamente la ausencia de ejecución cuando el sandbox no está disponible:
  - `stdout: str | None = None`
  - `stderr: str | None = None`
  - `tests_passed: int | None = Field(default=None, ge=0)`

### 2.2. Servicio de Ejecución de Código ([`apps/api/src/execution/service.py`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/execution/service.py))
- Se centralizó el registro de indisponibilidad en `_record_unavailable(...)`, persistiendo el `Snapshot` con `execution_status="unavailable"` y `tests_passed=None`.
- Además de verificar `check_availability()` antes del bucle de tests, se capturan explícitamente `SandboxUnavailableError`, `SandboxProviderError`, `SandboxTimeoutError` y `SandboxInvalidResponseError` durante `self._runner.run(request)` por si Judge0 cae a mitad de la batería de pruebas.
- Se incluyó `compile_output` en `combined_stderr` cuando `stderr` está vacío pero el compilador/intérprete devolvió `compile_output`.

### 2.3. Frontend Sala de Entrevista (`apps/web`, sin tocar `packages/contracts/`)
- En [`apps/web/src/lib/hooks/use-interview-socket.ts`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/web/src/lib/hooks/use-interview-socket.ts):
  - Se añadió `'unavailable'` a `CodeExecutionStatus`.
  - Se permitió `stdout: string | null`, `stderr: string | null` y `tests_passed: number | null`.
- En [`apps/web/src/components/interview/test-console.tsx`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/web/src/components/interview/test-console.tsx):
  - Se añadió el badge ámbar `Sandbox no disponible` (`status === 'unavailable'`).
  - Cuando `tests_passed === null`, se muestra `Sin ejecutar (N tests)` en lugar de mostrar falsamente `0/N tests pasados`.

---

## 3. Decisión Arquitectónica sobre Aislamiento de Ejecución

Siguiendo estrictamente la directiva de seguridad de la Fase 3.3:
- **NO** se implementó un runner local con `subprocess` ni `resource.setrlimit` sobre el host, ya que no proporciona aislamiento de sistema de archivos, red ni contenedores para código arbitrario no confiable.
- El único motor de ejecución de código sigue siendo **Judge0 CE** (`Judge0CodeRunner` en `apps/api/src/sandbox/judge0.py`) con límites de CPU, memoria y procesos (`MAX_PROCESSES_AND_OR_THREADS=10`).
- Cuando Judge0 CE no está levantado en el entorno anfitrión, tanto el canal WebSocket como la herramienta `code_execution_sandbox` del agente devuelven `status="unavailable"` de forma transparente y sin romper la sesión.

---

## 4. Verificación y Pruebas Ejecutadas

- `tests/test_execution.py::TestCodeExecutionService::test_h01_sandbox_unavailable_returns_unavailable_contract` — **`PASSED`**
- `tests/test_execution.py::TestCodeExecutionService::test_h01_sandbox_exception_during_run_returns_unavailable` — **`PASSED`**
- `tests/test_websocket.py::TestWebSocketMessages::test_h01_code_execution_unavailable_over_websocket_does_not_crash` — **`PASSED`**
- Escenario real S2 `exec_07_failure_sandbox_unavailable` contra Grok (`grok-4.6`) — **`PASSED`** (`status="unavailable"`, el agente informa honestamente al candidato sin inventar resultados de pruebas).
