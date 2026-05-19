"""
Integración con Google Calendar — lectura y escritura.

- crear_evento(tarea, fecha, hora):  inserta un evento en Calendar (hook al crear recordatorio).
- listar_eventos(fecha):             devuelve eventos del día (usado por briefing 6:30, cierre 9 PM, detección de conflictos).

El token OAuth vive en GOOGLE_CREDS_DIR/token.json y se auto-refresca con el
refresh_token. El scope `calendar.events` ya incluye lectura — no hace falta
re-auth.
"""

import logging
import os
from datetime import date, time, datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TZ_LIMA = ZoneInfo("America/Lima")


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


def listar_eventos(fecha: date) -> list[dict]:
    """
    Devuelve eventos timed (con dateTime, no all-day) del calendar para esa fecha.
    Cada evento: {"summary": str, "hora_inicio": "HH:MM", "hora_fin": "HH:MM",
                  "inicio_dt": datetime aware, "fin_dt": datetime aware}.
    Ante cualquier fallo loguea y devuelve [] — nunca lanza.
    """
    try:
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

        inicio_dia = datetime.combine(fecha, time.min).replace(tzinfo=TZ_LIMA)
        fin_dia    = datetime.combine(fecha, time.max).replace(tzinfo=TZ_LIMA)

        service = _get_service()
        resultado = service.events().list(
            calendarId=calendar_id,
            timeMin=inicio_dia.isoformat(),
            timeMax=fin_dia.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        eventos = []
        for ev in resultado.get("items", []):
            start = ev.get("start", {})
            end   = ev.get("end", {})
            if "dateTime" not in start:
                continue  # ignoramos all-day events en v1
            inicio_dt = datetime.fromisoformat(start["dateTime"]).astimezone(TZ_LIMA)
            fin_dt    = datetime.fromisoformat(end["dateTime"]).astimezone(TZ_LIMA)
            eventos.append({
                "summary":     ev.get("summary", "(sin título)"),
                "hora_inicio": inicio_dt.strftime("%H:%M"),
                "hora_fin":    fin_dt.strftime("%H:%M"),
                "inicio_dt":   inicio_dt,
                "fin_dt":      fin_dt,
            })
        return eventos
    except Exception as e:
        log.warning(f"[CALENDAR] no pude listar eventos: {e}")
        return []


def detectar_conflicto(eventos: list[dict], fecha: date, hora_tarea: time,
                       duracion_min: int = 30) -> dict | None:
    """
    Devuelve el primer evento que se solapa con [hora_tarea, +duracion_min],
    o None si no hay conflicto. Compara naive en Lima local.
    """
    inicio_tarea = datetime.combine(fecha, hora_tarea)
    fin_tarea    = inicio_tarea + timedelta(minutes=duracion_min)

    for ev in eventos:
        ev_inicio = ev["inicio_dt"].replace(tzinfo=None)
        ev_fin    = ev["fin_dt"].replace(tzinfo=None)
        if ev_inicio < fin_tarea and ev_fin > inicio_tarea:
            return ev
    return None
