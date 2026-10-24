# ADR 0010: Rollback de migraciones Alembic y comportamiento de merge

## Estado
Pendiente de validación runtime.

## Contexto
La migración `merge_evaluation_invitations` une dos ramas divergentes que nacen de `a5fe8eec0469`:
- Rama A: `adding_evaluation_tables` — crea tablas `evaluations`, `evaluation_dimensions`, `evaluation_evidence`
- Rama B: `9e72f0a31071` — modifica `invitations.interview_id` (drop unique constraint + create unique index)

## Decisión

### Comportamiento de `merge_evaluation_invitations` (DR-12)
- `upgrade()`: vacío — ambas DDL ya estaban aplicadas, solo marca la versión como resuelta.
- `downgrade()`: vacío — **no revierte** las DDL de las ramas hijas. Solo restaura la fila de `alembic_version` al estado anterior al merge.

### Diferencia entre revisión de merge y downgrade de esquema
| Operación | Efecto en DDL | Efecto en `alembic_version` |
|---|---|---|
| `alembic downgrade merge_evaluation_invitations` | **No revierte** ninguna DDL de las ramas | Vuelve al estado pre-merge (fila removida o anterior) |
| `alembic downgrade adding_evaluation_tables` | Revierte DDL de la Rama A (drop tables evaluations/...) | Vuelve a `a5fe8eec0469` |
| `alembic downgrade 9e72f0a31071` | Revierte DDL de la Rama B (recreate unique index en invitations) | Vuelve a `a5fe8eec0469` |

### Validación pendiente (NEEDS_RUNTIME_VALIDATION)
- **No se han ejecutado** `alembic downgrade` sobre una base de datos compartida con datos reales.
- **Comportamiento estático** (leer el grafo y el código) confirma que `downgrade()` vacío no revierte DDL, pero **no garantiza** que los datos existentes permanezcan consistentes ni que `alembic_version` quúe en un estado significante sin pruebas adicionales.
- **Procedimiento propuesto** (probar en base temporal aislada):
  1. `alembic heads` → verificar current tip es `merge_evaluation_invitations`
  2. `alembic downgrade merge_evaluation_invitations` → verificar que DDL de ambas ramas persista (tables existen, index único en invitations)
  3. `alembic downgrade adding_evaluation_tables` → verificar que tables evaluations/... hayan sido droppeadas
  4. `alembic downgrade 9e72f0a31071` → verificar que unique index en invitations haya sido removido/restituido
  5. `alembic heads` → verificar estado actual después de cada operación

### Consecuencias
- **Actual**: Los desarrolladores que esperen que `downgrade merge` revierta automáticamente todas las DDL estarán equivocados. El comportamiento correcto es downgrade manual por rama.
- **Futuro**: Si se necesita un rollback completo a un estado anterior a S-11, se requerirían dos `alembic downgrade` separados (uno por rama) en el orden correcto, o un script de migración personalizado.
- **Riesgo medio**: Confundir el merge downgrade con downgrade de rama individual podría llevar a pérdida inesperada de esquema o datos en entornos donde las migraciones se aplicaron progresivamente.

### Historial

| Revisión | Fecha | Comentario |
|---|---|---|
| 0010 | 2026-10-14 | Documentación inicial para cierre S-11 |