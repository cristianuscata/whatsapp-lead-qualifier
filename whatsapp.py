"""Cliente compartido para enviar mensajes vía Evolution API."""

import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

EVOLUTION_URL      = os.getenv("EVOLUTION_URL", "").rstrip("/")
EVOLUTION_API_KEY  = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE")


async def enviar_mensaje(numero: str, texto: str) -> None:
    """Envía un mensaje de texto a un número (JID) vía Evolution API."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(
                f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
                headers={"apikey": EVOLUTION_API_KEY},
                json={"number": numero, "text": texto},
            )
            response.raise_for_status()
            log.info(f"Mensaje enviado a {numero}")
        except httpx.HTTPStatusError as e:
            log.error(
                f"Error HTTP {e.response.status_code} enviando a {numero}: {e}. "
                f"Detalle: {e.response.text}"
            )
        except httpx.HTTPError as e:
            log.error(f"Error de conexión enviando a {numero}: {e}")
