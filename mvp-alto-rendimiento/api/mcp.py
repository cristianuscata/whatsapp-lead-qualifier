"""Sirve mcp_server.py como servicio HTTP independiente, para desarrollo local.

Ejecuta: uvicorn api.mcp:app --reload --port 8001
Quedará disponible en http://127.0.0.1:8001/
"""
import sys
from pathlib import Path

# Permite importar mcp_server.py (en la raíz del proyecto) al correr desde api/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_server import mcp

# path="/": ruta interna relativa a donde se monte esta app. Aquí no se monta
# dentro de nada más, así que responde en la raíz del puerto 8001.
#
# stateless_http=True: cada llamada abre un contexto nuevo, sin necesitar que
# dos solicitudes lleguen a la misma instancia. Es el modo pensado para
# entornos sin garantía de "instancia fija" — como el despliegue opcional.
app = mcp.http_app(path="/", stateless_http=True)
