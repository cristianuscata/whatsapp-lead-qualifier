"""Detecta si un mensaje pide GESTIONAR una meta (agregar/pausar/abandonar/...).

Espejo de coach/agent/intent.py, pero para la administración de metas por
lenguaje natural. Un pre-filtro barato evita llamar al LLM en cada mensaje.
La ESCRITURA no ocurre aquí: coach.py pide confirmación antes de persistir.
"""
import os
import json
import logging

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Pre-filtro: solo llamamos al LLM si el texto trae señales de gestión de metas.
_SENALES = (
    "meta", "metas", "objetivo", "objetivos",
    "agrega", "agregar", "añade", "anade", "añadir", "anadir", "nueva meta",
    "pausa", "pausar", "quita", "quitar", "elimina", "eliminar", "abandon",
    "reactiva", "reactivar", "renombra", "renombrar", "cambia el nombre",
    "logré", "logre", "logré la meta", "ya cumplí la meta",
)

META_INTENT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "meta_management",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "es_gestion_meta": {"type": "boolean"},
                "accion": {
                    "type": ["string", "null"],
                    "enum": ["agregar", "pausar", "activar", "lograr",
                             "abandonar", "renombrar", "listar", None],
                },
                "key": {"type": ["string", "null"],
                        "description": "Clave de la meta (existente, o una corta nueva para 'agregar')."},
                "descripcion": {"type": ["string", "null"]},
                "key_nueva": {"type": ["string", "null"],
                              "description": "Solo para 'renombrar': nueva clave."},
                "fecha_objetivo": {"type": ["string", "null"],
                                   "description": "Fecha límite YYYY-MM-DD si el usuario la menciona (p.ej. 'para julio 2026'), o null."},
            },
            "required": ["es_gestion_meta", "accion", "key", "descripcion", "key_nueva", "fecha_objetivo"],
        },
    },
}


def _hay_senal(texto: str) -> bool:
    t = texto.lower()
    return any(s in t for s in _SENALES)


async def detectar_gestion_meta(mensaje: str, keys_existentes: list[str]) -> dict | None:
    """Devuelve {accion, key, descripcion, key_nueva} si el mensaje gestiona una
    meta, o None si no aplica. Tolerante a fallos.
    """
    if not _hay_senal(mensaje):
        return None

    from datetime import datetime
    from zoneinfo import ZoneInfo
    hoy_iso = datetime.now(ZoneInfo("America/Lima")).date().isoformat()

    keys = ", ".join(keys_existentes) or "(ninguna)"
    system_prompt = f"""Detectas si el usuario quiere GESTIONAR sus metas de largo plazo.

FECHA DE HOY: {hoy_iso} (para resolver fechas relativas).
Metas actuales (keys): {keys}.

Acciones posibles:
- agregar: crear una meta nueva. Devuelve una `key` corta y representativa sin
  espacios (ej. "Salud", "Finanzas"), una `descripcion` en una frase, y si el
  usuario menciona un plazo, `fecha_objetivo` en formato YYYY-MM-DD.
- pausar / activar / lograr / abandonar: sobre una meta EXISTENTE; devuelve su `key`.
- renombrar: devuelve `key` (actual) y `key_nueva` y/o `descripcion` (y `fecha_objetivo` si cambia el plazo).
- listar: el usuario quiere ver sus metas.

`fecha_objetivo`: resuélvela contra la FECHA DE HOY ("para julio 2026" → 2026-07-31;
"en 3 meses" → hoy + 3 meses). Si no menciona plazo, déjala null.

Si el mensaje NO es sobre gestionar metas (por ejemplo crear un recordatorio con
hora, preguntar cómo va con una meta, o charla normal), devuelve
es_gestion_meta=false y el resto en null. "¿cómo voy con X?" NO es gestión (es consulta)."""

    try:
        resp = await client.chat.completions.create(
            model=os.getenv("COACH_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": mensaje},
            ],
            response_format=META_INTENT_SCHEMA,
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception as e:
        log.warning(f"[META] detección de gestión de meta falló: {e}")
        return None

    if not data.get("es_gestion_meta") or not data.get("accion"):
        return None
    return data
