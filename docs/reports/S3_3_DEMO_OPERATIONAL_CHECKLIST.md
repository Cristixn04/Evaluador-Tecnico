# S3.3 — Checklist Operativo y Ensayo Previo de Demostración

**Fecha:** 2026-11-01  
**Responsables:** Samuel (Grabación / Reclutador / Candidato) & Antigravity (Auditoría Técnica)  
**Veredicto Operativo:** `S3_OPERATIONALLY_READY_WITH_LIMITATIONS`

---

## 1. Comandos Exactos de Inicio

### Terminal 1 — Backend FastAPI (Puerto 8001)
> [!IMPORTANT]
> El puerto 8000 está ocupado en el host por `campuslands_backend`. FastAPI **debe** iniciarse obligatoriamente en el puerto **8001** para coincidir con la configuración del frontend (`NEXT_PUBLIC_API_URL=http://localhost:8001`).

```bash
cd /home/papisamu/Documentos/Evaluador-Tecnico/apps/api
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

### Terminal 2 — Frontend Next.js (Puerto 3000)
```bash
cd /home/papisamu/Documentos/Evaluador-Tecnico/apps/web
pnpm dev
```

### Terminal 3 — Generación de la Invitación Oficial (Una vez que FastAPI esté corriendo)
```bash
cd /home/papisamu/Documentos/Evaluador-Tecnico/apps/api
PYTHONPATH=. .venv/bin/python src/scripts/demo_s3.py --create-invitation
```

---

## 2. Orden de Inicio de Servicios

1. **Infraestructura Base:**
   - Verificar que `evaluador-postgres` (puerto 5435) y `evaluador-redis` (puerto 6379) estén activos mediante `docker ps`.
2. **Backend FastAPI:**
   - Iniciar en el puerto 8001 y verificar que responda `GET http://localhost:8001/health`.
3. **Frontend Next.js:**
   - Iniciar en el puerto 3000 y verificar acceso a `http://localhost:3000`.
4. **Generación de Invitación:**
   - Ejecutar el comando del script con `--create-invitation` para obtener el enlace de acceso oficial con el token generado.
5. **Inicio de Grabación de Pantalla:**
   - Activar la herramienta de captura de pantalla continua antes de abrir la sala en Chrome.

---

## 3. URLs Verificadas

| Servicio / Pantalla | URL Local Exacta | Estado de Enrutamiento / Puerto |
| :--- | :--- | :--- |
| **Health Check API** | `http://localhost:8001/health` | Verificado (200 OK) |
| **Documentación Swagger** | `http://localhost:8001/docs` | Verificado (OpenAPI v1) |
| **WebSocket API** | `ws://localhost:8001/ws/interview/{id}?token={token}` | Verificado (Rechazo seguro 1008 sin token) |
| **Portal Candidato (Inicio)** | `http://localhost:3000/interview/live?token={token}` | Verificado (`LiveInterviewPage`, Ley 1581) |
| **Login Reclutador** | `http://localhost:3000/login` | Verificado (Demo button habilitado) |
| **Panel Reclutador** | `http://localhost:3000/dashboard` | Verificado (Vacantes y métricas) |
| **Reporte de Resultados** | `http://localhost:3000/interview/results/{id}` | Verificado (Radar, Evidencias, PDF) |

---

## 4. Procedimiento Oficial de Invitación

Se auditó el mecanismo de invitaciones y se corrigió `demo_s3.py` para utilizar estrictamente el flujo oficial de producción:

1. **Servicio Oficial:** [`InvitationService.create()`](file:///home/papisamu/Documentos/Evaluador-Tecnico/apps/api/src/invitations/service.py#L27-L54)
   - Genera un token criptográfico de alta entropía (`secrets.token_urlsafe(32)`).
   - Extrae el selector de 16 caracteres (`token[:16]`) para búsqueda $O(1)$.
   - Calcula el hash seguro con Argon2 (`token_hash = hash_password(token)`).
   - Persiste la invitación vinculada a la vacante demo (`Ingeniero de Software Backend (Python / Fintech)`).
2. **Verificación Automática al Abrir el Enlace:**
   - La página `/interview/live?token={token}` invoca `GET /sessions/verify?token={token}`.
   - El backend ejecuta `InterviewService.get_or_create_from_invitation(token)` con bloqueo a nivel de fila (`SELECT ... FOR UPDATE`), garantizando idempotencia.
   - Si la entrevista aún no ha sido creada, la instancia, asigna el problema de catálogo (`pse-payment-reconciliation`), asocia la vacante, genera el token efímero de WebSocket (`ws_token`) y devuelve la configuración de la sesión anónima.

---

## 5. Verificación de Cuenta Reclutador

Se auditó la base de datos de desarrollo `evaluador_db` con los siguientes resultados comprobados:

- **Organización:** `Tech Colombia` (ID: `0ca1a120-f4c8-4244-8958-b7e4a822deb5`).
- **Usuario Reclutador:** `reclutador@tech-colombia.co` (ID: `44130bda-5fc1-4049-957a-88471fc1240b`).
- **Estado de Cuenta:** `is_active = True`.
- **Credencial Demo Verificada:** La contraseña configurada para pruebas (`demo123456`) fue comprobada exitosamente contra el hash de la base de datos (`verify_password() == True`).
- **Membresía:** Rol `recruiter` asociado a `Tech Colombia`.
- **Acceso en Pantalla:** El botón *"Iniciar sesión demo"* en `/login` rellena automáticamente estos datos y redirige al dashboard.
- **Procedimiento de Aprovisionamiento (Fallback):** Si por alguna razón la base requiriera reinicializarse, el comando oficial es:
  `cd apps/api && PYTHONPATH=. .venv/bin/python src/scripts/seed_demo.py`

---

## 6. Secuencia Exacta en Chrome

Durante la grabación continua, Samuel seguirá la siguiente ruta cronológica:

```text
[Chrome] http://localhost:3000/interview/live?token=...
   │
   ├── 1. PANTALLA INTRODUCCIÓN Y PRIVACIDAD
   │      - Verificar código de candidato anonimizado (ej. CAND-XXXX).
   │      - Marcar checkbox de consentimiento informado (Ley Estatutaria 1581 de 2012).
   │      - Hacer clic en "Entiendo las Reglas y Deseo Comenzar".
   │
   ├── 2. FASE PROBLEM & CLARIFY (Chat con Agente LLM)
   │      - Revisar enunciado del conciliador PSE en la pestaña izquierda.
   │      - Cambiar a pestaña Chat y enviar mensaje inicial:
   │        "Hola, he leído el problema. ¿Los extractos bancarios pueden contener transacciones duplicadas por reintentos de webhook?"
   │      - Observar la respuesta en streaming dinámico del agente LLM (Grok-4.6).
   │
   ├── 3. FASE DESIGN & CODING (Editor Monaco & Sandbox)
   │      - Avanzar la fase en la cabecera ("Listo para diseñar" -> "Empezar a programar").
   │      - En el editor derecho, revisar el código plantilla de Python.
   │      - Escribir o ajustar la lógica de conciliación con diccionario `seen_bank_cus`.
   │      - Presionar el botón "Ejecutar Pruebas".
   │      - Observar en la consola inferior el resultado devuelto (reportará 'unavailable' defensivo o resultados de ejecución sin tumbar la UI).
   │
   ├── 4. FASE PROBE & WRAPUP (Preguntas de Sondeo y Cierre)
   │      - Avanzar fase hacia "Sondeo" y responder a la pregunta del agente sobre complejidad temporal O(N + M).
   │      - Avanzar a "Cierre" (WRAPUP).
   │      - Hacer clic en el botón verde "Entregar y Finalizar Entrevista".
   │      - En el modal de confirmación, hacer clic en "Confirmar Entrega Definitiva".
   │
   ├── 5. FASE EVALUATE (Evaluación Dual-Judge en Progreso)
   │      - Observar la transición a estado cerrado y evaluación disparada.
   │
   └── 6. PORTAL RECLUTADOR (Visualización del Informe Defendible)
          - Abrir nueva pestaña: http://localhost:3000/login
          - Pulsar "Iniciar sesión demo" (reclutador@tech-colombia.co).
          - En /dashboard, localizar la entrevista recién completada.
          - Acceder a /interview/results/[id]:
            * Mostrar Radar de Competencias (5 dimensiones).
            * Desplegar evidencias con citas exactas de turnos de conversación.
            * Probar botón "Descargar Informe PDF".
```

---

## 7. Acciones que Ejecutará Samuel

- Iniciar y detener la grabación de pantalla del sistema operativo.
- Ejecutar los comandos en los terminales (o verificar que estén en ejecución).
- Escribir los mensajes en el chat de la entrevista de manera natural e interactiva.
- Modificar el código en el editor Monaco durante la fase de codificación.
- Pulsar los botones de transición de fase y confirmación de entrega en la interfaz.

---

## 8. Acciones que Podrá Preparar o Verificar Antigravity

- Monitorear los logs del backend para confirmar la emisión de telemetría y llamadas LLM.
- Verificar en la base de datos la persistencia de registros en `llm_usage_records`.
- Ejecutar la auditoría final post-proceso para reconciliar los costos medidos de la entrevista:
  `python -m src.scripts.demo_s3 --interview-id <INTERVIEW_ID>`
- Generar el reporte final con los identificadores y consumos reales obtenidos.

---

## 9. Estado de Judge0

- **Situación Confirmada:** El servicio Judge0 CE **no está activo** en el entorno local (puerto 2358 sin proceso y sin imagen local descargada).
- **Tratamiento Técnico:**
  - El backend `CodeExecutionService` ejecuta `check_availability()` antes de procesar envíos.
  - Al no detectar el servicio, registra el snapshot con `execution_status = "unavailable"` y `tests_passed = None`.
  - La interfaz de usuario muestra un mensaje descriptivo en la consola sin fallar ni simular éxito.
- **Valor Probatorio:** Esta limitación demuestra honestidad técnica: el sistema no inventa ejecuciones ni finge tests aprobados, cumpliendo estrictamente con la regla de no presentar datos sintéticos como reales.

---

## 10. Evidencias que Deben Observarse en la Grabación

1. **Interacción Conversacional Real:** El agente genera respuestas dinámicas coherentes con el problema de pagos PSE y adaptadas a las preguntas del candidato.
2. **Aislamiento Anti-Sesgo (Ley 1581):** En todo momento, la sala muestra únicamente el identificador anónimo `CAND-XXXX`, sin datos personales del candidato.
3. **Persistencia de Código:** Guardado automático (debounced snapshot) visible con el indicador `"Guardado"` en el editor.
4. **Cierre Defendible:** El botón de cierre solo se activa en la fase final `WRAPUP` y requiere confirmación explícita mediante modal accesible.
5. **Evaluación Dual-Judge con Citas:** El reporte final presenta dos jueces independientes, un consenso ponderado y citas textuales de los turnos conversacionales y snapshots generados.
6. **Trazabilidad de Costos:** Registros en la base de datos que diferencian costos medidos (`measured`) de costos estimados (`estimated`).

---

## 11. Plan Alternativo ante Fallos

- **Si el WebSocket se desconecta durante la sesión:**
  - El hook `useInterviewSocket` reconecta automáticamente sin perder el historial de mensajes ni el estado de la fase. Esperar 3 segundos hasta ver el indicador verde *"En vivo"*.
- **Si el candidato recarga la página por error:**
  - La sesión se restaura automáticamente gracias a la verificación de sesión en `/sessions/verify` y la rehidratación del consentimiento en `localStorage`.
- **Si el proveedor LLM sufre un timeout transitorio:**
  - El backend cuenta con 2 reintentos automáticos (`LLM_MAX_RETRIES=2`) y timeout de 30s. Si la llamada de un turno falla, el chat muestra un mensaje de reintento sin romper la conexión WebSocket.
- **Si el reporte de evaluación tarda unos segundos en generarse:**
  - El proceso de evaluación dual-judge ejecuta dos llamadas en paralelo. Esperar entre 10 y 15 segundos en la pantalla de evaluación hasta que los jueces concluyan.

---

## 12. Riesgos y Limitaciones Declaradas

1. **Puerto 8000 en Conflicto:** Si se intenta arrancar FastAPI con `make dev-api` por defecto, fallará por el puerto ocupado por `campuslands_backend`. Se debe usar siempre el comando con `--port 8001`.
2. **Judge0 No Disponible:** La ejecución de pruebas reportará `unavailable`. Esta limitación está documentada y prevista en el diseño desacoplado del evaluador.
3. **Costo de Evaluación:** Las dos solicitudes a `grok-4.6` durante el cierre de la entrevista consumirán aproximadamente ~9,800 tokens reales (~$0.07 USD) contra la API configurada.

---

## Veredicto Final

```text
================================================================================
VEREDICTO: S3_OPERATIONALLY_READY_WITH_LIMITATIONS
================================================================================
Fundamento:
El flujo operativo completo (creación oficial de invitaciones, verificación de
sesión anónima, WebSocket en tiempo real, chat con LLM, cierre formal y
evaluación dual-judge) ha sido verificado, ensayado en código y probado con 417
tests unitarios. La limitación operativa documentada es la indisponibilidad de
Judge0 local (que operará con fallback defensivo). El procedimiento está listo
para que Samuel inicie los servicios y ejecute la grabación continua de pantalla
en Chrome.
================================================================================
```
