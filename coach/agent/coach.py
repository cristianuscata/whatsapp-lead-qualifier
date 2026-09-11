"""
Lógica principal del coach.

Pipeline cuando llega un mensaje de Cristian:
1. ¿Es feedback de un recordatorio pendiente (sí/no/a medias)? → procesarlo.
2. ¿Es consulta sobre el Calendar (hoy/mañana)?                → lista armada en código + cierre del LLM.
3. ¿Es una nueva intención de tarea con hora?                  → crear recordatorio.
4. Si nada de lo anterior                                       → chat libre con el coach.
"""

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from coach.agent.intent import detectar_recordatorio, detectar_consulta_calendar
from coach.agent.openai_coach import responder_chat, generar_mensaje
from coach.agent.prompts import (
    plantilla_confirmacion_recordatorio,
    plantilla_no_cumplido,
)
from coach.agent.state import (
    get_pendiente_feedback,
    clear_pendiente_feedback,
    add_evento_calendar_cumplido,
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

    # 2. ¿Consulta sobre eventos del Calendar? (ruta dedicada, lista armada en código)
    alcance_cal = await detectar_consulta_calendar(texto)
    if alcance_cal:
        await m_db.guardar("user", texto)
        await _responder_consulta_calendar(numero, alcance_cal)
        return

    # 3. ¿Nueva intención de tarea?
    intent = await detectar_recordatorio(texto)
    if intent:
        await m_db.guardar("user", texto)
        await _crear_y_confirmar(numero, intent)
        return

    # 4. Chat libre — usamos historial PREVIO al mensaje actual.
    # Mantenemos 30 mensajes para que el coach pueda hilar conversaciones
    # de los últimos días (no solo del momento).
    historial = await m_db.historial(limite=30)
    await m_db.guardar("user", texto)
    try:
        respuesta = await responder_chat(texto, historial)
    except Exception as e:
        log.error(f"[COACH] error generando respuesta: {e}")
        respuesta = "Estoy teniendo un problema momentáneo. Vuelve a escribirme en un minuto."
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
    """
    Asocia el sí/no/medias al pendiente más reciente: puede ser un recordatorio
    de DB o un evento de Calendar. Se prioriza state.json (más fresco) sobre la
    DB; si no hay pendiente registrado se cae a la lógica antigua por compat.
    """
    pendiente_state = get_pendiente_feedback()

    es_calendar = pendiente_state and pendiente_state.get("tipo") == "calendar"
    tarea: str
    rec_id: int | None = None
    calendar_key: str | None = None

    if es_calendar:
        tarea = pendiente_state["tarea"]
        calendar_key = pendiente_state["ref"]
    else:
        # Recordatorio: usar state si está, sino la DB (back-compat)
        rec = None
        if pendiente_state and pendiente_state.get("tipo") == "recordatorio":
            try:
                rec_id = int(pendiente_state["ref"])
                rec = {"id": rec_id, "tarea": pendiente_state["tarea"]}
            except (ValueError, KeyError):
                rec = None
        if rec is None:
            rec = await r_db.ultimo_pendiente_seguimiento()
        if not rec:
            respuesta = (
                "No tengo un recordatorio abierto para asociar tu respuesta. "
                "¿Quieres contarme qué pasó?"
            )
            await m_db.guardar("assistant", respuesta)
            await enviar_mensaje(numero, respuesta)
            return
        tarea = rec["tarea"]
        rec_id = rec["id"]

    if feedback is True:
        if es_calendar:
            add_evento_calendar_cumplido(calendar_key)
            log.info(f"[CALENDAR] evento marcado cumplido en state: {tarea}")
        else:
            await r_db.marcar_cumplido(rec_id, True)
            hoy = datetime.now(TZ_LIMA).date()
            borradas = await r_db.eliminar_reprogramaciones_futuras(tarea, hoy)
            if borradas:
                log.info(f"[COACH] limpié {borradas} reprogramación(es) futura(s) de '{tarea}' (sí tardío)")
        instr = (
            f"Cristian acaba de confirmar que cumplió: '{tarea}'. "
            "Celebra genuinamente en máximo 4 líneas, con versículo."
        )
        try:
            respuesta = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando celebración: {e}")
            respuesta = (
                f"🔥 Así se hace: {tarea}.\n"
                f"Cada paso te acerca a tus metas.\n"
                f"'Todo lo puedo en Cristo que me fortalece' — Fil 4:13"
            )

    elif feedback is False:
        if es_calendar:
            add_evento_calendar_cumplido(calendar_key)  # cerramos la pregunta
        else:
            await r_db.marcar_cumplido(rec_id, False)
            await r_db.marcar_reprogramado(rec_id)
        instr = (
            f"Cristian acaba de decir que NO cumplió con: '{tarea}'. "
            "Responde con calidez genuina, sin juicio y sin sermón. "
            "1) pregúntale qué pasó (curiosidad, no reproche), "
            "2) ofrécele reagendar (mañana misma hora u otra que te diga), "
            "3) cierra con versículo breve. Máximo 4 líneas, tono de amigo no de jefe."
        )
        try:
            respuesta = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando follow-up empático: {e}")
            respuesta = plantilla_no_cumplido(tarea)

    else:  # "medias"
        if es_calendar:
            add_evento_calendar_cumplido(calendar_key)
        else:
            await r_db.marcar_cumplido(rec_id, False)
            await r_db.marcar_reprogramado(rec_id)
        instr = (
            f"Cristian cumplió a medias con: '{tarea}'. "
            "Responde con calidez: "
            "1) reconoce lo que sí avanzó, "
            "2) pregúntale qué le faltó / qué le trabó, "
            "3) sugiérele un siguiente paso concreto (chico) para hoy. "
            "Cierra con versículo. Máximo 4 líneas, tono de amigo."
        )
        try:
            respuesta = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando follow-up a medias: {e}")
            respuesta = (
                f"Algo es algo. ¿Qué te faltó para terminarlo?\n"
                f"Dime un paso chico que sí puedes cerrar hoy.\n"
                f"'No os canséis de hacer el bien' — Gál 6:9"
            )

    clear_pendiente_feedback()
    await m_db.guardar("assistant", respuesta, tipo="feedback_respuesta")
    await enviar_mensaje(numero, respuesta)


async def _crear_y_confirmar(numero: str, intent: dict) -> None:
    hoy = datetime.now(TZ_LIMA).date()
    fecha_tarea = intent.get("fecha") or hoy
    hora_tarea = intent["hora"]
    tarea = intent["tarea"]
    meta_key = intent.get("meta_key")

    momento_tarea = datetime.combine(fecha_tarea, hora_tarea)
    hora_recordar    = (momento_tarea - timedelta(minutes=5)).time()
    hora_seguimiento = (momento_tarea + timedelta(minutes=30)).time()

    # Detectar conflicto con Calendar ANTES de crear (no bloqueante, solo informativo)
    conflicto = None
    try:
        from coach.integrations.calendar import listar_eventos, detectar_conflicto
        eventos_fecha = listar_eventos(fecha_tarea)
        conflicto = detectar_conflicto(eventos_fecha, fecha_tarea, hora_tarea)
    except Exception as e:
        log.warning(f"[CALENDAR] no pude verificar conflictos: {e}")

    await r_db.crear_recordatorio(tarea, hora_recordar, hora_seguimiento, fecha_tarea, meta_key=meta_key)

    try:
        from coach.integrations.calendar import crear_evento
        crear_evento(tarea, fecha_tarea, hora_tarea)
    except Exception as e:
        log.warning(f"[CALENDAR] no se pudo crear el evento: {e}")

    # Formatear fecha para el mensaje de confirmación si no es hoy
    fecha_confirmacion_str = ""
    if fecha_tarea != hoy:
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        fecha_confirmacion_str = f"{dias[fecha_tarea.weekday()]} {fecha_tarea.day} de {meses[fecha_tarea.month - 1]}"

    respuesta = plantilla_confirmacion_recordatorio(
        tarea,
        hora_recordar.strftime("%H:%M"),
        hora_tarea.strftime("%H:%M"),
        fecha_confirmacion_str
    )
    if conflicto:
        respuesta += (
            f"\n\n⚠️ Ojo: a esa hora tienes *{conflicto['summary']}* "
            f"({conflicto['hora_inicio']}–{conflicto['hora_fin']}) en Calendar. "
            f"Si lo mueves dime."
        )

    await m_db.guardar("assistant", respuesta, tipo="confirmacion_recordatorio")
    await enviar_mensaje(numero, respuesta)


_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_humana_corta(fecha) -> str:
    return f"{_DIAS_ES[fecha.weekday()]} {fecha.day} de {_MESES_ES[fecha.month - 1]}"


def _formatear_lista_eventos(eventos: list[dict]) -> str:
    if not eventos:
        return "(sin eventos programados)"
    return "\n".join(
        f"• {ev['hora_inicio']}–{ev['hora_fin']}: {ev['summary']}" for ev in eventos
    )


async def _responder_consulta_calendar(numero: str, alcance: str) -> None:
    """
    Responde una consulta de calendar con la lista EXACTA armada en código
    (sin pasar por LLM) + un cierre breve del LLM (versículo + pregunta).
    Garantiza fidelidad de la lista.
    """
    from coach.integrations.calendar import listar_eventos

    hoy = datetime.now(TZ_LIMA).date()
    manana = hoy + timedelta(days=1)

    bloques: list[str] = []
    resumen_para_cierre: list[str] = []

    if alcance in ("hoy", "ambos"):
        try:
            eventos_hoy = listar_eventos(hoy)
        except Exception as e:
            log.warning(f"[CALENDAR] error listando eventos de hoy: {e}")
            eventos_hoy = []
        bloques.append(
            f"📅 *Hoy {_fecha_humana_corta(hoy)}:*\n{_formatear_lista_eventos(eventos_hoy)}"
        )
        resumen_para_cierre.append(f"hoy tiene {len(eventos_hoy)} evento(s)")

    if alcance in ("manana", "ambos"):
        try:
            eventos_manana = listar_eventos(manana)
        except Exception as e:
            log.warning(f"[CALENDAR] error listando eventos de mañana: {e}")
            eventos_manana = []
        bloques.append(
            f"📅 *Mañana {_fecha_humana_corta(manana)}:*\n{_formatear_lista_eventos(eventos_manana)}"
        )
        resumen_para_cierre.append(f"mañana tiene {len(eventos_manana)} evento(s)")

    lista = "\n\n".join(bloques)

    # El LLM solo arma el cierre — NO toca la lista
    instr = (
        f"Cristian acaba de pedir su agenda de Calendar ({', '.join(resumen_para_cierre)}). "
        "Ya le mostré la lista arriba. Genera SOLO un cierre breve (2 líneas máximo): "
        "1) un versículo bíblico corto con referencia, "
        "2) una pregunta concreta tipo '¿por cuál arrancas?' o '¿cómo te sientes con el día?'. "
        "NO repitas la lista. NO menciones eventos específicos. Tono cálido."
    )
    try:
        cierre = await generar_mensaje(instr)
    except Exception as e:
        log.error(f"[COACH] error generando cierre consulta calendar: {e}")
        cierre = (
            "'Todo lo puedo en Cristo que me fortalece' — Fil 4:13\n"
            "¿Por cuál vas a arrancar?"
        )

    respuesta = f"{lista}\n\n{cierre}"
    await m_db.guardar("assistant", respuesta, tipo="consulta_calendar")
    await enviar_mensaje(numero, respuesta)
