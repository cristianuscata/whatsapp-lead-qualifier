"""Agente MCP del coach de alto rendimiento (chat libre por WhatsApp).

Reemplaza el chat libre del v1 (openai_coach.responder_chat) cuando el flag
USE_MCP_AGENT=true. Usa GPT-4o-mini y descubre sus tools por MCP
(MultiServerMCPClient), en vez de inyectar todo el contexto en el prompt.

El resto del v1 (scheduler proactivo, feedback sí/no/medias, creación de
recordatorios, calendario) NO pasa por aquí: sigue determinista.
"""
import os

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from coach.agent.prompts import SYSTEM_COACH_AR

MCP_URL = os.getenv("MCP_URL", "http://mcp:8002/")

# El SDK de OpenAI exige api_key no vacío para construir el cliente. Si falta,
# usamos un placeholder para que el proceso levante; falla recién al invocar.
llm = ChatOpenAI(
    model=os.getenv("COACH_MODEL", "gpt-4o-mini"),
    api_key=os.getenv("OPENAI_API_KEY") or "sk-configura-tu-clave",
    temperature=0.3,
)

_client: MultiServerMCPClient | None = None


async def _get_tools():
    global _client
    if _client is None:
        _client = MultiServerMCPClient(
            {"coach": {"transport": "http", "url": MCP_URL}}
        )
    return await _client.get_tools()


async def responder_agente(mensaje: str, historial: list[dict]) -> str:
    """Genera la respuesta del coach usando el agente + tools MCP.

    `historial` viene de coach.db.mensajes.historial() como [{role, content}, ...].
    Devuelve el texto final del asistente (mismo contrato que responder_chat).
    """
    tools = await _get_tools()
    agente = create_agent(model=llm, tools=tools, system_prompt=SYSTEM_COACH_AR)
    mensajes = list(historial) + [{"role": "user", "content": mensaje}]
    resultado = await agente.ainvoke({"messages": mensajes})
    return resultado["messages"][-1].content
