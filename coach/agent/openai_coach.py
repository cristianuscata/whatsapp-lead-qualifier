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
    system_prompt = get_system_coach(metas_text(metas))
    if memoria_str:
        system_prompt += f"\n\n{memoria_str}"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historial)
    messages.append({"role": "user", "content": mensaje})

    resp = await client.chat.completions.create(
        model=os.getenv("COACH_MODEL", "gpt-4o-mini"),
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
        model=os.getenv("COACH_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": get_system_coach(metas_text(metas))},
            {"role": "user",   "content": instruccion},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()
