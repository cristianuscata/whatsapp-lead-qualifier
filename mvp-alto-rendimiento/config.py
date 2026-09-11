"""Configuración del MVP. Todo por variables de entorno; sin secretos en código."""
import os

from dotenv import load_dotenv

load_dotenv()

MODEL_ID = os.getenv("MODEL_ID", "nvidia/nemotron-3-ultra-550b-a55b:free")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8001/")
