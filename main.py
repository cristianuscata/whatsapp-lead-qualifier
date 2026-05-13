import os
import logging
from fastapi import FastAPI, Request
from dotenv import load_dotenv

from agent.openai_agent import responder
from agent.classifier import clasificar
from agent.notifier import notificar_vendedor
from db.supabase import guardar_mensaje, obtener_historial

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="WhatsApp Agent")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    """
    EvolutionAPI llama aquí cada vez que llega un mensaje de WhatsApp.
    Pipeline: recibir → clasificar → responder → (alertar si es caliente)
    """
    payload = await request.json()

    # 1. Extraer datos del mensaje
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

    log.info(f"Mensaje de {nombre} ({numero}): {texto[:60]}")

    # 2. Clasificar lead: frío / tibio / caliente
    temperatura = clasificar(texto)
    log.info(f"Lead clasificado como: {temperatura}")

    # 3. Obtener historial y generar respuesta con Gemini
    historial = await obtener_historial(numero)
    respuesta = await responder(texto, historial, temperatura)

    # 4. Guardar en Supabase
    await guardar_mensaje(numero, nombre, "user",      texto)
    await guardar_mensaje(numero, nombre, "assistant", respuesta)

    # 5. Notificar al vendedor (caliente=urgente, tibio=info, frío=silencioso)
    await notificar_vendedor(numero, nombre, texto, temperatura, respuesta)

    # 6. Enviar respuesta por WhatsApp vía EvolutionAPI
    await enviar_whatsapp(numero, respuesta)

    return {"status": "ok", "temperatura": temperatura}


async def enviar_whatsapp(numero: str, texto: str):
    """Envía un mensaje de texto usando EvolutionAPI."""
    import httpx

    url       = os.getenv("EVOLUTION_URL", "").rstrip("/")
    instancia = os.getenv("EVOLUTION_INSTANCE")
    api_key   = os.getenv("EVOLUTION_API_KEY")

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(
                f"{url}/message/sendText/{instancia}",
                headers={"apikey": api_key},
                json={"number": numero, "text": texto},
            )
            response.raise_for_status()
            log.info(f"Mensaje enviado a {numero}")
        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            log.error(f"Error HTTP {e.response.status_code} al enviar mensaje a {numero}: {e}. Detalle: {error_body}")
        except httpx.HTTPError as e:
            log.error(f"Error de conexión enviando mensaje a {numero}: {e}")
