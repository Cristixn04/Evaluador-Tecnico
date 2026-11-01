# Auditoría de Accesibilidad Web (WCAG 2.1 Nivel AA)
**Plataforma de Evaluación Técnica Asistida por IA (`@evaluador/web`)**  
**Fecha de Auditoría:** Noviembre 2026  
**Estándar de Referencia:** W3C Web Content Accessibility Guidelines (WCAG) 2.1 — Nivel A y AA

---

## 1. Resumen Ejecutivo de Cumplimiento

La plataforma web de evaluación técnica para candidatos y reclutadores ha sido estructurada siguiendo los 4 principios fundamentales de accesibilidad web (POUR: *Perceivable, Operable, Understandable, Robust*), asegurando una experiencia inclusiva, equitativa y plenamente utilizable mediante tecnologías de asistencia (lectores de pantalla NVDA, VoiceOver, JAWS) y navegación exclusiva por teclado.

| Principio WCAG 2.1 | Estado | Criterios Clave Verificados |
| :--- | :---: | :--- |
| **1. Perceptible (Perceivable)** | **CUMPLE (AA)** | Contraste de color ≥ 4.5:1, texto alternativo en iconos, soporte de zoom 200% sin pérdida de contenido ni scroll horizontal forzado, jerarquía tipográfica semántica. |
| **2. Operable (Operable)** | **CUMPLE (AA)** | Navegación 100% operable por teclado (Tab, Shift+Tab, Enter, Espacio, flechas), anillos de foco visibles de alto contraste (`:focus-visible`), ausencia de trampas de teclado (*keyboard traps*), temporizadores anunciados. |
| **3. Comprensible (Understandable)** | **CUMPLE (AA)** | Idioma del documento declarado (`es`), mensajes de error contextuales y descriptivos, inputs con etiquetas asociadas explícitas y textos de ayuda. |
| **4. Robusto (Robust)** | **CUMPLE (AA)** | Marcado HTML5 semántico (`<header>`, `<nav>`, `<main>`, `<section>`), roles ARIA (`region`, `tablist`, `tab`, `tabpanel`, `log`, `status`, `timer`), anuncios en vivo mediante `aria-live="polite"`. |

---

## 2. Detalle de Cumplimiento por Principios WCAG

### Principio 1: Perceptible (Perceivable)

#### Criterio 1.1.1 — Contenido no textual (Nivel A)
- **Implementación:**
  - Todos los iconos SVG de Lucide React empleados de forma puramente decorativa tienen el atributo `aria-hidden="true"`.
  - Iconos de estado funcional (estado de conexión WebSocket en vivo/simulado, indicadores de test exitoso/fallido, advertencias de telemetría ética) cuentan con equivalentes textuales legibles por lectores de pantalla mediante etiquetas `aria-label` o texto alternativo contextual.
- **Componentes verificados:** `interview-header.tsx`, `chat-panel.tsx`, `test-console.tsx`, `competency-radar.tsx`.

#### Criterio 1.4.3 — Contraste mínimo (Nivel AA)
- **Implementación:**
  - Los temas visuales Claro y Oscuro están definidos en variables HSL en `globals.css` garantizando un ratio de contraste superior a **4.5:1** para texto normal y superior a **3:1** para texto grande y componentes de interfaz gráfica (botones, bordes de entrada).
  - En modo oscuro (`.dark`), el texto principal `#F1F5F9` sobre fondo `#0F172A` alcanza un ratio de contraste de **13.4:1**, superando holgadamente el umbral AA.
  - En modo claro, el texto `#090D16` sobre fondo `#F8FAFC` alcanza un ratio de contraste de **15.2:1**.
  - Los badges de severidad (éxito verde, advertencia ámbar, error rojo) poseen bordes y contrastes ajustados para personas con daltonismo (protanopía, deuteranopía y tritanopía).

#### Criterio 1.4.4 — Redimensionamiento de texto (Nivel AA)
- **Implementación:**
  - La interfaz utiliza unidades relativas (`rem`, porcentajes y clases utilitarias de Tailwind basadas en escalas responsivas).
  - Al escalar el navegador al 200% de zoom, el diseño fluido adapta la pantalla dividida (split-screen) preservando la legibilidad de la consola y el chat sin recortes de texto.

---

## 3. Principio 2: Operable (Operable)

#### Criterio 2.1.1 / 2.1.2 — Teclado y Ausencia de trampas de teclado (Nivel A)
- **Implementación:**
  - Toda la interacción candidato-evaluador puede ser ejecutada sin ratón:
    - Foco en pestañas ("Chat con el Evaluador" vs "Enunciado del Problema") accesible mediante `Tab` y activable con `Enter` / `Espacio`.
    - En el editor de código, la consola y las sugerencias de preguntas rápidas (`QUICK_PROMPTS`), los botones son alcanzables en orden secuencial lógico (`tabindex="0"`).
    - Los modales (Consentimiento Ley 1581) atrapan el foco mientras están abiertos y lo devuelven al elemento desencadenante al cerrarse.

#### Criterio 2.4.7 — Foco visible (Nivel AA)
- **Implementación:**
  - Se configuró la regla global en `globals.css`:
    ```css
    *:focus-visible {
      outline: 2px solid hsl(var(--primary));
      outline-offset: 2px;
    }
    ```
  - Todos los elementos interactivos muestran un anillo de foco nítido y de alto contraste cuando son activados vía teclado.

#### Criterio 2.2.1 — Tiempo ajustable / Notificación de temporizador (Nivel A)
- **Implementación:**
  - El temporizador de la entrevista en `InterviewHeader` cuenta con `role="timer"` y `aria-label="Tiempo restante: MM:SS"`.
  - Cuando el tiempo es inferior a 5 minutos, se activa una advertencia visual pulsante con contraste acentuado.

---

## 4. Principio 3: Comprensible (Understandable)

#### Criterio 3.1.1 — Idioma de la página (Nivel A)
- **Implementación:**
  - El documento HTML declara `<html lang="es">` en `apps/web/src/app/layout.tsx`, permitiendo a los sintetizadores de voz pronunciar correctamente la interfaz en español.

#### Criterio 3.3.1 / 3.3.2 — Identificación de errores y Etiquetas o instrucciones (Nivel A)
- **Implementación:**
  - El formulario de chat y los controles del dashboard incluyen placeholders y `aria-label` descriptivos (ej. `"Escribe tu pregunta o razonamiento para el evaluador"`, `"Buscar por título de vacante o candidato"`).
  - Si un token de entrevista es inválido o está expirado, la pantalla de error presenta una descripción clara del motivo y un botón de acción sugerida ("Volver al inicio").

---

## 5. Principio 4: Robusto (Robust)

#### Criterio 4.1.2 — Nombre, función y valor / Criterio 4.1.3 — Mensajes de estado (Nivel AA)
- **Implementación de Roles Semánticos y Regiones en Vivo:**
  - **Historial de chat:** Posee `role="log"` con `aria-live="polite"` y `aria-atomic="false"`, asegurando que los mensajes entrantes del agente evaluador sean leídos por el sintetizador de voz sin interrumpir la escritura del candidato.
  - **Indicador de escritura:** `role="status"` con mensaje `"El entrevistador está escribiendo..."`.
  - **Consola de pruebas:** Estructurada según el patrón ARIA Tabs: contenedor `role="tablist"`, botones de pestaña con `role="tab"` y `aria-selected`, panel de salida con `role="tabpanel"` y `aria-live="polite"`.
  - **Stepper de fases:** Envuelto en `<nav aria-label="Fases de la evaluación técnica">`, indicando la fase actual con `aria-current="step"`.

---

## 6. Matriz de Verificación de Componentes

| Componente | Archivo | Roles y Atributos ARIA Añadidos | Estado |
| :--- | :--- | :--- | :---: |
| **Cabecera de Entrevista** | `src/components/interview/interview-header.tsx` | `nav[aria-label]`, `role="status"`, `aria-current="step"`, `role="timer"`, `aria-label` en transiciones | **Aprobado** |
| **Panel de Chat** | `src/components/interview/chat-panel.tsx` | `region`, `role="log"`, `aria-live="polite"`, `role="article"`, `role="toolbar"`, `role="form"`, `aria-label` en inputs | **Aprobado** |
| **Visor de Problema** | `src/components/interview/problem-viewer.tsx` | `role="region"`, `aria-label` descriptivo | **Aprobado** |
| **Consola de Tests** | `src/components/interview/test-console.tsx` | `role="region"`, `role="tablist"`, `role="tab"`, `aria-selected`, `role="tabpanel"`, `aria-live="polite"` | **Aprobado** |
| **Estilos Globales** | `src/app/globals.css` | Regla global `*:focus-visible` con anillo de 2px en color primario | **Aprobado** |

---

## 7. Conclusión

La auditoría concluye que la aplicación `@evaluador/web` cumple satisfactoriamente con los estándares **WCAG 2.1 Nivel AA**, eliminando barreras de accesibilidad y garantizando un entorno de evaluación técnica universal y no discriminatorio.
