"""
Lógica principal del coach.

Pipeline cuando llega un mensaje de Cristian:
1. ¿Es feedback de un recordatorio pendiente (sí/no/a medias)? → procesarlo.
2. ¿Es una nueva intención de tarea con hora?                  → crear recordatorio.
3. Si nada de lo anterior                                       → chat libre con el coach.
"""

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from coach.agent.intent import detectar_recordatorio
from coach.agent.openai_coach import responder_chat, generar_mensaje
from coach.agent.prompts import (
    plantilla_confirmacion_recordatorio,
    plantilla_no_cumplido,
)
from coach.db import mensajes as m_db
from coach.db import recordatorios as r_db
from whatsapp import enviar_mensaje

log = logging.getLogger(__name__)
TZ_LIMA = ZoneInfo("America/Lima")

# Patrones de feedback corto (sí/no/a medias)
PATRON_SI       = re.compile(r"^\s*(s[ií]+|listo|hecho|cumplido|done|yes|ok+)\s*[.!]?\s*$", re.IGNORECASE)
PATRON_NO       = re.compile(r"^\s*(no+|nope|no pude|no lo hice|negativo)\s*[.!]?\s*$", re.IGNORECASE)
PATRON_A_MEDIAS = re.compile(r"^\s*(a medias|m[aá]s o menos|parcial|kinda|sortof)\s*[.!]?\s*$", re.IGNORECASE)


async def coach_handle_message(numero: str, mensaje: str) -> None:
    """
    Punto de entrada del coach. Lo llama el webhook cuando el remitente
    es CRISTIAN_PHONE.
    """
    texto = mensaje.strip()
    log.info(f"[COACH] mensaje de Cristian: {texto[:80]}")

    # Cualquier mensaje cuenta como "respondiste al check del mediodía"
    try:
        from coach.scheduler import marcar_check_mediodia_respondido
        marcar_check_mediodia_respondido()
    except Exception:
        pass  # si el scheduler no está activo, no rompemos el flujo

    # 1. ¿Feedback de un recordatorio pendiente?
    feedback = _detectar_feedback(texto)
    if feedback is not None:
        await m_db.guardar("user", texto)
        await _procesar_feedback(numero, feedback)
        return

    # 2. ¿Nueva intención de tarea?
    intent = await detectar_recordatorio(texto)
    if intent:
        await m_db.guardar("user", texto)
        await _crear_y_confirmar(numero, intent)
        return

    # 3. Chat libre — usamos historial PREVIO al mensaje actual
    historial = await m_db.historial(limite=10)
    await m_db.guardar("user", texto)
    try:
        respuesta = await responder_chat(texto, historial)
    except Exception as e:
        log.error(f"[COACH] error generando respuesta: {e}")
        respuesta = "Estoy teniendo un problema momentáneo. Volvé a escribirme en un minuto."
    await m_db.guardar("assistant", respuesta)
    await enviar_mensaje(numero, respuesta)


def _detectar_feedback(texto: str):
    """Retorna True (cumplido), False (no), 'medias', o None si no es feedback."""
    if PATRON_SI.match(texto):
        return True
    if PATRON_NO.match(texto):
        return False
    if PATRON_A_MEDIAS.match(texto):
        return "medias"
    return None


async def _procesar_feedback(numero: str, feedback) -> None:
    pendiente = await r_db.ultimo_pendiente_seguimiento()
    if not pendiente:
        respuesta = (
            "No tengo un recordatorio abierto para asociar tu respuesta. "
            "¿Querés contarme qué pasó?"
        )
        await m_db.guardar("assistant", respuesta)
        await enviar_mensaje(numero, respuesta)
        return

    tarea = pendiente["tarea"]
    rec_id = pendiente["id"]

    if feedback is True:
        await r_db.marcar_cumplido(rec_id, True)
        instr = (
            f"Cristian acaba de confirmar que cumplió: '{tarea}'. "
            "Celebrá genuinamente en máximo 4 líneas, con versículo."
        )
        try:
            respuesta = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando celebración: {e}")
            respuesta = (
                f"🔥 Así se hace: {tarea}.\n"
                f"Cada paso suma a Sydney.\n"
                f"'Todo lo puedo en Cristo' — Fil 4:13"
            )

    elif feedback is False:
        await r_db.marcar_cumplido(rec_id, False)
        await r_db.marcar_reprogramado(rec_id)  # ofrecemos reagendar manualmente
        respuesta = plantilla_no_cumplido(tarea)

    else:  # "medias"
        await r_db.marcar_cumplido(rec_id, False)
        await r_db.marcar_reprogramado(rec_id)
        instr = (
            f"Cristian cumplió a medias con: '{tarea}'. "
            "Confrontá con amor, sin juzgar, y empujá a ejecución completa. "
            "Máximo 4 líneas, con versículo."
        )
        try:
            respuesta = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando confrontación: {e}")
            respuesta = (
                f"A medias no cuenta como cumplido. Sin juicio, pero la verdad duele.\n"
                f"¿Qué necesitás para terminarlo hoy?\n"
                f"'No os canséis de hacer el bien' — Gál 6:9"
            )

    await m_db.guardar("assistant", respuesta, tipo="feedback_respuesta")
    await enviar_mensaje(numero, respuesta)


async def _crear_y_confirmar(numero: str, intent: dict) -> None:
    hoy = datetime.now(TZ_LIMA).date()
    hora_tarea = intent["hora"]
    tarea = intent["tarea"]

    momento_tarea = datetime.combine(hoy, hora_tarea)
    hora_recordar    = (momento_tarea - timedelta(minutes=5)).time()
    hora_seguimiento = (momento_tarea + timedelta(minutes=30)).time()

    await r_db.crear_recordatorio(tarea, hora_recordar, hora_seguimiento, hoy)

    try:
        from coach.integrations.calendar import crear_evento
        crear_evento(tarea, hoy, hora_tarea)
    except Exception as e:
        log.warning(f"[CALENDAR] no se pudo crear el evento: {e}")

    respuesta = plantilla_confirmacion_recordatorio(
        tarea,
        hora_recordar.strftime("%H:%M"),
        hora_tarea.strftime("%H:%M"),
    )
    await m_db.guardar("assistant", respuesta, tipo="confirmacion_recordatorio")
    await enviar_mensaje(numero, respuesta)
