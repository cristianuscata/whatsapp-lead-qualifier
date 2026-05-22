"""
Historial de conversación del coach.

Tabla esperada:

    create table coach_mensajes (
        id          bigint generated always as identity primary key,
        role        text not null check (role in ('user', 'assistant')),
        content     text not null,
        tipo        text default 'chat',
        created_at  timestamptz default now()
    );

`tipo` permite distinguir chat libre de mensajes proactivos (arranque, aviso,
seguimiento, cierre, etc.) para análisis posterior.
"""

import os
from supabase import acreate_client, AsyncClient
from dotenv import load_dotenv

load_dotenv()

_cliente: AsyncClient | None = None


async def _get_cliente() -> AsyncClient:
    global _cliente
    if _cliente is None:
        _cliente = await acreate_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )
    return _cliente


async def guardar(role: str, content: str, tipo: str = "chat") -> None:
    db = await _get_cliente()
    await db.table("coach_mensajes").insert({
        "role":    role,
        "content": content,
        "tipo":    tipo,
    }).execute()


async def mensajes_recientes(dias: int = 14) -> list[dict]:
    """
    Devuelve TODOS los mensajes (user + assistant) de los últimos N días.
    Usado por la revisión semanal para detectar qué metas se mencionaron poco.
    """
    from datetime import datetime, timedelta, timezone
    db = await _get_cliente()
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    resultado = await (
        db.table("coach_mensajes")
        .select("role, content, created_at")
        .gte("created_at", desde)
        .order("created_at", desc=False)
        .execute()
    )
    return resultado.data or []


async def historial(limite: int = 10) -> list[dict]:
    """Devuelve los últimos N mensajes en orden cronológico (formato OpenAI)."""
    db = await _get_cliente()
    resultado = await (
        db.table("coach_mensajes")
        .select("role, content")
        .order("created_at", desc=True)
        .limit(limite)
        .execute()
    )
    filas = list(reversed(resultado.data or []))
    return [{"role": f["role"], "content": f["content"]} for f in filas]
