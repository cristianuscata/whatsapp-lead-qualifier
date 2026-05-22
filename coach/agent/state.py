"""Gestor de estado persistente para el planificador del coach."""

import os
import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def _get_state_path() -> str:
    creds_dir = os.getenv("GOOGLE_CREDS_DIR", "./google")
    return os.path.join(creds_dir, "scheduler_state.json")


def load_state() -> dict[str, Any]:
    path = _get_state_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"[STATE] Error al leer scheduler_state.json: {e}")
    return {}


def save_state(state: dict[str, Any]) -> None:
    path = _get_state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"[STATE] Error al guardar scheduler_state.json: {e}")


# Helpers específicos para scheduler.py

def get_seguimientos_preguntados() -> set[int]:
    state = load_state()
    return set(state.get("seguimientos_preguntados", []))


def add_seguimiento_preguntado(rec_id: int) -> None:
    state = load_state()
    segs = state.get("seguimientos_preguntados", [])
    if rec_id not in segs:
        segs.append(rec_id)
        state["seguimientos_preguntados"] = segs
        save_state(state)


def clear_seguimientos_preguntados() -> None:
    state = load_state()
    state["seguimientos_preguntados"] = []
    save_state(state)


def get_eventos_avisados() -> set[str]:
    state = load_state()
    return set(state.get("eventos_avisados", []))


def add_evento_avisado(key: str) -> None:
    state = load_state()
    evs = state.get("eventos_avisados", [])
    if key not in evs:
        evs.append(key)
        state["eventos_avisados"] = evs
        save_state(state)


def clear_eventos_avisados() -> None:
    state = load_state()
    state["eventos_avisados"] = []
    save_state(state)


def get_eventos_seguimiento() -> set[str]:
    state = load_state()
    return set(state.get("eventos_seguimiento", []))


def add_evento_seguimiento(key: str) -> None:
    state = load_state()
    evs = state.get("eventos_seguimiento", [])
    if key not in evs:
        evs.append(key)
        state["eventos_seguimiento"] = evs
        save_state(state)


def clear_eventos_seguimiento() -> None:
    state = load_state()
    state["eventos_seguimiento"] = []
    save_state(state)


def get_check_mediodia_respondido(fecha_iso: str) -> bool:
    state = load_state()
    respuestas = state.get("check_mediodia_respondido", {})
    # Por defecto asumimos True para no enviar recordatorios falsos en caso de duda
    return respuestas.get(fecha_iso, True)


def set_check_mediodia_respondido(fecha_iso: str, respondido: bool) -> None:
    state = load_state()
    respuestas = state.get("check_mediodia_respondido", {})
    respuestas[fecha_iso] = respondido
    state["check_mediodia_respondido"] = respuestas
    save_state(state)


def remove_check_mediodia_respondido(fecha_iso: str) -> None:
    state = load_state()
    respuestas = state.get("check_mediodia_respondido", {})
    respuestas.pop(fecha_iso, None)
    state["check_mediodia_respondido"] = respuestas
    save_state(state)


# ── Último seguimiento esperando feedback (recordatorio DB o evento Calendar) ──
# Permite que un "sí / no / a medias" se asocie al pendiente correcto, sea
# un recordatorio o un evento de Calendar.

def set_pendiente_feedback(tipo: str, ref: str, ts_iso: str, tarea: str) -> None:
    """tipo: 'recordatorio' (ref = id como str) | 'calendar' (ref = key del evento)."""
    state = load_state()
    state["pendiente_feedback"] = {
        "tipo": tipo,
        "ref": ref,
        "ts": ts_iso,
        "tarea": tarea,
    }
    save_state(state)


def get_pendiente_feedback() -> dict | None:
    return load_state().get("pendiente_feedback")


def clear_pendiente_feedback() -> None:
    state = load_state()
    state.pop("pendiente_feedback", None)
    save_state(state)


def get_eventos_calendar_cumplidos() -> set[str]:
    return set(load_state().get("eventos_calendar_cumplidos", []))


def add_evento_calendar_cumplido(key: str) -> None:
    state = load_state()
    cumplidos = state.get("eventos_calendar_cumplidos", [])
    if key not in cumplidos:
        cumplidos.append(key)
        state["eventos_calendar_cumplidos"] = cumplidos
        save_state(state)


def clear_eventos_calendar_cumplidos() -> None:
    state = load_state()
    state["eventos_calendar_cumplidos"] = []
    save_state(state)
