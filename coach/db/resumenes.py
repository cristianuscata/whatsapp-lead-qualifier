"""
Tabla `coach_resumenes` — resúmenes semanales del historial de conversación.

Permite que el coach "recuerde" conversaciones de meses atrás sin pagar el
costo de tokens de cargar miles de mensajes en cada turno. El job sábado 22:00
genera el resumen de los últimos 7 días, lo guarda acá, y el system prompt del
chat libre inyecta los 3 resúmenes más recientes.

Migración Supabase (ejecutar en SQL Editor):

    create table coach_resumenes (
        id          bigint generated always as identity primary key,
        desde       date not null,
        hasta       date not null,
        contenido   text not null,
        created_at  timestamptz default now()
    );
    create index if not exists coach_resumenes_hasta_idx on coach_resumenes (hasta desc);
"""

import os
from datetime import date
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


async def guardar(desde: date, hasta: date, contenido: str) -> None:
    db = await _get_cliente()
    await db.table("coach_resumenes").insert({
        "desde":     desde.isoformat(),
        "hasta":     hasta.isoformat(),
        "contenido": contenido,
    }).execute()


async def ultimos(n: int = 3) -> list[dict]:
    """Devuelve los N resúmenes más recientes, del más antiguo al más nuevo."""
    db = await _get_cliente()
    resultado = await (
        db.table("coach_resumenes")
        .select("desde, hasta, contenido")
        .order("hasta", desc=True)
        .limit(n)
        .execute()
    )
    filas = list(reversed(resultado.data or []))
    return filas


async def existe_para_semana(hasta: date) -> bool:
    """Idempotencia: evita generar el mismo resumen dos veces si el job se dispara doble."""
    db = await _get_cliente()
    resultado = await (
        db.table("coach_resumenes")
        .select("id")
        .eq("hasta", hasta.isoformat())
        .limit(1)
        .execute()
    )
    return bool(resultado.data)
