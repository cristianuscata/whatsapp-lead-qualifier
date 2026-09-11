"""Herramientas del dominio del Coach de alto rendimiento, expuestas como servidor MCP.

Capacidad migrada desde el PoC (sesión 5): el coach llevaba el estado de las
metas de largo plazo y los recordatorios del usuario. Aquí formalizamos la
CONSULTA de ese estado como dos tools MCP de SOLO LECTURA, con datos
sintéticos, para dar accountability ("¿cómo voy con mis metas?", "¿qué tengo
pendiente?").

Este archivo NO se ejecuta directamente: api/mcp.py lo sirve en local
(uvicorn api.mcp:app --port 8001) y api/index.py lo monta dentro de la app
principal si se intenta el despliegue opcional en Vercel.

Fuente de verdad: data/metas_demo.csv y data/recordatorios_demo.csv
(sintéticos; no representan datos productivos).
Límite: solo lectura. No crea, modifica ni borra; no expone información
laboral ni de terceros.
"""
from pathlib import Path
import csv

from fastmcp import FastMCP

mcp = FastMCP("Coach de alto rendimiento — consulta de metas y recordatorios")

DATA_DIR = Path(__file__).resolve().parent / "data"
METAS_FILE = DATA_DIR / "metas_demo.csv"
RECORDATORIOS_FILE = DATA_DIR / "recordatorios_demo.csv"

ESTADOS_RECORDATORIO = {"pendiente", "cumplido", "vencido"}


def _leer_csv(path: Path):
    """Lee un CSV a lista de dicts, o None si la fuente no existe."""
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


# --- Lógica pura (sin MCP) para poder probarla de forma reproducible ---

def buscar_metas(meta: str = "") -> dict:
    filas = _leer_csv(METAS_FILE)
    if filas is None:
        return {"ok": False, "error": "La fuente de metas no está disponible."}

    meta = (meta or "").strip().lower()
    if not meta:
        resumen = [
            {
                "meta": f["key"],
                "descripcion": f["descripcion"],
                "estado": f["estado"],
                "fecha_objetivo": f["fecha_objetivo"],
                "avance": f"{f['tareas_cumplidas']}/{f['tareas_totales']} tareas",
            }
            for f in filas
        ]
        return {
            "ok": True,
            "consulta": "todas",
            "cantidad_registros": len(resumen),
            "metas": resumen,
            "fuente": METAS_FILE.name,
            "advertencia": "Datos de demostración; no representan una fuente productiva.",
        }

    encontrada = [
        f for f in filas
        if f["key"].lower() == meta or meta in f["descripcion"].lower()
    ]
    if not encontrada:
        return {
            "ok": True,
            "consulta": meta,
            "cantidad_registros": 0,
            "metas": [],
            "fuente": METAS_FILE.name,
            "advertencia": "No se encontró ninguna meta con ese nombre; no hay evidencia para responder.",
        }

    f = encontrada[0]
    total = int(f["tareas_totales"])
    cumplidas = int(f["tareas_cumplidas"])
    avance = round(100 * cumplidas / total) if total else 0
    return {
        "ok": True,
        "consulta": meta,
        "cantidad_registros": len(encontrada),
        "meta": {
            "clave": f["key"],
            "descripcion": f["descripcion"],
            "estado": f["estado"],
            "fecha_objetivo": f["fecha_objetivo"],
            "prioridad": int(f["prioridad"]),
            "tareas_totales": total,
            "tareas_cumplidas": cumplidas,
            "avance_pct": avance,
        },
        "fuente": METAS_FILE.name,
        "advertencia": "Datos de demostración; no representan una fuente productiva.",
    }


def buscar_recordatorios(estado: str = "") -> dict:
    filas = _leer_csv(RECORDATORIOS_FILE)
    if filas is None:
        return {"ok": False, "error": "La fuente de recordatorios no está disponible."}

    estado = (estado or "").strip().lower()
    if estado and estado not in ESTADOS_RECORDATORIO:
        return {
            "ok": False,
            "error": (
                f"Estado inválido '{estado}'. Usa uno de: "
                f"{', '.join(sorted(ESTADOS_RECORDATORIO))}, o déjalo vacío para todos."
            ),
        }

    seleccion = [f for f in filas if not estado or f["estado"].lower() == estado]
    return {
        "ok": True,
        "estado_consultado": estado or "todos",
        "cantidad_registros": len(seleccion),
        "recordatorios": [
            {
                "tarea": f["tarea"],
                "fecha": f["fecha"],
                "hora": f["hora"],
                "estado": f["estado"],
                "meta": f["meta_key"],
            }
            for f in seleccion[:20]
        ],
        "fuente": RECORDATORIOS_FILE.name,
        "advertencia": "Datos de demostración; no representan una fuente productiva.",
    }


# --- Tools MCP: contratos que el agente descubre y decide usar ---

@mcp.tool
def consultar_metas(meta: str = "") -> dict:
    """Consulta el estado y avance de las metas de largo plazo del usuario.

    Úsala cuando la persona pregunte cómo va con una meta o quiera un
    panorama de todas sus metas (ej: "¿cómo voy con PTE?",
    "¿qué metas tengo activas?"). Si `meta` viene vacía, devuelve el
    resumen de TODAS las metas. Si viene con un nombre o clave (PTE,
    Azure, Maestría, MVP, Visa, Sydney), devuelve el detalle de esa meta:
    estado, fecha objetivo, prioridad y avance de tareas.

    Es de SOLO LECTURA: no crea, modifica ni elimina metas. Si la meta no
    existe, devuelve cantidad_registros = 0 (no la inventa).
    """
    return buscar_metas(meta)


@mcp.tool
def consultar_recordatorios(estado: str = "") -> dict:
    """Consulta los recordatorios del usuario, opcionalmente filtrados por estado.

    Úsala cuando la persona pregunte qué tiene pendiente, qué cumplió o qué
    se le venció (ej: "¿qué tengo pendiente?", "¿qué recordatorios vencí?").
    `estado` acepta: "pendiente", "cumplido", "vencido", o vacío para todos.
    Devuelve la lista con su fecha, hora, estado y meta asociada.

    Es de SOLO LECTURA: no crea ni modifica recordatorios. Un estado no
    válido devuelve un error claro sin romper la aplicación.
    """
    return buscar_recordatorios(estado)
