"""Backend del MVP: sirve la interfaz y expone /api/chat.

Ejecuta: uvicorn api.chat:app --reload --port 8000
Abre:    http://127.0.0.1:8000

Requiere que api/mcp.py esté corriendo en otra terminal (puerto 8001) — ver README.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import responder

ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title="MVP Coach de alto rendimiento — metas y recordatorios")
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
            "error": "No fue posible completar la consulta. Revisa el servidor MCP y la configuración.",
            "detalle": str(error),
        }
