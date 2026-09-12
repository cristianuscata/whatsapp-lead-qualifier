"""
Lógica principal del coach.

Pipeline cuando llega un mensaje de Cristian:
1. ¿Hay una gestión de meta esperando confirmación (sí/no)?    → aplicarla o cancelar.
2. ¿Es feedback de un recordatorio pendiente (sí/no/a medias)? → procesarlo.
3. ¿Es una gestión de meta (agregar/pausar/listar)?           → confirmar y escribir.
4. ¿Es una nueva intención de tarea con hora?                  → crear recordatorio.
5. Si nada de lo anterior                                       → chat libre con el coach.
"""

import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from coach.agent.intent import detectar_recordatorio
from coach.agent.meta_intent import detectar_gestion_meta
from coach.agent.openai_coach import responder_chat, generar_mensaje
from coach.agent.prompts import (
    plantilla_confirmacion_recordatorio,
    plantilla_no_cumplido,
)
from coach.agent.state import (
    get_pendiente_feedback,
    clear_pendiente_feedback,
    get_pendiente_meta,
    set_pendiente_meta,
    clear_pendiente_meta,
)
from coach.db import mensajes as m_db
from coach.db import recordatorios as r_db
from coach.db import metas as metas_db
from coach.db.metas import obtener_metas
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

    # 0. ¿Hay una gestión de meta esperando confirmación (sí/no)?
    if get_pendiente_meta() is not None:
        if PATRON_SI.match(texto):
            await m_db.guardar("user", texto)
            await _confirmar_gestion_meta(numero, aplicar=True)
            return
        if PATRON_NO.match(texto):
            await m_db.guardar("user", texto)
            await _confirmar_gestion_meta(numero, aplicar=False)
            return
        # Respondió otra cosa: descartamos la propuesta y seguimos el flujo normal.
        clear_pendiente_meta()

    # 1. ¿Feedback de un recordatorio pendiente?
    feedback = _detectar_feedback(texto)
    if feedback is not None:
        await m_db.guardar("user", texto)
        await _procesar_feedback(numero, feedback)
        return

    # 2. ¿Gestión de una meta (agregar / pausar / abandonar / listar)?
    metas_actuales = await obtener_metas()
    gestion = await detectar_gestion_meta(texto, [m["key"] for m in metas_actuales])
    if gestion:
        await m_db.guardar("user", texto)
        await _manejar_gestion_meta(numero, gestion)
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
        if os.getenv("USE_MCP_AGENT", "false").lower() == "true":
            # Coach de alto rendimiento: agente que descubre tools por MCP.
            from coach.agent.agente_mcp import responder_agente
            respuesta = await responder_agente(texto, historial)
        else:
            # Comportamiento v1: chat libre con contexto inyectado en el prompt.
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
    Asocia el sí/no/medias al recordatorio pendiente más reciente. Se prioriza
    state.json (más fresco) sobre la DB.
    """
    pendiente_state = get_pendiente_feedback()

    rec = None
    rec_id: int | None = None
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

    await r_db.crear_recordatorio(tarea, hora_recordar, hora_seguimiento, fecha_tarea, meta_key=meta_key)

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


async def _manejar_gestion_meta(numero: str, gestion: dict) -> None:
    """Responde 'listar' al toque, o arma la confirmación para escribir una meta."""
    accion = gestion.get("accion")
    key = (gestion.get("key") or "").strip()
    descripcion = (gestion.get("descripcion") or "").strip()
    key_nueva = (gestion.get("key_nueva") or "").strip()
    fecha_objetivo = (gestion.get("fecha_objetivo") or "").strip() or None

    if accion == "listar":
        metas = await obtener_metas()
        if metas:
            lista = "\n".join(f"• {m['key']}: {m['descripcion']}" for m in metas)
            respuesta = f"Tus metas activas:\n{lista}"
        else:
            respuesta = "No tienes metas activas registradas."
        await m_db.guardar("assistant", respuesta, tipo="meta_listar")
        await enviar_mensaje(numero, respuesta)
        return

    # Acciones sobre una meta EXISTENTE: validar que exista.
    if accion in ("pausar", "activar", "lograr", "abandonar", "renombrar"):
        if not key or not await metas_db.existe(key):
            respuesta = (f"No encuentro una meta llamada «{key or '—'}». "
                         "¿Cuál de tus metas quieres cambiar?")
            await m_db.guardar("assistant", respuesta, tipo="meta_error")
            await enviar_mensaje(numero, respuesta)
            return

    if accion == "agregar" and not key:
        respuesta = "¿Qué nombre corto le pongo a esa meta? (ej. Salud, Finanzas)"
        await m_db.guardar("assistant", respuesta, tipo="meta_error")
        await enviar_mensaje(numero, respuesta)
        return

    # Guardar la propuesta y pedir confirmación explícita antes de escribir.
    set_pendiente_meta(accion, key, descripcion, key_nueva or None, fecha_objetivo)
    plazo_txt = f" (plazo {fecha_objetivo})" if fecha_objetivo else ""
    resumen = {
        "agregar":   f"agrego la meta «{key}»" + (f": {descripcion}" if descripcion else "") + plazo_txt,
        "pausar":    f"pauso la meta «{key}» (no la borro)",
        "activar":   f"reactivo la meta «{key}»",
        "lograr":    f"marco «{key}» como lograda 🎉",
        "abandonar": f"abandono la meta «{key}» (queda archivada, no se borra)",
        "renombrar": (f"renombro «{key}»" + (f" a «{key_nueva}»" if key_nueva else "")
                      + (f" / {descripcion}" if descripcion else "") + plazo_txt),
    }.get(accion, f"aplico «{accion}» sobre «{key}»")
    respuesta = f"¿Confirmo? {resumen}. Responde *sí* o *no*."
    await m_db.guardar("assistant", respuesta, tipo="meta_confirmacion")
    await enviar_mensaje(numero, respuesta)


async def _confirmar_gestion_meta(numero: str, aplicar: bool) -> None:
    """Aplica (o cancela) la gestión de meta que quedó pendiente de confirmación."""
    pendiente = get_pendiente_meta()
    clear_pendiente_meta()
    if not pendiente:
        return
    if not aplicar:
        respuesta = "Ok, no cambio nada."
        await m_db.guardar("assistant", respuesta, tipo="meta_cancelada")
        await enviar_mensaje(numero, respuesta)
        return

    accion = pendiente["accion"]
    key = pendiente.get("key")
    descripcion = pendiente.get("descripcion")
    key_nueva = pendiente.get("key_nueva")
    fecha_objetivo = pendiente.get("fecha_objetivo")
    try:
        if accion == "agregar":
            await metas_db.upsert(key, descripcion or key, estado="activa",
                                  fecha_objetivo=fecha_objetivo)
            plazo = f" (plazo {fecha_objetivo})" if fecha_objetivo else ""
            msg = f"✅ Meta «{key}» agregada{plazo}. Ya la tomo en cuenta desde ahora."
        elif accion == "pausar":
            await metas_db.cambiar_estado(key, "pausada")
            msg = f"✅ «{key}» en pausa."
        elif accion == "activar":
            await metas_db.cambiar_estado(key, "activa")
            msg = f"✅ «{key}» reactivada."
        elif accion == "lograr":
            await metas_db.cambiar_estado(key, "lograda")
            msg = f"✅ «{key}» marcada como lograda. 🎉"
        elif accion == "abandonar":
            await metas_db.cambiar_estado(key, "abandonada")
            msg = f"✅ «{key}» archivada (abandonada, no se borra)."
        elif accion == "renombrar":
            nueva = key_nueva or key
            desc = descripcion or key
            await metas_db.upsert(nueva, desc, estado="activa",
                                  fecha_objetivo=fecha_objetivo)
            if key_nueva and key_nueva != key:
                await metas_db.cambiar_estado(key, "abandonada")
            msg = f"✅ Meta actualizada: «{nueva}»."
        else:
            msg = "No pude aplicar ese cambio."
    except Exception as e:
        log.error(f"[META] error aplicando gestión: {e}")
        msg = "Tuve un problema guardando el cambio. Inténtalo de nuevo en un momento."
    await m_db.guardar("assistant", msg, tipo="meta_aplicada")
    await enviar_mensaje(numero, msg)
