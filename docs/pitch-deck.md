# Pitch Deck: Evaluador Técnico de Candidatos con IA
## *Evaluación técnica defendible, objetiva y adaptativa para el talento TI en Colombia y Latinoamérica*

---

## 1. El Problema (The Problem)

### ¿Por qué la contratación técnica en Colombia y Latam está rota?
1. **Falsos Positivos & LeetCode Memorization:** Las pruebas tradicionales de código tipo "puzzle" evalúan memorización de algoritmos poco realistas. Los candidatos copian soluciones de ChatGPT o GitHub Copilot sin comprender los fundamentos de diseño ni la gestión de complejidad.
2. **Cuellos de Botella en Ingeniería:** Los ingenieros Senior y Tech Leads dedican entre **12 y 18 horas semanales** a realizar entrevistas técnicas iniciales repetitivas, deteniendo el roadmap de producto.
3. **Falta de Defendibilidad y Sesgo:** Las decisiones de contratación suelen depender de notas subjetivas ("no me dio buena vibra", "escribió código desordenado"). Ante auditorías o reclamos laborales, no existe evidencia forense verificable.
4. **Riesgos de Cumplimiento Legal (Habeas Data):** Plataformas invasivas utilizan grabación por cámara web y análisis biométrico que violan la **Ley 1581 de 2012 de Colombia**, exponiendo a las empresas a sanciones de la SIC (Superintendencia de Industria y Comercio).

---

## 2. Nuestra Solución (The Solution)

**Evaluador Técnico** es la primera plataforma B2B de evaluación de código impulsada por un Agente Socrático con IA que evalúa **el razonamiento del candidato en tiempo real**, no solo una respuesta binaria pasa/falla.

```
       Candidato                   Agente Socrático                  Juez LLM & Sandbox
           │                               │                                 │
           ├─── Clarifica requisitos ─────►│                                 │
           │◄── Respuestas contextuales ───┤                                 │
           │                               │                                 │
           ├─── Diseña arquitectura ──────►│                                 │
           ├─── Escribe código y tests ───►│── Telemetría en tiempo real ───►│ (Sandbox aislado)
           │                               │                                 │
           │◄── Preguntas PROBE Anti-Cheat─┤                                 │
           │                               │                                 ▼
           ▼                               ▼                     Informe Defendible PDF
   Experiencia Humana              Sin Invasión Biométrica       (Radar 5D + Hash SHA-256)
```

### Características Diferenciales:
- **Agente Conversacional Socrático:** Guía al candidato en 8 fases estructuradas (`INTRO` → `PROBLEM` → `CLARIFY` → `DESIGN` → `CODING` → `PROBE` → `WRAPUP` → `EVALUATE`).
- **Anti-Cheat Cognitivo (Sin Cámaras):** Si el candidato pega código complejo repentinamente, la IA formula preguntas de sondeo sobre la complejidad algorítmica y decisiones de diseño para probar autoría genuina.
- **Rúbrica Armonizada de 5 Dimensiones:**
  1. *Resolución de Problemas* (Problem Solving)
  2. *Razonamiento Algorítmico* (Algorithmic Reasoning)
  3. *Calidad de Código y Tipado* (Code Quality)
  4. *Comunicación Técnica* (Technical Communication)
  5. *Gestión de Complejidad y Escalabilidad* (Complexity Management)
- **Informe Defendible en PDF con Hash SHA-256:** Generado automáticamente con WeasyPrint, incluye radar de competencias y citas forenses directas de la conversación.
- **Habeas Data (Ley 1581 de 2012):** Consentimiento informado previo, anonimización por defecto (`CAND-XXXX`) y endpoints de supresión de datos / derecho al olvido.

---

## 3. Demostración de ROI (Business Case)

Para una empresa de tecnología o software factory que contrata 10 desarrolladores al mes evaluando a 60 candidatos:

| Métrica | Proceso Tradicional (Ingenieros) | Evaluador Técnico IA | Ahorro / Beneficio |
| :--- | :--- | :--- | :--- |
| **Tiempo de Tech Lead por candidato** | 90 minutos | 10 minutos (revisión de informe) | **-88% de tiempo** |
| **Horas de ingeniería invertidas** | 90 horas / mes | 10 horas / mes | **80 horas recuperadas** |
| **Costo por proceso de evaluación** | $4,500,000 COP ($1,150 USD) | $750,000 COP ($190 USD) | **Ahorro de ~$3.7M COP / mes** |
| **Tiempo de respuesta al candidato** | 5 a 10 días hábiles | **Inmediato (Mismo día)** | **Mejor satisfacción y retención** |
| **Trazabilidad y Cumplimiento SIC** | Inexistente / Notas dispersas | Hash SHA-256 auditado en PDF | **100% defendible** |

---

## 4. Mercado Objetivo (Tam / Sam / Som)

- **TAM (Total Addressable Market):** Mercado de contratación técnica y HR Tech en América Latina (~$1.8B USD).
- **SAM (Serviceable Available Market):** Empresas de software, fintechs, bancos y consultoras de desarrollo en Colombia, México y la región andina (~$280M USD).
- **SOM (Serviceable Obtainable Market):** 1,200 software factories, startups fintech y bootcamps en Colombia que requieren escalabilidad y cumplimiento de Ley 1581 (~$14M USD).

---

## 5. Modelo de Negocio & Pricing B2B (SaaS)

| Plan | Tarifa Mensual | Evaluaciones Incluidas | Características Clave |
| :--- | :--- | :--- | :--- |
| **Starter** | $149 USD / mes (~$590,000 COP) | 25 entrevistas / mes | Catálogo de problemas estándar, soporte por email, informes PDF defendibles con SHA-256. |
| **Growth (Recomendado)** | $399 USD / mes (~$1,580,000 COP) | 80 entrevistas / mes | Problemas adaptativos a la vacante con IA, Anti-cheat cognitivo avanzado, webhook API y soporte prioritario. |
| **Enterprise** | Custom ($890+ USD / mes) | Ilimitadas | Integración ATS (Greenhouse, Lever), problemas propietarios, despliegue On-Premise / Single-Tenant y SLA del 99.9%. |

---

## 6. Tracción y Hoja de Ruta Tecnológica

- **Sprint 0 - 2:** Infraestructura core, State Machine de 8 fases, ejecución sandbox en Judge0 CE, WebSocket con tokens efímeros y catálogo de problemas para Colombia (Fintech, Nómina, DIAN).
- **Sprint 3 - 4:** Sincronización bidireccional de telemetría de código, generador de PDF WeasyPrint con vector radar, anti-cheat cognitivo y módulo de privacidad Ley 1581.
- **Sprint 5 - 6:** Harness de calibración de jueces LLM (100% de consistencia), Modo Demo interactivo offline para ventas y congelación de release v1.0.0.

---

## 7. Equipo Fundador & Contacto

- **Cristian & Equipo de Ingeniería de Evaluador Técnico**
- **Sede:** Bogotá / Bucaramanga, Colombia
- **Website:** `https://evaluador-tecnico.co` (Demo interactiva en `/demo`)
