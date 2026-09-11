"""Sirve el servidor MCP del coach por HTTP (contenedor `mcp`).

Ejecuta:  uvicorn coach.mcp.mcp_app:app --host 0.0.0.0 --port 8002
Uso interno del docker-compose; NO se expone públicamente.

stateless_http=True: cada llamada abre un contexto nuevo, sin depender de que dos
solicitudes lleguen a la misma instancia.
"""
from coach.mcp.mcp_server import mcp

app = mcp.http_app(path="/", stateless_http=True)
