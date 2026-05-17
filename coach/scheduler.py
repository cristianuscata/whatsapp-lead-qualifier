"""
APScheduler con todos los jobs proactivos del coach.

Jobs:
- Cada minuto:   revisa avisos (5 min antes) y preguntas de seguimiento (30 min después).
- 06:30 (Lima):  mensaje de arranque del día con tareas + versículo + pregunta.
- 12:00 (Lima):  check del mediodía sobre la tarea de la mañana.
- 12:30 (Lima):  si Cristian no respondió → recordatorio.
- 21:00 (Lima):  cierre del día (balance + reprogramar no cumplidas + versículo).

Todos los errores se manejan silenciosamente para que un fallo de un job
no tumbe el scheduler ni la app.
"""

import os
import logging
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from coach.agent.openai_coach import generar_mensaje
from coach.agent.prompts import (
    plantilla_aviso,
    plantilla_pregunta_seguimiento,
    plantilla_recordatorio_12_30,
)
from coach.db import mensajes as m_db
from coach.db import recordatorios as r_db
from whatsapp import enviar_mensaje

load_dotenv()
log = logging.getLogger(__name__)
TZ_LIMA = ZoneInfo("America/Lima")
CRISTIAN_PHONE = os.getenv("CRISTIAN_PHONE", "")

# Estado en memoria (se reinicia con la app — aceptable para v1)
_seguimientos_preguntados: set[int] = set()
_check_mediodia_respondido: dict[str, bool] = {}


def iniciar_scheduler() -> AsyncIOScheduler | None:
    """
    Crea, configura y arranca el scheduler. Llamado al startup de FastAPI.
    Devuelve None si COACH_ENABLED=false o si CRISTIAN_PHONE no está seteado.
    """
    if os.getenv("COACH_ENABLED", "false").lower() != "true":
        log.info("[COACH] COACH_ENABLED=false → scheduler no inicia")
        return None
    if not CRISTIAN_PHONE:
        log.warning("[COACH] CRISTIAN_PHONE no configurado → scheduler no inicia")
        return None

    sched = AsyncIOScheduler(timezone=TZ_LIMA)
    sched.add_job(_tick_recordatorios, CronTrigger(second=0))
    sched.add_job(_arranque_dia,       CronTrigger(hour=6,  minute=30))
    sched.add_job(_check_mediodia,     CronTrigger(hour=12, minute=0))
    sched.add_job(_recordatorio_12_30, CronTrigger(hour=12, minute=30))
    sched.add_job(_cierre_dia,         CronTrigger(hour=21, minute=0))
    sched.start()
    log.info("[COACH] scheduler iniciado (TZ=America/Lima)")
    return sched


def marcar_check_mediodia_respondido() -> None:
    """Coach.py llama esto cuando llega cualquier mensaje de Cristian."""
    hoy = datetime.now(TZ_LIMA).date().isoformat()
    _check_mediodia_respondido[hoy] = True


# ── Helpers internos ──

async def _enviar(texto: str, tipo: str) -> None:
    try:
        await enviar_mensaje(CRISTIAN_PHONE, texto)
        await m_db.guardar("assistant", texto, tipo=tipo)
    except Exception as e:
        log.error(f"[COACH] error enviando '{tipo}': {e}")


def _add_minutes(hora_str: str, minutos: int) -> str:
    """Suma minutos a una hora 'HH:MM:SS' o 'HH:MM' y retorna 'HH:MM'."""
    formato = "%H:%M:%S" if hora_str.count(":") == 2 else "%H:%M"
    base = datetime.strptime(hora_str, formato)
    return (base + timedelta(minutes=minutos)).strftime("%H:%M")


# ── Jobs ──

async def _tick_recordatorios() -> None:
    try:
        ahora = datetime.now(TZ_LIMA)
        fecha = ahora.date()
        hora  = ahora.time()

        for rec in await r_db.pendientes_aviso(fecha, hora):
            await _enviar(plantilla_aviso(rec["tarea"]), tipo="aviso")
            await r_db.marcar_avisado(rec["id"])
            log.info(f"[COACH] aviso enviado: {rec['tarea']}")

        for rec in await r_db.pendientes_seguimiento(fecha, hora):
            if rec["id"] in _seguimientos_preguntados:
                continue
            hora_tarea = _add_minutes(rec["hora_recordar"], 5)
            await _enviar(
                plantilla_pregunta_seguimiento(rec["tarea"], hora_tarea),
                tipo="seguimiento_pregunta",
            )
            _seguimientos_preguntados.add(rec["id"])
            log.info(f"[COACH] seguimiento preguntado: {rec['tarea']}")
    except Exception as e:
        log.error(f"[COACH] _tick_recordatorios: {e}")


async def _arranque_dia() -> None:
    try:
        hoy = datetime.now(TZ_LIMA).date()
        tareas = await r_db.tareas_del_dia(hoy)
        listado = (
            "\n".join(f"- {t['hora_recordar'][:5]} {t['tarea']}" for t in tareas)
            if tareas
            else "(no hay tareas programadas todavía)"
        )

        instr = (
            "Es 6:30 AM, lunes-a-domingo. Generá el mensaje de arranque del día para Cristian. "
            "Tareas programadas hoy:\n"
            f"{listado}\n\n"
            "Estructura: saludo breve + lista de tareas tal cual + versículo motivador "
            "+ una pregunta de acción concreta para arrancar el día. Máximo 6 líneas."
        )
        try:
            texto = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando arranque: {e}")
            texto = (
                "☀️ Buen día, Cristian.\n"
                f"Tareas de hoy:\n{listado}\n"
                "'El alma diligente será prosperada' — Prov 13:4\n"
                "¿Cuál atacás primero?"
            )
        await _enviar(texto, tipo="arranque_dia")
        _seguimientos_preguntados.clear()
        _check_mediodia_respondido.pop(hoy.isoformat(), None)
    except Exception as e:
        log.error(f"[COACH] _arranque_dia: {e}")


async def _check_mediodia() -> None:
    try:
        hoy = datetime.now(TZ_LIMA).date()
        tareas_manana = [
            t for t in await r_db.tareas_del_dia(hoy)
            if t["hora_recordar"] < "12:00:00"
        ]
        if not tareas_manana:
            log.info("[COACH] check mediodía: sin tareas de la mañana")
            return

        tarea_str = ", ".join(t["tarea"] for t in tareas_manana)
        texto = (
            "☀️ Check del mediodía.\n"
            f"¿Cumpliste con la tarea de la mañana ({tarea_str})?\n"
            "Respondé: sí / no / a medias"
        )
        await _enviar(texto, tipo="check_mediodia")
        _check_mediodia_respondido[hoy.isoformat()] = False
    except Exception as e:
        log.error(f"[COACH] _check_mediodia: {e}")


async def _recordatorio_12_30() -> None:
    try:
        hoy = datetime.now(TZ_LIMA).date().isoformat()
        # Si nunca se envió check (sin tareas mañana) o ya respondió → nada
        if _check_mediodia_respondido.get(hoy, True):
            return
        await _enviar(plantilla_recordatorio_12_30(), tipo="recordatorio_check")
    except Exception as e:
        log.error(f"[COACH] _recordatorio_12_30: {e}")


async def _cierre_dia() -> None:
    try:
        hoy = datetime.now(TZ_LIMA).date()
        tareas = await r_db.tareas_del_dia(hoy)
        cumplidas    = [t for t in tareas if t["cumplido"] is True]
        a_reprogramar = [
            t for t in tareas
            if t["cumplido"] is not True and not t.get("reprogramado")
        ]

        # Reprogramar para mañana las que no cumplió (y no fueron procesadas antes)
        manana = hoy + timedelta(days=1)
        for t in a_reprogramar:
            try:
                hr = dtime.fromisoformat(t["hora_recordar"])
                hs = dtime.fromisoformat(t["hora_seguimiento"])
                await r_db.crear_recordatorio(t["tarea"], hr, hs, manana)
                await r_db.marcar_reprogramado(t["id"])
            except Exception as e:
                log.error(f"[COACH] error reprogramando {t.get('tarea')}: {e}")

        cumplidas_str = (
            "\n".join(f"✅ {t['tarea']}" for t in cumplidas) if cumplidas else "(ninguna)"
        )
        reprog_str = (
            "\n".join(f"⏭️ {t['tarea']}" for t in a_reprogramar) if a_reprogramar else "(ninguna)"
        )

        instr = (
            "Es 9 PM, cierre del día para Cristian.\n"
            f"Cumplidas:\n{cumplidas_str}\n"
            f"Reprogramadas para mañana:\n{reprog_str}\n\n"
            "Estructura: balance honesto + versículo de cierre + un foco concreto para mañana. "
            "Máximo 6 líneas."
        )
        try:
            texto = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando cierre: {e}")
            texto = (
                "🌙 Cierre del día.\n"
                f"Cumplidas:\n{cumplidas_str}\n"
                f"Reprogramadas:\n{reprog_str}\n"
                "'Todo lo puedo en Cristo que me fortalece' — Fil 4:13"
            )
        await _enviar(texto, tipo="cierre_dia")
    except Exception as e:
        log.error(f"[COACH] _cierre_dia: {e}")
