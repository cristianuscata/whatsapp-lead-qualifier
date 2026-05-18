"""
Integración con Google Calendar — solo escritura (Opción A).

Crea un evento en Calendar cuando se guarda un recordatorio.
El token OAuth se guarda en GOOGLE_CREDS_DIR/token.json y sobrevive rebuilds
gracias al volumen montado en docker-compose.yml.
"""

import logging
import os
from datetime import date, time, datetime, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _creds_dir() -> str:
    return os.getenv("GOOGLE_CREDS_DIR", "./google")


def _token_path() -> str:
    return os.path.join(_creds_dir(), "token.json")


def _credentials_path() -> str:
    return os.path.join(_creds_dir(), "credentials.json")


def _get_service():
    creds = None

    if os.path.exists(_token_path()):
        creds = Credentials.from_authorized_user_file(_token_path(), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "No hay token de Google Calendar. "
                "Corré: python -m coach.integrations.calendar_auth"
            )

        with open(_token_path(), "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def crear_evento(tarea: str, fecha: date, hora: time, duracion_min: int = 30) -> str:
    """
    Crea un evento en Google Calendar y devuelve el event_id.
    Lanza excepción si falla — el caller debe usar try/except.
    """
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    inicio = datetime.combine(fecha, hora)
    fin = inicio + timedelta(minutes=duracion_min)

    # Google Calendar usa RFC3339 con offset; usamos Lima (UTC-5)
    tz_str = "America/Lima"

    evento = {
        "summary": tarea,
        "start": {"dateTime": inicio.isoformat(), "timeZone": tz_str},
        "end":   {"dateTime": fin.isoformat(),    "timeZone": tz_str},
    }

    service = _get_service()
    resultado = service.events().insert(calendarId=calendar_id, body=evento).execute()
    event_id = resultado.get("id", "")
    log.info(f"[CALENDAR] evento creado: {event_id} — {tarea}")
    return event_id
