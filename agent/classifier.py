"""
Clasifica el nivel de interés del lead basándose en palabras clave.

Niveles:
    frío     → el cliente navega sin intención clara de compra
    tibio    → muestra interés, hace preguntas concretas
    caliente → quiere comprar, pide precio, disponibilidad o cómo pagar
"""

# Palabras que indican alta intención de compra
PALABRAS_CALIENTE = [
    "comprar", "precio", "costo", "cuánto cuesta", "cuanto vale",
    "disponible", "stock", "pagar", "transferencia", "tarjeta",
    "lo quiero", "me interesa", "lo llevo", "envío", "delivery",
]

# Palabras que indican interés pero sin urgencia
PALABRAS_TIBIO = [
    "información", "info", "detalles", "características", "cómo funciona",
    "qué incluye", "tiempo de entrega", "garantía", "diferencia",
]


def clasificar(mensaje: str) -> str:
    """
    Retorna 'caliente', 'tibio' o 'frío' según el contenido del mensaje.
    La lógica es simple y deliberadamente legible; se puede reemplazar
    por un clasificador de ML si se necesita mayor precisión.
    """
    texto = mensaje.lower()

    if any(palabra in texto for palabra in PALABRAS_CALIENTE):
        return "caliente"

    if any(palabra in texto for palabra in PALABRAS_TIBIO):
        return "tibio"

    return "frío"
