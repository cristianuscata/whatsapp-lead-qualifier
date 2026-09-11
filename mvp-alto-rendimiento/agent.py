"""Agente LangChain que descubre tools vía MCP.

No importa mcp_server.py directamente: la única forma de llegar a las tools
consultar_metas / consultar_recordatorios es a través del protocolo MCP.
Ese desacople es el punto central del patrón de la guía "Del PoC al MVP".

Reutiliza el mismo bloque ChatOpenAI + OpenRouter probado en el PoC (sesión 5).
"""
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from config import MODEL_ID, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MCP_URL
from prompts import SYSTEM_PROMPT

# OJO: el SDK de OpenAI exige un api_key no vacío para construir el cliente.
# Con "" revienta al importar este módulo (y al arrancar api/chat.py), antes
# de que llegues a preguntar nada. Si todavía no pusiste tu clave real en
# .env usamos un placeholder para que el servidor levante igual; la falla
# aparecerá recién al preguntar, como un error de autenticación legible
# devuelto por /api/chat.
llm = ChatOpenAI(
    model=MODEL_ID,
    api_key=OPENROUTER_API_KEY or "sk-configura-tu-clave-en-env",
    base_url=OPENROUTER_BASE_URL,
    temperature=0,
    max_tokens=4096,
)


async def crear_agente():
    client = MultiServerMCPClient(
        {
            "coach": {
                "transport": "http",
                "url": MCP_URL,
            }
        }
    )
    tools = await client.get_tools()
    return create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)


async def responder(pregunta: str) -> str:
    agente = await crear_agente()
    resultado = await agente.ainvoke(
        {"messages": [{"role": "user", "content": pregunta}]}
    )
    return resultado["messages"][-1].content
