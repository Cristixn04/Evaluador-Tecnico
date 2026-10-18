# Umbrales de inactividad para entrega de hints (en segundos)
# Definidos basándose en los archivos de hints v2:
#   Nivel 1: >3 min sin output o progreso
#   Nivel 2: >5 min o errores recurrentes en tests
#   Nivel 3: >10 min o frustración detectada
HINT_THRESHOLDS_SECONDS = [180, 300, 600]  # 3min, 5min, 10min


def get_threshold(hint_level: int) -> int:
    """Obtener el umbral de inactividad para el nivel de hint dado."""
    if hint_level < 0 or hint_level >= len(HINT_THRESHOLDS_SECONDS):
        return 0
    return HINT_THRESHOLDS_SECONDS[hint_level]