"""Cliente OpenAI del coach personal (chat libre y mensajes proactivos)."""

import os
import logging
from openai import AsyncOpenAI
from dotenv import load_dotenv

from coach.agent.prompts import get_system_coach
from coach.db.metas import obtener_metas, metas_text

load_dotenv()
log = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def responder_chat(mensaje: str, historial: list[dict]) -> str:
    """Genera una respuesta del coach al chat libre de Cristian."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    hoy = datetime.now(ZoneInfo("America/Lima")).date()
    manana = hoy + timedelta(days=1)

    # Obtener eventos de Google Calendar para hoy y mañana
    try:
        from coach.integrations.calendar import listar_eventos
        eventos_hoy = listar_eventos(hoy)
        eventos_manana = listar_eventos(manana)
    except Exception as e:
        log.warning(f"[OPENAI_COACH] no se pudo listar eventos del calendario para inyectar al chat: {e}")
        eventos_hoy = []
        eventos_manana = []

    def _fmt(eventos, fecha):
        if not eventos:
            return "(sin eventos)"
        return "\n".join(
            f"- [{fecha.isoformat()}] {ev['hora_inicio']}–{ev['hora_fin']}: {ev['summary']}"
            for ev in eventos
        )

    eventos_str = (
        f"EVENTOS EN TU GOOGLE CALENDAR HOY ({hoy.isoformat()}):\n{_fmt(eventos_hoy, hoy)}\n\n"
        f"EVENTOS EN TU GOOGLE CALENDAR MAÑANA ({manana.isoformat()}):\n{_fmt(eventos_manana, manana)}\n\n"
        "REGLA DURA: las fechas y horas de arriba son la única fuente de verdad. "
        "NO inventes fechas ni horas, NO menciones eventos que no estén en estas listas. "
        "Si el usuario pregunta por sus eventos/calendar/agenda del día o de mañana, "
        "DEBES listar TODOS los eventos de la lista correspondiente sin omitir ninguno, "
        "en el mismo orden y con la hora exacta. No resumas ni agrupes."
    )

    # Inyectar últimos 3 resúmenes semanales para memoria de largo plazo
    try:
        from coach.db import resumenes as res_db
        ultimos_resumenes = await res_db.ultimos(n=3)
    except Exception as e:
        log.warning(f"[OPENAI_COACH] no se pudieron cargar resúmenes semanales: {e}")
        ultimos_resumenes = []

    if ultimos_resumenes:
        bloques = []
        for r in ultimos_resumenes:
            bloques.append(
                f"--- Semana {r['desde']} al {r['hasta']} ---\n{r['contenido']}"
            )
        memoria_str = (
            "MEMORIA DE SEMANAS PREVIAS (úsala para hacer seguimiento real, "
            "menciona avances o retrocesos cuando aplique, NO inventes hechos que no estén acá):\n\n"
            + "\n\n".join(bloques)
        )
    else:
        memoria_str = ""

    metas = await obtener_metas()
    system_prompt = f"{get_system_coach(metas_text(metas))}\n\n{eventos_str}"
    if memoria_str:
        system_prompt += f"\n\n{memoria_str}"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historial)
    messages.append({"role": "user", "content": mensaje})

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


async def generar_mensaje(instruccion: str) -> str:
    """
    Genera un mensaje proactivo (arranque, cierre, celebración, confrontación)
    siguiendo el system prompt del coach y una instrucción puntual.
    """
    metas = await obtener_metas()
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": get_system_coach(metas_text(metas))},
            {"role": "user",   "content": instruccion},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()
