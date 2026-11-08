# INFORME TÉCNICO SEMANAL
## Proyecto Evaluador-Técnico
**Periodo:** 2 al 8 de noviembre de 2026  
**Área:** Backend, arquitectura, ejecución automatizada y validación de carga  
**Entregable principal:** Implementación, estabilización y ejecución oficial de la prueba S4.

---

## 1. Resumen ejecutivo

Durante la semana se trabajó en la estabilización técnica del backend del proyecto Evaluador-Técnico, con especial atención al sistema de ejecución automatizada de evaluaciones y a la preparación de la prueba oficial de carga S4.

El trabajo comprendió auditorías del código, revisión de persistencia y migraciones, correcciones en la integración con proveedores LLM y Judge0, optimización del consumo de tokens, control financiero, recuperación de tareas y mecanismos de ejecución desatendida.

El resultado principal fue completar la prueba oficial S4 utilizando el modelo Grok 4.6 mediante el gateway configurado y Judge0 para la validación de código. La ejecución alcanzó más de 12 horas de actividad LLM continua y superó las 1.000 tareas exitosas y validadas, manteniendo la exposición financiera por debajo del presupuesto autorizado.

## 2. Objetivos de trabajo

Los principales objetivos técnicos fueron:

1. Consolidar y auditar las funcionalidades implementadas en el backend.
2. Garantizar la persistencia de ejecuciones, tareas y registros de consumo LLM.
3. Estabilizar la comunicación con el proveedor LLM y el servicio Judge0.
4. Implementar mecanismos de recuperación ante errores y fallos transitorios.
5. Evitar reintentos que pudieran generar cargos duplicados o no identificados.
6. Controlar el presupuesto y las reservas financieras durante la ejecución.
7. Ejecutar una prueba desatendida de al menos 12 horas.
8. Completar y validar al menos 1.000 tareas.
9. Generar evidencia persistente y exportable de la ejecución.

## 3. Trabajo técnico realizado

### 3.1. Auditoría y estabilización del backend

Se realizaron revisiones técnicas de los componentes relacionados con la ejecución de evaluaciones, la integración LLM, la persistencia y el control de tareas.

Se prestó especial atención a:

- Consistencia entre estados de ejecución y estados de tareas.
- Integridad de los registros de consumo LLM.
- Manejo de excepciones y errores de comunicación.
- Recuperación de tareas interrumpidas.
- Prevención de ejecuciones duplicadas.
- Integridad de las migraciones de base de datos.
- Correspondencia entre las tareas ejecutadas y sus resultados de validación.

También se revisaron las pruebas automatizadas, el análisis estático y el tipado para reducir el riesgo de introducir regresiones durante las correcciones.

### 3.2. Persistencia y trazabilidad de ejecuciones

Se trabajó sobre la estructura de persistencia de S4, incluyendo:

- `S4LoadRun`: representación de una ejecución de carga.
- `S4TaskExecution`: registro individual de cada tarea.
- `LLMUsageRecord`: registro de consumo y trazabilidad de llamadas LLM.

Se mantuvieron restricciones de unicidad para evitar duplicaciones de tareas dentro de una misma ejecución, y se reforzó la relación entre tareas y registros de uso.

Se contemplaron estados de ejecución como:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

Asimismo, se reforzó la validación para impedir que una tarea se considere exitosa si no cuenta con validación satisfactoria y evidencia de consumo LLM confirmado cuando corresponde.

### 3.3. Integración con Grok y Judge0

Se estabilizó el flujo de ejecución que conecta el sistema con el proveedor LLM y el servicio Judge0.

**Proveedor LLM:**
- Modelo utilizado: `grok-4.6`.
- Gateway: `https://api.reto.pltk.mx/v1`.
- Timeout de lectura elevado a 90 segundos para adaptarse a los tiempos reales de respuesta.
- Separación entre errores de conexión y errores de lectura/escritura.
- Tratamiento conservador de timeouts cuya facturación no puede determinarse inmediatamente.
- Registro de tokens de entrada y salida, coste y referencias de las solicitudes.

**Judge0:**
- Servicio local: `http://localhost:2358`.
- Corrección del envío de código mediante codificación Base64.
- Separación de los errores de Judge0 respecto del ciclo de corrección LLM.
- Validación de los ejercicios ejecutables antes de registrar una tarea como exitosa.

Se corrigió además la clasificación de ejercicios ejecutables y no ejecutables para evitar llamadas innecesarias a Judge0 y prevenir que una tarea que requiere ejecución de código pudiera eludir su validación.

### 3.4. Optimización del consumo LLM

Se realizaron ajustes para reducir el coste por tarea y mejorar la estabilidad de la ejecución:

- Límite inicial de tokens de respuesta: 2.000.
- Límite para correcciones: 1.600.
- Simplificación de prompts y reducción de instrucciones redundantes.
- Prompts más concisos, generalmente de 60 a 110 palabras.
- Incorporación de palabras clave requeridas por el catálogo de ejercicios.
- Restricción de código generado a implementaciones autocontenidas y pequeñas cuando correspondía.
- Evitar generación de código en ejercicios que no requieren ejecución.

Estas modificaciones permitieron reducir el consumo innecesario y mejorar la relación entre coste y tareas completadas.

### 3.5. Control de concurrencia y recuperación

Se reforzaron los mecanismos de ejecución desatendida:

- Reserva de tareas mediante transacciones y bloqueos PostgreSQL.
- Uso de `FOR UPDATE` y `SKIP LOCKED` para controlar la asignación concurrente.
- Gestión de leases y heartbeats.
- Recuperación de tareas interrumpidas.
- Protección mediante advisory locks para evitar múltiples workers incompatibles.
- Rehidratación del estado del circuit breaker al reanudar la ejecución.
- Tratamiento diferenciado de fallos transitorios y fallos permanentes.

Se ajustó el pacer para que las tareas fallidas o con timeout no introdujeran pausas innecesarias. También se corrigió el momento de registro del despacho para mantener un control adecuado de los intervalos de actividad.

La reposición dinámica de tareas quedó condicionada tanto al tiempo de reloj como al tiempo efectivo de actividad LLM.

### 3.6. Control financiero y conciliación

Se reforzó el control del presupuesto para distinguir entre:

- Costes confirmados.
- Pasivos inciertos asociados a timeouts.
- Reservas activas.
- Exposición financiera total.

Esta separación permitió evitar que una llamada con resultado desconocido se contabilizara automáticamente como gratuita.

El presupuesto máximo autorizado para la corrida oficial fue de **35 USD**. La ejecución terminó por debajo de ese límite, sin reservas pendientes.

## 4. Incidencias encontradas y correcciones

Durante las primeras ejecuciones se identificaron problemas que impedían garantizar la continuidad y la eficiencia necesarias para la prueba oficial.

### 4.1. Timeouts del proveedor LLM

Se observaron respuestas del proveedor que tardaban aproximadamente entre 32 y 45 segundos, mientras que el cliente podía generar `ReadTimeout` antes de recibirlas.

**Corrección:** se ajustó el timeout de lectura a 90 segundos y se diferenciaron los errores recuperables de aquellos cuyo resultado financiero debía permanecer como incierto.

### 4.2. Circuit breaker bloqueando ejecuciones

La acumulación de errores de lectura provocaba que el circuit breaker alcanzara un estado de bloqueo permanente.

**Corrección:** se ajustó la transición temporal a estado de sondeo y se implementó la recuperación del estado del breaker al reanudar el worker.

### 4.3. Errores en la ejecución de Judge0

Se detectaron respuestas HTTP 400 relacionadas con el formato de envío del código.

**Corrección:** se normalizó el envío utilizando Base64 y se separó la gestión de errores de Judge0 de la lógica de corrección LLM.

### 4.4. Clasificación incorrecta de ejercicios

Algunos ejercicios podían entrar en rutas de ejecución que no correspondían a sus requisitos de validación.

**Corrección:** se alineó la clasificación del ejecutable con el validador del catálogo y se reforzaron las condiciones para considerar una tarea exitosa.

### 4.5. Interrupciones de la ventana continua

La primera ejecución no consiguió mantener los intervalos de actividad necesarios. Se identificaron pausas superiores al máximo permitido entre llamadas.

**Corrección:** se ajustó el pacer, se eliminó el retraso innecesario después de fallos y se incorporó un control de continuidad basado en ventanas de actividad confirmada.

### 4.6. Control de presupuesto

Durante el arranque inicial se detectó una configuración de presupuesto superior a la autorización establecida. Se corrigió antes de continuar con la ejecución controlada.

**Resultado:** la corrida se mantuvo bajo el límite autorizado de 35 USD.

## 5. Pruebas y validación técnica

Antes de reanudar la ejecución oficial se realizaron pruebas automatizadas y validaciones estáticas.

| Validación | Resultado reportado |
|---|---:|
| Suite de pruebas S4 | 154 pruebas aprobadas |
| Ruff | Sin errores |
| Mypy | 23 archivos verificados correctamente |
| Pruebas de regresión S4 | Aprobadas |
| Validación de ejecución y recuperación | Aprobada en las suites correspondientes |

Estas pruebas se realizaron sin necesidad de consumir llamadas LLM facturables adicionales para la validación offline.

Posteriormente se reanudó la misma ejecución oficial, conservando el historial de tareas, los éxitos previos y las obligaciones financieras inciertas.

## 6. Resultados de la ejecución oficial S4

**Identificador de ejecución:**

`02444adc-4c30-4d2e-9887-71df2e1a17e8`

**Estado final:** `completed`

### 6.1. Duración y continuidad

| Indicador | Resultado |
|---|---:|
| Actividad LLM efectiva | 43.215,74 segundos |
| Duración efectiva | 12 h 00 min 15,74 s |
| Llamadas confirmadas en la ventana continua | 1.260 |
| Mayor intervalo entre llamadas | 119,66 segundos |
| Ventana continua válida | Sí |

La ventana efectiva comenzó el 7 de noviembre a las 10:47:56 (hora de Colombia) y terminó el mismo día a las 22:48:12.

Se cumplió el requisito de mantener al menos 12 horas de actividad LLM continua, utilizando intervalos máximos inferiores a 120 segundos.

### 6.2. Tareas procesadas

| Indicador | Resultado |
|---|---:|
| Tareas registradas | 1.358 |
| Tareas exitosas y validadas | 1.315 |
| Tareas fallidas | 43 |
| Tareas exitosas sin validar | 0 |
| Tasa global de éxito | 96,83 % |

Durante la fase V3 de recuperación y estabilización se obtuvieron:

- 1.238 tareas exitosas.
- 1.243 tareas procesadas.
- Tasa de éxito del 99,60 %.

Esto representa una mejora importante frente a las primeras fases, que estuvieron afectadas por timeouts, errores de validación y problemas de comunicación.

### 6.3. Consumo y trazabilidad LLM

| Indicador | Resultado |
|---|---:|
| Registros de llamadas LLM | 1.392 |
| Llamadas confirmadas y medidas | 1.357 |
| Timeouts con coste incierto | 30 |
| Fallos HTTP sin cargo confirmado | 5 |
| Tokens de entrada | 1.655.339 |
| Tokens de salida | 534.049 |

Las llamadas confirmadas registraron tokens positivos y estado de medición `measured`.

Se conservaron referencias de trazabilidad como:

- `gateway_request_id`
- `response_body_id`
- `provider_request_id`
- `cf_ray`

Los 30 timeouts históricos se mantuvieron como pasivos inciertos, evitando asumir que no generaron costes.

### 6.4. Resultado financiero

| Concepto | Importe |
|---|---:|
| Presupuesto autorizado | $35,00 USD |
| Coste confirmado | $16,287430 USD |
| Pasivos inciertos | $1,500000 USD |
| Reservas pendientes | $0,00 USD |
| Exposición total | $17,787430 USD |
| Presupuesto disponible frente a exposición | $17,212570 USD |
| Porcentaje de exposición | 50,82 % |

La exposición total se mantuvo dentro del presupuesto autorizado.

Como indicador complementario, el coste confirmado dividido entre las 1.315 tareas exitosas equivale aproximadamente a **$0,01239 USD por tarea exitosa**. Es una razón global de coste por resultado, no el coste individual de cada llamada.

## 7. Evidencias y artefactos generados

La ejecución finalizó con estado `completed` y se reportó la generación de los siguientes artefactos:

1. `S4_OFFICIAL_RUN_SUMMARY.json`
   - Resumen de la ejecución.
   - Estado final.
   - Conteo de tareas.
   - Duración efectiva.
   - Exposición financiera.

2. `S4_OFFICIAL_RUN_TASKS.csv`
   - Registro de las 1.358 tareas.
   - Estados individuales.
   - Resultados de validación.

3. `S4_OFFICIAL_RUN_LLM_CALLS.csv`
   - Registro de las 1.392 llamadas.
   - Tokens.
   - Costes.
   - Identificadores de trazabilidad.
   - Estados de medición.

4. `S4_OFFICIAL_RUN_EXECUTION.log`
   - Bitácora de ejecución.
   - Eventos operativos.
   - Incidencias y recuperación.

También se reportó la finalización del worker `s4-official-worker-v3`, la liberación del advisory lock de PostgreSQL y la cancelación del monitor periódico una vez completada la ejecución.

**Nota de verificación documental:** los informes de ejecución confirman la generación y los tamaños de estos artefactos. La revisión directa de sus rutas, integridad, checksums y consistencia contra PostgreSQL debe quedar documentada en la auditoría posterior al cierre.

## 8. Estado técnico y actividades pendientes

Aunque la prueba oficial S4 finalizó satisfactoriamente, el cierre operativo no debe confundirse con el cierre del proceso de integración del repositorio.

Quedan pendientes:

1. Auditoría posterior a la ejecución: comparar PostgreSQL, JSON, CSV y log.
2. Verificar integridad, ubicación y consistencia de todos los artefactos.
3. Revisar el estado Git y los cambios pendientes.
4. Preparar commits individuales por corrección o unidad lógica.
5. Ejecutar una revisión de los cambios preparados antes de autorizar commits.
6. Completar una validación E2E manual del frontend y backend.
7. Revisar el historial final y preparar el push únicamente después de la autorización correspondiente.

No se debe considerar que los commits o el push ya fueron realizados. El cierre de S4 y la integración final del código son etapas diferentes.

## 9. Conclusión técnica

El trabajo de la semana permitió estabilizar el sistema de ejecución automatizada y completar una prueba oficial de carga que inicialmente presentaba problemas de continuidad, errores de comunicación y riesgos de conciliación financiera.

La ejecución final alcanzó 1.315 tareas exitosas y validadas, mantuvo 12 horas de actividad LLM continua y cerró con una exposición total de 17,787430 USD frente a un presupuesto autorizado de 35 USD.

Además del cumplimiento de los objetivos cuantitativos, se obtuvieron mejoras en la clasificación de ejercicios, la recuperación de fallos, el control de concurrencia, la trazabilidad de llamadas y la gestión financiera.

El resultado constituye un avance importante en la validación operativa del backend de Evaluador-Técnico y deja una base de evidencia para continuar con la auditoría, la preparación de commits y el cierre de integración.

---

## Resumen breve: problemas encontrados y logros

Durante el desarrollo de la prueba S4 tuvimos problemas con los tiempos de respuesta del proveedor LLM, interrupciones de la continuidad, errores de ejecución en Judge0 y fallos en la clasificación y recuperación de algunas tareas. Esto obligó a detener, auditar y corregir el sistema antes de continuar. Finalmente, logramos estabilizar la ejecución, completar **1.315 tareas exitosas y validadas**, mantener **más de 12 horas de actividad continua** y cerrar con una exposición financiera de **17,79 USD sobre los 35 USD autorizados**, generando registros y evidencias para respaldar los resultados.
