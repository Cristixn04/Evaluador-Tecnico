# ADR 0003: Selección de Problemas Relacional Determinista vs pgvector Temprano

## Estado
Aceptado

## Contexto
El agente necesita seleccionar el problema técnico más pertinente a partir del perfil extraído de la vacante (tecnologías, nivel de seniority y tipo de rol). El plan preliminar sugería instalar la extensión `pgvector` en PostgreSQL y generar embeddings vectoriales para emparejar semánticamente el perfil con el banco de problemas.

## Decisión
Para el catálogo inicial de **12 a 30 problemas**, se descarta `pgvector` y se implementa una estrategia de **selección determinista basada en metadatos relacionales indexados**:
- Coincidencia exacta de `language` (Python, JavaScript/TypeScript, SQL).
- Rango de `seniority` (Junior, Mid, Senior).
- Intersección de `tags` y habilidades obligatorias (`required_skills`).

Si múltiples problemas satisfacen los criterios, se selecciona de forma aleatoria ponderada para evitar que dos candidatos para la misma vacante reciban siempre exactamente el mismo problema.

`pgvector` y búsqueda vectorial semántica se reservan para una fase posterior cuando el banco supere los 100 problemas heterogéneos.

## Justificación
1. **Evitar Sobreingeniería Prematura:** Configurar embeddings vectoriales para una colección de 12 problemas agrega complejidad operativa (dimensiones de vectores, índices HNSW/IVFFlat, costos de llamadas a APIs de embeddings) sin ninguna ventaja funcional perceptible.
2. **Determinismo y Auditabilidad:** Los reclutadores y líderes técnicos comprenden y auditan con mayor facilidad una regla clara (*"Este problema se asignó porque la vacante pide Python + Backend + Mid"*) que una distancia de coseno opaca.
3. **Agilidad en Sprints:** Permite a Samuel enfocar todo su esfuerzo del Sprint 2 en el motor de la entrevista y en la ejecución de código en sandbox, en lugar de lidiar con extensiones de bases de datos.
