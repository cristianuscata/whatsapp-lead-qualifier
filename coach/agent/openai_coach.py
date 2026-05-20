"""Cliente OpenAI del coach personal (chat libre y mensajes proactivos)."""

import os
import logging
from openai import AsyncOpenAI
from dotenv import load_dotenv

from coach.agent.prompts import get_system_coach

load_dotenv()
log = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def responder_chat(mensaje: str, historial: list[dict]) -> str:
    """Genera una respuesta del coach al chat libre de Cristian."""
    # Obtener eventos de Google Calendar para hoy
    try:
        from coach.integrations.calendar import listar_eventos
        from datetime import datetime
        from zoneinfo import ZoneInfo
        hoy = datetime.now(ZoneInfo("America/Lima")).date()
        eventos = listar_eventos(hoy)
    except Exception as e:
        log.warning(f"[OPENAI_COACH] no se pudo listar eventos del calendario para inyectar al chat: {e}")
        eventos = []

    if eventos:
        eventos_lineas = [f"- {ev['hora_inicio']} - {ev['hora_fin']}: {ev['summary']}" for ev in eventos]
        eventos_str = "EVENTOS EN TU GOOGLE CALENDAR HOY:\n" + "\n".join(eventos_lineas)
    else:
        eventos_str = "EVENTOS EN TU GOOGLE CALENDAR HOY:\n(No hay eventos registrados para hoy)"

    system_prompt = f"{get_system_coach()}\n\n{eventos_str}"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historial)
    messages.append({"role": "user", "content": mensaje})

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


async def generar_mensaje(instruccion: str) -> str:
    """
    Genera un mensaje proactivo (arranque, cierre, celebración, confrontación)
    siguiendo el system prompt del coach y una instrucción puntual.
    """
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": get_system_coach()},
            {"role": "user",   "content": instruccion},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()
