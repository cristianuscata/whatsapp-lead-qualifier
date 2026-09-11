"""Versión unificada para el despliegue OPCIONAL en Vercel (guía, sección 8).

Une backend + servidor MCP en una sola app FastAPI: monta el MCP como
subaplicación en /api/mcp. Uso exclusivo del despliegue; para desarrollo
local sigue usando api/chat.py y api/mcp.py por separado (dos terminales).

Si intentas Vercel: deja en api/ solo este archivo (mueve chat.py y mcp.py a
local/), y configura MCP_URL = https://<tu-dominio>.vercel.app/api/mcp
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from mcp_server import mcp
from agent import responder

ROOT = Path(__file__).resolve().parent.parent

# path="/": deja la ruta interna de FastMCP relativa a donde la montemos.
mcp_asgi = mcp.http_app(path="/", stateless_http=True)

# FastMCP administra su propio ciclo de vida (lifespan): se lo pasamos a la
# app principal para que arranque y cierre correctamente.
app = FastAPI(title="MVP Coach de alto rendimiento", lifespan=mcp_asgi.lifespan)
app.mount("/api/mcp", mcp_asgi)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class Pregunta(BaseModel):
    pregunta: str


@app.get("/")
async def index():
    return FileResponse(ROOT / "index.html")


@app.post("/api/chat")
async def chat(payload: Pregunta):
    try:
        respuesta = await responder(payload.pregunta)
        return {"ok": True, "respuesta": respuesta}
    except Exception as error:
        return {
            "ok": False,
            "error": "No fue posible completar la consulta.",
            "detalle": str(error),
        }
