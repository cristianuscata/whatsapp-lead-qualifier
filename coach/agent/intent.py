"""Detecta si un mensaje contiene una intención de tarea con hora."""

import os
import json
import logging
from datetime import time as dtime

from openai import AsyncOpenAI
from dotenv import load_dotenv

from coach.agent.prompts import SYSTEM_INTENT, INTENT_SCHEMA

load_dotenv()
log = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def detectar_recordatorio(mensaje: str) -> dict | None:
    """
    Devuelve {"tarea": str, "hora": time} si detecta intención, o None.
    Tolerante a fallos: ante cualquier error devuelve None y loguea.
    """
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_INTENT},
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
    if not tarea or not hora_str:
        return None

    try:
        hh, mm = map(int, hora_str.split(":"))
        hora = dtime(hour=hh, minute=mm)
    except (ValueError, AttributeError):
        log.warning(f"[COACH] hora inválida del intent: {hora_str!r}")
        return None

    return {"tarea": tarea, "hora": hora}
