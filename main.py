import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from dotenv import load_dotenv

from agent.openai_agent import responder
from agent.classifier import clasificar
from agent.notifier import notificar_vendedor
from db.supabase import guardar_mensaje, obtener_historial
from whatsapp import enviar_mensaje
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


app = FastAPI(title="WhatsApp Agent", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    """
    EvolutionAPI llama aquí cada vez que llega un mensaje de WhatsApp.

    Routing:
        - Si viene de CRISTIAN_PHONE  → coach personal
        - Si viene de otro número     → agente de leads
    """
    payload = await request.json()

    evento = payload.get("event", "")
    if evento != "messages.upsert":
        return {"status": "ignorado"}

    mensaje_data = payload["data"]
    if mensaje_data["key"]["fromMe"]:
        return {"status": "ignorado"}

    numero = mensaje_data["key"]["remoteJid"]
    nombre = mensaje_data.get("pushName", "Cliente")
    texto  = mensaje_data.get("message", {}).get("conversation", "")

    if not texto:
        return {"status": "sin texto"}

    # ── Routing por número ──
    if es_cristian(numero):
        try:
            await coach_handle_message(numero, texto)
        except Exception as e:
            log.error(f"[COACH] error procesando mensaje: {e}")
        return {"status": "ok", "modo": "coach"}

    # ── Pipeline de agente de leads ──
    log.info(f"Mensaje de {nombre} ({numero}): {texto[:60]}")
    temperatura = clasificar(texto)
    log.info(f"Lead clasificado como: {temperatura}")

    historial = await obtener_historial(numero)
    respuesta = await responder(texto, historial, temperatura)

    await guardar_mensaje(numero, nombre, "user",      texto)
    await guardar_mensaje(numero, nombre, "assistant", respuesta)

    await notificar_vendedor(numero, nombre, texto, temperatura, respuesta)
    await enviar_mensaje(numero, respuesta)

    return {"status": "ok", "modo": "lead", "temperatura": temperatura}
