"""
WhatsApp Personal Coach — entrypoint.

Solo procesa mensajes que vienen de CRISTIAN_PHONE. Cualquier otro número
se ignora silenciosamente (este branch es un coach privado, no un agente
multi-usuario).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from dotenv import load_dotenv

from coach.main import es_cristian, iniciar_coach
from coach.agent.coach import coach_handle_message

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sched = iniciar_coach()
    yield
    if sched:
        sched.shutdown()


app = FastAPI(title="WhatsApp Personal Coach", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    """EvolutionAPI llama aquí cada vez que llega un mensaje de WhatsApp."""
    payload = await request.json()

    if payload.get("event") != "messages.upsert":
        return {"status": "ignorado"}

    data = payload["data"]
    if data["key"]["fromMe"]:
        return {"status": "ignorado"}

    numero = data["key"]["remoteJid"]
    texto  = data.get("message", {}).get("conversation", "")

    if not texto:
        return {"status": "sin texto"}

    if not es_cristian(numero):
        log.info(f"Mensaje ignorado (remitente no autorizado): {numero}")
        return {"status": "no autorizado"}

    try:
        await coach_handle_message(numero, texto)
    except Exception as e:
        log.error(f"[COACH] error procesando mensaje: {e}")

    return {"status": "ok"}
