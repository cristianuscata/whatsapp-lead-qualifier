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
        meta_key         text default null,    -- 'Networking' | 'BienesRaices' | 'Tecnologia' | 'Azure' | 'Maestría' | 'MVP' | null
        created_at       timestamptz default now()
    );

Migración para agregar meta_key a una tabla existente:

    alter table recordatorios add column if not exists meta_key text default null;

Semántica de los flags:
- avisado=false      → todavía no se envió el aviso de "5 min antes".
- avisado=true       → ya se envió.
- cumplido=null      → todavía no preguntamos ni recibimos feedback.
- cumplido=true      → Cristian confirmó que cumplió.
- cumplido=false     → respondió que no o a medias.
- reprogramado=true  → ya se trató (no reprogramar de nuevo en el cierre del día).
- meta_key=...       → tarea ligada a una de las metas activas (ver prompts.METAS_ACTIVAS).
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
    meta_key: str | None = None,
) -> dict | None:
    db = await _get_cliente()
    fila = {
        "tarea":            tarea,
        "hora_recordar":    hora_recordar.strftime("%H:%M:%S"),
        "hora_seguimiento": hora_seguimiento.strftime("%H:%M:%S"),
        "fecha":            fecha.isoformat(),
    }
    if meta_key:
        fila["meta_key"] = meta_key
    resultado = await db.table("recordatorios").insert(fila).execute()
    return resultado.data[0] if resultado.data else None


async def conteo_tareas_por_meta(desde_fecha: date) -> dict[str, dict[str, int]]:
    """
    Devuelve {meta_key: {"total": N, "cumplidas": M}} para tareas con fecha >= desde_fecha.
    Solo incluye tareas con meta_key no-null.
    """
    db = await _get_cliente()
    resultado = await (
        db.table("recordatorios")
        .select("meta_key, cumplido")
        .gte("fecha", desde_fecha.isoformat())
        .not_.is_("meta_key", "null")
        .execute()
    )
    conteo: dict[str, dict[str, int]] = {}
    for fila in resultado.data or []:
        key = fila["meta_key"]
        bucket = conteo.setdefault(key, {"total": 0, "cumplidas": 0})
        bucket["total"] += 1
        if fila.get("cumplido") is True:
            bucket["cumplidas"] += 1
    return conteo


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


async def eliminar_reprogramaciones_futuras(tarea: str, desde_fecha: date) -> int:
    """
    Borra recordatorios futuros de la misma tarea que aún no fueron avisados.
    Se llama cuando Cristian confirma tarde que sí cumplió: el cierre del día
    anterior ya creó una copia reprogramada para hoy/mañana, hay que removerla
    para no preguntar de nuevo.
    Devuelve la cantidad de filas borradas.
    """
    db = await _get_cliente()
    resultado = await (
        db.table("recordatorios")
        .delete()
        .eq("tarea", tarea)
        .eq("avisado", False)
        .is_("cumplido", "null")
        .gt("fecha", desde_fecha.isoformat())
        .execute()
    )
    return len(resultado.data or [])


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


async def consultar_por_estado(estado: str = "", limite: int = 30) -> list[dict]:
    """Recordatorios por estado derivado (SOLO LECTURA), para el agente MCP.

    - pendiente: cumplido is null y fecha >= hoy
    - cumplido:  cumplido = true
    - vencido:   cumplido is null y fecha < hoy
    - (vacío):   fecha >= hoy (agenda vigente)
    Devuelve hasta `limite` filas, más recientes primero. `hoy` en zona Lima.
    """
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    hoy = _dt.now(ZoneInfo("America/Lima")).date().isoformat()

    db = await _get_cliente()
    q = db.table("recordatorios").select("*")
    estado = (estado or "").strip().lower()
    if estado == "cumplido":
        q = q.eq("cumplido", True)
    elif estado == "pendiente":
        q = q.is_("cumplido", "null").gte("fecha", hoy)
    elif estado == "vencido":
        q = q.is_("cumplido", "null").lt("fecha", hoy)
    else:
        q = q.gte("fecha", hoy)
    resultado = await q.order("fecha", desc=True).limit(limite).execute()
    return resultado.data or []
