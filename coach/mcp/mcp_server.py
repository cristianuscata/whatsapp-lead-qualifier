"""Servidor MCP del coach de alto rendimiento (tools de SOLO LECTURA).

Formaliza como herramientas MCP la consulta del estado del usuario —metas y
recordatorios— sobre la MISMA fuente de verdad del v1 (Supabase). El agente
(coach/agent/agente_mcp.py) las descubre por el protocolo MCP y las usa para
responder el chat libre con datos reales, sin inventar.

Se sirve por HTTP en coach/mcp/mcp_app.py (contenedor `mcp`, puerto interno 8002).

Reutiliza:
- coach.agent.prompts.METAS_ACTIVAS  (las 6 metas de largo plazo)
- coach.db.recordatorios             (cliente Supabase async ya existente)

Límite: SOLO LECTURA. No crea, modifica ni borra; no expone información laboral
ni de terceros. La creación de recordatorios sigue en la rama determinista del v1.
"""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

from coach.db import recordatorios as r_db
from coach.db import metas as metas_db

mcp = FastMCP("Coach de alto rendimiento — metas y recordatorios")

TZ_LIMA = ZoneInfo("America/Lima")


@mcp.tool
async def consultar_metas(meta: str = "") -> dict:
    """Consulta el avance de las metas de largo plazo del usuario.

    Úsala cuando pregunte cómo va con una meta o quiera un panorama de todas
    (ej: "¿cómo voy con Networking?", "¿qué metas tengo?"). Si `meta` viene vacía,
    devuelve todas; si trae una clave (Networking, BienesRaices, Tecnologia, Azure, Maestría, MVP)
    o parte de su descripción, devuelve esa. El avance sale de las tareas reales
    registradas en los últimos 90 días. Es de SOLO LECTURA.
    """
    hoy = date.today()
    try:
        conteo = await r_db.conteo_tareas_por_meta(hoy - timedelta(days=90))
        metas = await metas_db.obtener_metas()
    except Exception as e:
        return {"ok": False, "error": f"No se pudo leer metas o avance: {e}"}

    filtro = (meta or "").strip().lower()
    filas = []
    for m in metas:
        if filtro and filtro != m["key"].lower() and filtro not in m["descripcion"].lower():
            continue
        b = conteo.get(m["key"], {"total": 0, "cumplidas": 0})
        total, cumplidas = b["total"], b["cumplidas"]
        avance = round(100 * cumplidas / total) if total else 0
        fila = {
            "meta": m["key"],
            "descripcion": m["descripcion"],
            "tareas_totales": total,
            "tareas_cumplidas": cumplidas,
            "avance_pct": avance,
        }
        # Plazo: días restantes / vencida, si la meta tiene fecha objetivo.
        fobj = m.get("fecha_objetivo")
        if fobj:
            try:
                dias = (date.fromisoformat(str(fobj)) - hoy).days
                fila["fecha_objetivo"] = str(fobj)
                fila["dias_restantes"] = dias
                fila["vencida"] = dias < 0
            except ValueError:
                pass
        filas.append(fila)

    if filtro and not filas:
        return {
            "ok": True, "consulta": filtro, "cantidad_registros": 0, "metas": [],
            "nota": "No hay una meta con ese nombre; no hay evidencia para responder.",
        }
    return {
        "ok": True,
        "consulta": filtro or "todas",
        "cantidad_registros": len(filas),
        "metas": filas,
        "ventana": "tareas de los últimos 90 días",
        "fuente": "Supabase · recordatorios + METAS_ACTIVAS",
    }


@mcp.tool
async def consultar_recordatorios(estado: str = "") -> dict:
    """Consulta los recordatorios del usuario, opcionalmente por estado.

    Úsala cuando pregunte qué tiene pendiente, qué cumplió o qué se le venció
    (ej: "¿qué tengo pendiente?", "¿qué recordatorios vencí?"). `estado` acepta:
    "pendiente", "cumplido", "vencido", o vacío para todos los de hoy en adelante.
    Es de SOLO LECTURA: no crea ni modifica recordatorios.
    """
    estado_norm = (estado or "").strip().lower()
    if estado_norm and estado_norm not in {"pendiente", "cumplido", "vencido"}:
        return {
            "ok": False,
            "error": (f"Estado inválido '{estado_norm}'. Usa: pendiente, cumplido, "
                      "vencido, o déjalo vacío."),
        }
    try:
        filas = await r_db.consultar_por_estado(estado_norm)
    except Exception as e:
        return {"ok": False, "error": f"No se pudieron leer los recordatorios: {e}"}

    return {
        "ok": True,
        "estado_consultado": estado_norm or "todos",
        "cantidad_registros": len(filas),
        "recordatorios": [
            {
                "tarea": f.get("tarea"),
                "fecha": f.get("fecha"),
                "hora": (f.get("hora_recordar") or "")[:5],
                "cumplido": f.get("cumplido"),
                "meta": f.get("meta_key"),
            }
            for f in filas
        ],
        "fuente": "Supabase · recordatorios",
    }
