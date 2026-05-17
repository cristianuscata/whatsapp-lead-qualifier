"""
CRUD de la tabla `recordatorios` del coach personal.

Tabla esperada (ejecutar en SQL Editor de Supabase):

    create table recordatorios (
        id               bigint generated always as identity primary key,
        tarea            text not null,
        hora_recordar    time not null,
        hora_seguimiento time not null,
        fecha            date not null,
        avisado          boolean default false,
        cumplido         boolean default null,
        reprogramado     boolean default false,
        created_at       timestamptz default now()
    );

Semántica de los flags:
- avisado=false      → todavía no se envió el aviso de "5 min antes".
- avisado=true       → ya se envió.
- cumplido=null      → todavía no preguntamos ni recibimos feedback.
- cumplido=true      → Cristian confirmó que cumplió.
- cumplido=false     → respondió que no o a medias.
- reprogramado=true  → ya se trató (no reprogramar de nuevo en el cierre del día).
"""

import os
from datetime import date, time
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


async def crear_recordatorio(
    tarea: str,
    hora_recordar: time,
    hora_seguimiento: time,
    fecha: date,
) -> dict | None:
    db = await _get_cliente()
    resultado = await db.table("recordatorios").insert({
        "tarea":            tarea,
        "hora_recordar":    hora_recordar.strftime("%H:%M:%S"),
        "hora_seguimiento": hora_seguimiento.strftime("%H:%M:%S"),
        "fecha":            fecha.isoformat(),
    }).execute()
    return resultado.data[0] if resultado.data else None


async def pendientes_aviso(fecha: date, ahora: time) -> list[dict]:
    """Recordatorios cuya hora_recordar ya llegó y no han sido avisados."""
    db = await _get_cliente()
    resultado = await (
        db.table("recordatorios")
        .select("*")
        .eq("fecha", fecha.isoformat())
        .eq("avisado", False)
        .lte("hora_recordar", ahora.strftime("%H:%M:%S"))
        .execute()
    )
    return resultado.data or []


async def pendientes_seguimiento(fecha: date, ahora: time) -> list[dict]:
    """
    Recordatorios cuya hora_seguimiento ya pasó y siguen sin feedback
    (cumplido is null). El scheduler usa además un set en memoria para
    no repreguntar cada minuto.
    """
    db = await _get_cliente()
    resultado = await (
        db.table("recordatorios")
        .select("*")
        .eq("fecha", fecha.isoformat())
        .eq("avisado", True)
        .is_("cumplido", "null")
        .lte("hora_seguimiento", ahora.strftime("%H:%M:%S"))
        .execute()
    )
    return resultado.data or []


async def marcar_avisado(recordatorio_id: int) -> None:
    db = await _get_cliente()
    await db.table("recordatorios").update({"avisado": True}).eq("id", recordatorio_id).execute()


async def marcar_cumplido(recordatorio_id: int, cumplido: bool) -> None:
    db = await _get_cliente()
    await db.table("recordatorios").update({"cumplido": cumplido}).eq("id", recordatorio_id).execute()


async def marcar_reprogramado(recordatorio_id: int) -> None:
    db = await _get_cliente()
    await db.table("recordatorios").update({"reprogramado": True}).eq("id", recordatorio_id).execute()


async def tareas_del_dia(fecha: date) -> list[dict]:
    db = await _get_cliente()
    resultado = await (
        db.table("recordatorios")
        .select("*")
        .eq("fecha", fecha.isoformat())
        .order("hora_recordar", desc=False)
        .execute()
    )
    return resultado.data or []


async def ultimo_pendiente_seguimiento() -> dict | None:
    """
    Recordatorio más reciente que esperaba respuesta y aún no tiene cumplido.
    Heurística: cuando Cristian responde "sí/no/a medias", lo asociamos al
    último seguimiento que se le preguntó.
    """
    db = await _get_cliente()
    resultado = await (
        db.table("recordatorios")
        .select("*")
        .eq("avisado", True)
        .is_("cumplido", "null")
        .order("hora_seguimiento", desc=True)
        .limit(1)
        .execute()
    )
    filas = resultado.data or []
    return filas[0] if filas else None
