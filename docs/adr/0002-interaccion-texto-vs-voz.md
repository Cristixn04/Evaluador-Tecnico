# ADR 0002: Interacción por Chat Técnico y Código Escrito vs Voz en el MVP

## Estado
Aceptado

## Contexto
En procesos de contratación de tecnología existe el dilema entre entrevistas habladas (llamadas de voz simuladas) versus interfaces interactivas de chat técnico asistido con editor de código en tiempo real. 

## Decisión
Para el producto mínimo viable (MVP) y las versiones v1.x, el Evaluador Técnico operará **100% mediante chat técnico interactivo por texto y editor de código en vivo (Monaco Editor)**, posponiendo interfaces de voz bidireccional para fases avanzadas posteriores.

## Justificación Estratégica
1. **Eliminación Total del Sesgo de Acento y Origen Geográfico:**
   En Colombia y Latinoamérica, el tono de voz, acento regional o fluidez al hablar generan sesgos inconscientes en evaluadores humanos y en modelos de IA de audio. El texto técnico escrito nivela el campo de juego y asegura que el informe sea 100% defendible y ciego a sesgos.
2. **Cero Errores de Transcripción (STT):**
   Los modelos Speech-to-Text suelen cometer errores críticos al transcribir terminología técnica, nombres de variables, sintaxis SQL o palabras reservadas en inglés y español mezclados (p. ej., confundir `boolean` con `bullet`, `dict` con `did`, o nombres de paquetes).
3. **Latencia y Costos Operativos:**
   La inferencia de voz en tiempo real incrementa los costos de API hasta en un 800% y añade latencia de 1 a 2 segundos que deteriora la experiencia técnica.
4. **Fidelidad al Trabajo Real:**
   El trabajo diario de un desarrollador de software ocurre en Slack, pull requests, documentación y editores de código. Explicar un diseño por escrito y estructurar código refleja de forma más fidedigna la habilidad técnica real que improvisar respuestas orales bajo estrés.

## Consecuencias
- Mayor accesibilidad para candidatos con limitaciones auditivas o en entornos con ruido ambiental.
- El modelo de evaluación procesa transcripciones limpias y reproducibles.
