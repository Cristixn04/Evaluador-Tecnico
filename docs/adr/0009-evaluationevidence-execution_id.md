# ADR 0009: Campo execution_id en EvaluationEvidence

## Estado
Aceptado (pendiente de documentación complementaria).

## Contexto
El modelo `EvaluationEvidence` incluye un campo `execution_id: uuid.UUID | None` con FK a `snapshots.id`. No existe una entidad persistente `Execution` independiente en el códigobase. El servicio de evaluación y los tests no asignan valor alguno a este campo en la práctica actual.

## Decisión

### `execution_id` — Referencia a Snapshot (DR-11)
- El campo `EvaluationEvidence.execution_id` referencia la tabla `snapshots.id` mediante FK con `ON DELETE SET NULL`.
- No existe entidad `Execution` ni tabla `executions` persistente en el repositorio actual.
- El valor nunca se asigna en el código de producción (`src/evaluation/service.py`, tests, ni handlers de API). El campo es **opcional y sin usar** en la implementación actual.
- El diseño actual considera que `Snapshot` captura suficiente información sobre la ejecución de código (véase `Snapshot.execution_status`, `Snapshot.tests_passed`, `Snapshot.total_tests`) como para no requerir una entidad `Execution` separada.

### Evidencia confirmada
- **Modelo** (`apps/api/src/db/models/interview.py:346`): `execution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("snapshots.id", ondelete="SET NULL"), nullable=True)`
- **Migración** (`apps/api/alembic/versions/adding_evaluation_tables.py:58`): `sa.Column("execution_id", sa.Uuid(), nullable=True)` — FK implícita en modelo, no declarada de forma explícita en el DDL de Alembic.
- **Falta de uso**: Búsqueda exhaustiva en `src/`, `tests/` y migraciones demuestra que `execution_id` nunca se pobla con un UUID real de `Snapshot.id`. Los tests usan datos mock y el servicio evalúa basándose en `competencies` y `evidence` de turns/snapshots.
- **Sin entidad Execution**: Búsqueda `grep -rn "execution_id" apps/api/src/ apps/api/tests/` retorna solo la definición de modelo y la migración; no hay servicio, router ni código de dominio que escriba este campo.

### Condiciones para reconsideración
- Si se introduce una entidad `Execution` persistente con su propia tabla y servicio, `execution_id` debería referenciar `executions.id` en su lugar.
- Si los tests o el servicio comienzan a poblar `execution_id` con UUIDs reales de `Snapshot.id`, la FK y la semántica deben validarse contra el esquema de datos resultante.
- Si surge un requisito nuevo para rastrear ejecuciones de código independientes de snapshots, se crearía tabla `executions` y `execution_id` pasaría a referenciarla.

### Consecuencias
- **Actual**: Campo inactivo, sin riesgo de datos corruptos. Documentar como "diseño por decisión futura" para evitar que se elimine por accidente.
- **Futuro**: Si se poblara el campo, la FK a `snapshots.id` garantiza integridad referencial sobre snapshots existentes; un cambio a `executions.id` requeriría migración y posible pérdida de datos si snapshots referenciados fuesen borrados.
- **Riesgo bajo**: Dado que nadie usa el campo, no hay riesgo operativo. El único riesgo es eliminación accidental de la columna o confusión por futuros desarrolladores.

## Historial

| Revisión | Fecha | Comentario |
|---|---|---|
| 0009 | 2026-10-14 | Documentación inicial para cierre S-11 |