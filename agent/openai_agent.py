import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Eres un asistente de ventas amable y profesional de WhatsApp.
Tu objetivo es ayudar al cliente y guiarlo hacia una compra.

Reglas:
- Responde siempre en el mismo idioma que el cliente.
- Sé conciso (máximo 3 oraciones).
- Si el cliente está muy interesado, ofrece agendar una llamada.
- Nunca inventes precios ni especificaciones que no se te hayan dado.
"""

async def responder(mensaje: str, historial: list, temperatura: str) -> str:
    """
    Genera una respuesta con OpenAI usando el historial de conversación.

    Args:
        mensaje:     Texto del cliente.
        historial:   Lista de dicts {"role": "user"|"assistant", "content": "texto"}
        temperatura: "frío" | "tibio" | "caliente" (ajusta el tono)

    Returns:
        Texto de respuesta del agente.
    """
    # Ajustar el prompt según la temperatura del lead
    contexto_extra = {
        "frío":     "El cliente aún no está seguro, sé paciente y educativo.",
        "tibio":    "El cliente muestra interés, destaca los beneficios clave.",
        "caliente": "El cliente quiere comprar, ayúdalo a concretar la compra ahora.",
    }.get(temperatura, "")

    prompt = f"{mensaje}\n\n[Contexto interno: {contexto_extra}]" if contexto_extra else mensaje

    # Preparar mensajes para OpenAI
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(historial)
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7
    )
    
    return response.choices[0].message.content.strip()
