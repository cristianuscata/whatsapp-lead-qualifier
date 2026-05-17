"""
Punto de integración del coach con la app FastAPI.

Expone:
- es_cristian(numero):    decide si un mensaje entrante debe ir al coach.
- iniciar_coach(app):     monta el scheduler en el lifespan de FastAPI.
"""

import os
import logging
from dotenv import load_dotenv

from coach.scheduler import iniciar_scheduler

load_dotenv()
log = logging.getLogger(__name__)

CRISTIAN_PHONE = os.getenv("CRISTIAN_PHONE", "")
COACH_ENABLED  = os.getenv("COACH_ENABLED", "false").lower() == "true"


def es_cristian(numero: str) -> bool:
    """True si el JID del remitente coincide con CRISTIAN_PHONE y el coach está activo."""
    if not COACH_ENABLED or not CRISTIAN_PHONE:
        return False
    return numero == CRISTIAN_PHONE


def iniciar_coach():
    """Arranca el scheduler del coach. Llamado desde el lifespan de FastAPI."""
    if not COACH_ENABLED:
        log.info("[COACH] desactivado (COACH_ENABLED=false)")
        return None
    return iniciar_scheduler()
