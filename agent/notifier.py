"""
Notifica al vendedor según la clasificación del lead.

Estrategia de notificación:
    🔥 caliente → alerta INMEDIATA con urgencia (el cliente quiere comprar)
    🌤️ tibio    → notificación informativa (el cliente muestra interés)
    🧊 frío     → sin notificación (solo se guarda en Supabase)

El vendedor recibe contexto suficiente para decidir si intervenir.
"""

import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

VENDEDOR_NUMERO    = os.getenv("VENDEDOR_NUMERO")       # ej: 51958213628
EVOLUTION_URL      = os.getenv("EVOLUTION_URL", "").rstrip("/")
EVOLUTION_API_KEY  = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE")


# ── Plantillas de mensaje por temperatura ──

def _formato_caliente(nombre: str, numero_cliente: str, mensaje: str) -> str:
    return (
        f"🔥🔥🔥 *LEAD CALIENTE* 🔥🔥🔥\n\n"
        f"👤 *Cliente:* {nombre}\n"
        f"📱 *Número:* {numero_cliente.split('@')[0]}\n"
        f"💬 *Dijo:* _{mensaje}_\n\n"
        f"⚡ *Acción:* Este cliente quiere comprar AHORA.\n"
        f"Entra al chat y cierra la venta 💪"
    )


def _formato_tibio(nombre: str, numero_cliente: str, mensaje: str) -> str:
    return (
        f"🌤️ *Lead tibio detectado*\n\n"
        f"👤 *Cliente:* {nombre}\n"
        f"📱 *Número:* {numero_cliente.split('@')[0]}\n"
        f"💬 *Dijo:* _{mensaje}_\n\n"
        f"💡 *Acción:* Está interesado pero aún no decide.\n"
        f"El bot ya le respondió. Revisa el chat si quieres intervenir."
    )


PLANTILLAS = {
    "caliente": _formato_caliente,
    "tibio":    _formato_tibio,
}


async def notificar_vendedor(
    numero_cliente: str,
    nombre: str,
    mensaje: str,
    temperatura: str,
    respuesta_bot: str,
):
    """
    Envía una notificación al vendedor según la temperatura del lead.

    Args:
        numero_cliente: JID del cliente que escribió.
        nombre:         Nombre del cliente (pushName de WhatsApp).
        mensaje:        Último mensaje que envió el cliente.
        temperatura:    'frío', 'tibio' o 'caliente'.
        respuesta_bot:  Lo que el bot le respondió al cliente.
    """
    # Los leads fríos no generan notificación (se guardan en Supabase)
    if temperatura == "frío":
        log.info(f"Lead frío de {nombre} — sin notificación al vendedor")
        return

    if not VENDEDOR_NUMERO:
        log.warning("VENDEDOR_NUMERO no configurado — notificación omitida")
        return

    # Obtener la plantilla según temperatura
    formato_fn = PLANTILLAS.get(temperatura)
    if not formato_fn:
        log.warning(f"Temperatura desconocida: {temperatura}")
        return

    texto_alerta = formato_fn(nombre, numero_cliente, mensaje)

    await _enviar_whatsapp_vendedor(texto_alerta, nombre, temperatura)


async def _enviar_whatsapp_vendedor(texto: str, nombre: str, temperatura: str):
    """Envía un mensaje al vendedor vía Evolution API."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(
                f"{EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCE}",
                headers={"apikey": EVOLUTION_API_KEY},
                json={"number": VENDEDOR_NUMERO, "text": texto},
            )
            response.raise_for_status()
            log.info(f"Notificación [{temperatura}] enviada al vendedor para: {nombre}")
        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            log.error(
                f"Error HTTP {e.response.status_code} notificando al vendedor: {e}. "
                f"Detalle: {error_body}"
            )
        except httpx.HTTPError as e:
            log.error(f"Error de conexión notificando al vendedor: {e}")
