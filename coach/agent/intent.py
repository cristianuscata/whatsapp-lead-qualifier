"""Detecta si un mensaje contiene una intención de tarea con hora."""

import os
import json
import logging
from datetime import datetime, time as dtime, date as ddate
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from dotenv import load_dotenv

from coach.agent.prompts import (
    get_system_intent,
    INTENT_SCHEMA,
    SYSTEM_CALENDAR_QUERY,
    CALENDAR_QUERY_SCHEMA,
)
from coach.db.metas import obtener_metas

load_dotenv()
log = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def detectar_recordatorio(mensaje: str) -> dict | None:
    """
    Devuelve {"tarea": str, "hora": time, "fecha": date} si detecta intención, o None.
    Tolerante a fallos: ante cualquier error devuelve None y loguea.
    """
    try:
        ahora = datetime.now(ZoneInfo("America/Lima"))
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        fecha_ref_str = (f"{dias[ahora.weekday()]} {ahora.day} de {meses[ahora.month - 1]} "
                         f"de {ahora.year}, {ahora.strftime('%H:%M')} (Lima, Perú)")

        metas = await obtener_metas()
        system_prompt = get_system_intent(fecha_ref_str, metas)

        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": mensaje},
            ],
            response_format=INTENT_SCHEMA,
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception as e:
        log.warning(f"[COACH] intent detection falló: {e}")
        return None

    if not data.get("has_intent"):
        return None

    tarea = (data.get("tarea") or "").strip()
    hora_str = data.get("hora_hhmm") or ""
    fecha_str = data.get("fecha_yyyymmdd") or ""
    if not tarea or not hora_str:
        return None

    try:
        hh, mm = map(int, hora_str.split(":"))
        hora = dtime(hour=hh, minute=mm)
    except (ValueError, AttributeError):
        log.warning(f"[COACH] hora inválida del intent: {hora_str!r}")
        return None

    try:
        y, m, d = map(int, fecha_str.split("-"))
        fecha = ddate(year=y, month=m, day=d)
    except (ValueError, AttributeError):
        log.warning(f"[COACH] fecha inválida del intent: {fecha_str!r}, usando hoy")
        fecha = ahora.date()

    meta_key = data.get("meta_key")
    # Validar contra las metas vigentes (tabla) para no aceptar valores inventados
    keys_validas = {m["key"] for m in metas}
    if meta_key and meta_key not in keys_validas:
        log.warning(f"[COACH] meta_key inválida del intent: {meta_key!r}")
        meta_key = None

    return {"tarea": tarea, "hora": hora, "fecha": fecha, "meta_key": meta_key}


async def detectar_consulta_calendar(mensaje: str) -> str | None:
    """
    Detecta si el mensaje es una consulta al calendar.
    Devuelve "hoy", "manana", "ambos", o None si no es consulta.
    Tolerante a fallos: ante cualquier error devuelve None y loguea.
    """
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_CALENDAR_QUERY},
                {"role": "user",   "content": mensaje},
            ],
            response_format=CALENDAR_QUERY_SCHEMA,
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception as e:
        log.warning(f"[COACH] calendar-query detection falló: {e}")
        return None

    if not data.get("es_consulta_calendar"):
        return None

    alcance = data.get("alcance")
    if alcance not in ("hoy", "manana", "ambos"):
        return None
    return alcance
