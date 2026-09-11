"""Prueba de humo de punta a punta (agente + MCP + modelo).

Requiere:
- api/mcp.py corriendo en otra terminal (puerto 8001).
- OPENROUTER_API_KEY válida en .env.

Ejecuta: python tests/test_smoke.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import responder


async def main():
    pregunta = "¿Cómo voy con la meta PTE?"
    respuesta = await responder(pregunta)
    assert respuesta
    print(f"Pregunta:  {pregunta}\n")
    print(f"Respuesta: {respuesta}")


if __name__ == "__main__":
    asyncio.run(main())
