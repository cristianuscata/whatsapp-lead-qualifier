"""CRUD de la tabla `metas` — fuente única de metas, editable desde WhatsApp.

Reemplaza la constante METAS_ACTIVAS de coach/agent/prompts.py, que queda solo
como semilla/fallback. `obtener_metas()` cachea ~60s y cae a la constante si la
tabla está vacía o Supabase falla, para que el coach nunca se quede sin metas.

Estados: activa | pausada | lograda | abandonada. "Quitar" una meta = pasarla a
'abandonada' (soft-delete, se conserva el historial).
"""
import os
import time
import logging

from supabase import acreate_client, AsyncClient
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

ESTADOS_VALIDOS = {"activa", "pausada", "lograda", "abandonada"}

_cliente: AsyncClient | None = None
_cache: list[dict] | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 60.0


async def _get_cliente() -> AsyncClient:
    global _cliente
    if _cliente is None:
        _cliente = await acreate_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )
    return _cliente


async def listar(incluir_no_activas: bool = False) -> list[dict]:
    db = await _get_cliente()
    q = db.table("metas").select("*").order("prioridad", desc=False)
    if not incluir_no_activas:
        q = q.eq("estado", "activa")
    resultado = await q.execute()
    return resultado.data or []


async def existe(key: str) -> bool:
    db = await _get_cliente()
    resultado = await db.table("metas").select("key").eq("key", key).execute()
    return bool(resultado.data)


async def upsert(key: str, descripcion: str, estado: str = "activa",
                 prioridad: int = 3, fecha_objetivo=None) -> dict | None:
    db = await _get_cliente()
    fila = {"key": key, "descripcion": descripcion,
            "estado": estado, "prioridad": prioridad}
    if fecha_objetivo:
        fila["fecha_objetivo"] = (fecha_objetivo.isoformat()
                                  if hasattr(fecha_objetivo, "isoformat") else fecha_objetivo)
    resultado = await db.table("metas").upsert(fila).execute()
    invalidar_cache()
    return resultado.data[0] if resultado.data else None


async def cambiar_estado(key: str, estado: str) -> None:
    db = await _get_cliente()
    await db.table("metas").update({"estado": estado}).eq("key", key).execute()
    invalidar_cache()


def invalidar_cache() -> None:
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0.0


async def obtener_metas(incluir_no_activas: bool = False) -> list[dict]:
    """Metas vigentes, con cache TTL (~60s) y fallback a METAS_ACTIVAS.

    Si la tabla está vacía o Supabase falla, devuelve la constante para que el
    coach nunca se quede sin metas.
    """
    global _cache, _cache_ts
    ahora = time.monotonic()
    if (not incluir_no_activas and _cache is not None
            and (ahora - _cache_ts) < _CACHE_TTL):
        return _cache

    try:
        filas = await listar(incluir_no_activas=incluir_no_activas)
    except Exception as e:
        log.warning(f"[METAS] no se pudo leer la tabla, uso fallback: {e}")
        filas = []

    if not filas:
        from coach.agent.prompts import METAS_ACTIVAS
        filas = [dict(m) for m in METAS_ACTIVAS]  # fallback (solo key + descripcion)

    if not incluir_no_activas:
        _cache = filas
        _cache_ts = ahora
    return filas


def metas_text(metas: list[dict]) -> str:
    """Lista de metas en bullets para inyectar en un prompt."""
    return "\n".join(f"- {m['descripcion']}" for m in metas)
