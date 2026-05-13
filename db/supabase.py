"""
Historial de conversación en Supabase.

Tabla esperada (ejecuta esto en el SQL Editor de Supabase):

    create table mensajes (
        id         bigint generated always as identity primary key,
        numero     text not null,
        nombre     text,
        rol        text not null check (rol in ('user', 'assistant')),
        contenido  text not null,
        creado_en  timestamptz default now()
    );
"""

import os
from supabase import acreate_client, AsyncClient
from dotenv import load_dotenv

load_dotenv()

# Cliente Supabase (se inicializa la primera vez que se usa)
_cliente: AsyncClient | None = None


async def _get_cliente() -> AsyncClient:
    global _cliente
    if _cliente is None:
        _cliente = await acreate_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )
    return _cliente


async def guardar_mensaje(numero: str, nombre: str, rol: str, contenido: str):
    """Guarda un mensaje (del usuario o del asistente) en Supabase."""
    db = await _get_cliente()
    await db.table("mensajes").insert({
        "numero":    numero,
        "nombre":    nombre,
        "rol":       rol,
        "contenido": contenido,
    }).execute()


async def obtener_historial(numero: str, limite: int = 20) -> list:
    """
    Devuelve el historial de la conversación en el formato que espera Gemini:
        [{"role": "user"|"model", "parts": ["texto"]}, ...]
    """
    db = await _get_cliente()

    resultado = await (
        db.table("mensajes")
        .select("rol, contenido")
        .eq("numero", numero)
        .order("creado_en", desc=False)
        .limit(limite)
        .execute()
    )

    # OpenAI espera formato {"role": "user"|"assistant", "content": "mensaje"}
    historial = []
    for fila in resultado.data:
        historial.append({
            "role": fila["rol"],  # la base de datos ya guarda "user" o "assistant"
            "content": fila["contenido"]
        })

    return historial
