"""
APScheduler con todos los jobs proactivos del coach.

Jobs:
- Cada minuto:        revisa avisos (5 min antes) y preguntas de seguimiento (30 min después) de recordatorios DB.
- Cada 5 min:         revisa eventos de Calendar → aviso 10 min antes, seguimiento 15 min después.
- 06:30 (Lima, todos los días):  arranque del día — tareas + eventos de Calendar + versículo.
- 12:00 (Lima):       check del mediodía sobre la tarea de la mañana.
- 12:30 (Lima):       si Cristian no respondió → recordatorio.
- 21:00 (Lima):       cierre del día — balance + reprogramar SOLO no-cumplidas + vista de mañana (Calendar).
- 19:00 mié (Lima):   check-in emocional — cómo se siente, qué le pesa, hilo con conversaciones recientes.
- 22:00 sáb (Lima):   resumen semanal silencioso — comprime 7 días de chat en bullets persistidos.
- 20:00 dom (Lima):   revisión semanal — 2 metas MENOS atendidas (chat + ejecución) en las últimas 2 semanas.

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
    METAS_ACTIVAS,
    plantilla_aviso,
    plantilla_pregunta_seguimiento,
    plantilla_recordatorio_12_30,
)
from coach.agent.state import (
    get_seguimientos_preguntados,
    add_seguimiento_preguntado,
    clear_seguimientos_preguntados,
    get_eventos_avisados,
    add_evento_avisado,
    clear_eventos_avisados,
    get_eventos_seguimiento,
    add_evento_seguimiento,
    clear_eventos_seguimiento,
    get_eventos_calendar_cumplidos,
    clear_eventos_calendar_cumplidos,
    set_pendiente_feedback,
    get_check_mediodia_respondido,
    set_check_mediodia_respondido,
    remove_check_mediodia_respondido,
)
from coach.db import mensajes as m_db
from coach.db import recordatorios as r_db
from coach.db import resumenes as res_db
from coach.integrations.calendar import listar_eventos
from whatsapp import enviar_mensaje

load_dotenv()
log = logging.getLogger(__name__)
TZ_LIMA = ZoneInfo("America/Lima")
CRISTIAN_PHONE = os.getenv("CRISTIAN_PHONE", "")


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
    sched.add_job(_tick_recordatorios,      CronTrigger(second=0))
    sched.add_job(_tick_eventos_calendar,   CronTrigger(minute="*/5", second=30))
    sched.add_job(_arranque_dia,            CronTrigger(hour=6,  minute=30))
    sched.add_job(_check_mediodia,          CronTrigger(hour=12, minute=0))
    sched.add_job(_recordatorio_12_30,      CronTrigger(hour=12, minute=30))
    sched.add_job(_cierre_dia,              CronTrigger(hour=21, minute=0))
    sched.add_job(_revision_semanal_metas,  CronTrigger(day_of_week="sun", hour=20, minute=0))
    sched.add_job(_check_in_emocional,      CronTrigger(day_of_week="wed", hour=19, minute=0))
    sched.add_job(_resumen_semanal,         CronTrigger(day_of_week="sat", hour=22, minute=0))
    sched.start()
    log.info("[COACH] scheduler iniciado (TZ=America/Lima)")
    return sched


def marcar_check_mediodia_respondido() -> None:
    """Coach.py llama esto cuando llega cualquier mensaje de Cristian."""
    hoy = datetime.now(TZ_LIMA).date().isoformat()
    set_check_mediodia_respondido(hoy, True)


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
            if rec["id"] in get_seguimientos_preguntados():
                continue
            hora_tarea = _add_minutes(rec["hora_recordar"], 5)
            await _enviar(
                plantilla_pregunta_seguimiento(rec["tarea"], hora_tarea),
                tipo="seguimiento_pregunta",
            )
            add_seguimiento_preguntado(rec["id"])
            set_pendiente_feedback(
                tipo="recordatorio",
                ref=str(rec["id"]),
                ts_iso=ahora.isoformat(),
                tarea=rec["tarea"],
            )
            log.info(f"[COACH] seguimiento preguntado: {rec['tarea']}")
    except Exception as e:
        log.error(f"[COACH] _tick_recordatorios: {e}")


async def _tick_eventos_calendar() -> None:
    """Cada 5 min: avisa 10 min antes de un evento Calendar, pregunta 15 min después.
    Ignora eventos que ya están como recordatorios en la DB (para no duplicar)."""
    try:
        ahora = datetime.now(TZ_LIMA)
        hoy = ahora.date()
        eventos = listar_eventos(hoy)

        # Nombres de tareas en la DB hoy → para no duplicar con el tick de recordatorios
        tareas_db = await r_db.tareas_del_dia(hoy)
        nombres_db = {t["tarea"].lower().strip() for t in tareas_db}

        cumplidos = get_eventos_calendar_cumplidos()
        for ev in eventos:
            # Si el evento fue creado por el bot (existe como recordatorio), skip
            if ev["summary"].lower().strip() in nombres_db:
                continue
            key = f"{ev['hora_inicio']}|{ev['summary']}"
            if key in cumplidos:
                continue  # ya respondió sí/no/medias, no re-preguntar
            inicio = ev["inicio_dt"]
            fin = ev["fin_dt"]
            minutos_para_inicio = (inicio - ahora).total_seconds() / 60
            minutos_desde_fin = (ahora - fin).total_seconds() / 60

            # Aviso previo: entre 10 y 0 minutos antes del inicio
            if 0 <= minutos_para_inicio <= 10 and key not in get_eventos_avisados():
                add_evento_avisado(key)
                try:
                    instr = (
                        f"Cristian tiene '{ev['summary']}' a las {ev['hora_inicio']}. "
                        f"Faltan ~{int(minutos_para_inicio)} minutos. "
                        "Avísale que se prepare. Máximo 3 líneas, tono directo y motivador."
                    )
                    texto = await generar_mensaje(instr)
                except Exception:
                    texto = (
                        f"⏰ En unos minutos: *{ev['summary']}* ({ev['hora_inicio']})\n"
                        f"Prepárate, Cristian."
                    )
                await _enviar(texto, tipo="aviso_evento_calendar")
                log.info(f"[CALENDAR] aviso previo enviado: {ev['summary']}")

            # Seguimiento: entre 15 y 30 minutos después de que terminó
            if 15 <= minutos_desde_fin <= 30 and key not in get_eventos_seguimiento():
                add_evento_seguimiento(key)
                try:
                    instr = (
                        f"'{ev['summary']}' estaba programado de {ev['hora_inicio']} a {ev['hora_fin']}. "
                        "Ya pasó. Pregúntale a Cristian si lo cumplió. "
                        "Máximo 3 líneas, directo."
                    )
                    texto = await generar_mensaje(instr)
                except Exception:
                    texto = (
                        f"¿Cumpliste con *{ev['summary']}* "
                        f"(de las {ev['hora_inicio']})?\n"
                        f"Responde: sí / no / a medias"
                    )
                await _enviar(texto, tipo="seguimiento_evento_calendar")
                set_pendiente_feedback(
                    tipo="calendar",
                    ref=key,
                    ts_iso=ahora.isoformat(),
                    tarea=ev["summary"],
                )
                log.info(f"[CALENDAR] seguimiento enviado: {ev['summary']}")

    except Exception as e:
        log.error(f"[COACH] _tick_eventos_calendar: {e}")


_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_humana(fecha) -> str:
    return f"{_DIAS_ES[fecha.weekday()]} {fecha.day} de {_MESES_ES[fecha.month - 1]} ({fecha.isoformat()})"


def _formatear_eventos(eventos: list[dict], fecha=None) -> str:
    if not eventos:
        return "(sin eventos)"
    prefijo = f"[{fecha.isoformat()}] " if fecha is not None else ""
    return "\n".join(f"- {prefijo}{ev['hora_inicio']}–{ev['hora_fin']} {ev['summary']}" for ev in eventos)


async def _arranque_dia() -> None:
    try:
        hoy = datetime.now(TZ_LIMA).date()
        tareas = await r_db.tareas_del_dia(hoy)
        eventos = listar_eventos(hoy)

        listado_tareas = (
            "\n".join(f"- {t['hora_recordar'][:5]} {t['tarea']}" for t in tareas)
            if tareas
            else "(no hay tareas programadas todavía)"
        )
        listado_eventos = _formatear_eventos(eventos, fecha=hoy)

        instr = (
            f"Es 6:30 AM del {_fecha_humana(hoy)}. Genera el mensaje de arranque del día para Cristian. "
            "IMPORTANTE: solo menciones tareas/eventos que aparecen en las listas abajo, "
            "NO inventes fechas ni horas — las listas son la única fuente de verdad.\n\n"
            "Tareas programadas hoy (recordatorios del coach):\n"
            f"{listado_tareas}\n\n"
            "Eventos en tu Google Calendar hoy (meetings, citas, compromisos):\n"
            f"{listado_eventos}\n\n"
            "Estructura: saludo breve + las dos listas (separadas, con la hora EXACTA como aparece) "
            "+ versículo motivador + una pregunta de acción concreta. Máximo 8 líneas."
        )
        try:
            texto = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando arranque: {e}")
            texto = (
                "☀️ Buen día, Cristian.\n"
                f"Tareas:\n{listado_tareas}\n"
                f"Calendar:\n{listado_eventos}\n"
                "'El alma diligente será prosperada' — Prov 13:4\n"
                "¿Cuál atacas primero?"
            )
        await _enviar(texto, tipo="arranque_dia")
        clear_seguimientos_preguntados()
        clear_eventos_avisados()
        clear_eventos_seguimiento()
        clear_eventos_calendar_cumplidos()
        remove_check_mediodia_respondido(hoy.isoformat())
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
            "Responde: sí / no / a medias"
        )
        await _enviar(texto, tipo="check_mediodia")
        set_check_mediodia_respondido(hoy.isoformat(), False)
    except Exception as e:
        log.error(f"[COACH] _check_mediodia: {e}")


async def _recordatorio_12_30() -> None:
    try:
        hoy = datetime.now(TZ_LIMA).date().isoformat()
        # Si nunca se envió check (sin tareas mañana) o ya respondió → nada
        if get_check_mediodia_respondido(hoy):
            return
        await _enviar(plantilla_recordatorio_12_30(), tipo="recordatorio_check")
    except Exception as e:
        log.error(f"[COACH] _recordatorio_12_30: {e}")


async def _cierre_dia() -> None:
    try:
        hoy = datetime.now(TZ_LIMA).date()
        tareas = await r_db.tareas_del_dia(hoy)
        cumplidas    = [t for t in tareas if t["cumplido"] is True]
        # SOLO reprogramamos lo que Cristian dijo explícitamente que no cumplió
        # (cumplido=False). Las que están sin respuesta (cumplido=null) se
        # mencionan pero NO se mueven, para evitar duplicaciones cuando
        # responde tarde.
        a_reprogramar = [
            t for t in tareas
            if t["cumplido"] is False and not t.get("reprogramado")
        ]
        sin_respuesta = [
            t for t in tareas
            if t["cumplido"] is None
        ]

        # Reprogramar para mañana las que confirmó que no cumplió
        manana = hoy + timedelta(days=1)
        for t in a_reprogramar:
            try:
                hr = dtime.fromisoformat(t["hora_recordar"])
                hs = dtime.fromisoformat(t["hora_seguimiento"])
                await r_db.crear_recordatorio(
                    t["tarea"], hr, hs, manana, meta_key=t.get("meta_key")
                )
                await r_db.marcar_reprogramado(t["id"])
            except Exception as e:
                log.error(f"[COACH] error reprogramando {t.get('tarea')}: {e}")

        eventos_manana = listar_eventos(manana)
        eventos_manana_str = _formatear_eventos(eventos_manana, fecha=manana)

        cumplidas_str = (
            "\n".join(f"✅ {t['tarea']}" for t in cumplidas) if cumplidas else "(ninguna)"
        )
        reprog_str = (
            "\n".join(f"⏭️ {t['tarea']}" for t in a_reprogramar) if a_reprogramar else "(ninguna)"
        )
        sin_respuesta_str = (
            "\n".join(f"❓ {t['tarea']}" for t in sin_respuesta) if sin_respuesta else ""
        )

        bloque_sin_respuesta = (
            f"\nSin respuesta (no las muevo, contame qué pasó):\n{sin_respuesta_str}\n"
            if sin_respuesta_str else ""
        )

        instr = (
            f"Es 9 PM del {_fecha_humana(hoy)}, cierre del día para Cristian. "
            f"Mañana es {_fecha_humana(manana)}. "
            "IMPORTANTE: usa SOLO las tareas y eventos de las listas abajo, "
            "NO inventes fechas ni horas.\n\n"
            f"Cumplidas hoy:\n{cumplidas_str}\n"
            f"Reprogramadas para mañana (las que dijo que no cumplió):\n{reprog_str}\n"
            f"{bloque_sin_respuesta}\n"
            f"Eventos en Calendar para mañana:\n{eventos_manana_str}\n\n"
            "Estructura: balance honesto de hoy + vista de mañana (tareas + Calendar) "
            "+ si hay 'sin respuesta', pídele que te diga rápido si las cumplió o no "
            "+ versículo de cierre + un foco concreto para mañana. Máximo 9 líneas."
        )
        try:
            texto = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando cierre: {e}")
            sin_resp_fb = (
                f"Sin respuesta:\n{sin_respuesta_str}\n" if sin_respuesta_str else ""
            )
            texto = (
                "🌙 Cierre del día.\n"
                f"Cumplidas:\n{cumplidas_str}\n"
                f"Reprogramadas:\n{reprog_str}\n"
                f"{sin_resp_fb}"
                f"Calendar mañana:\n{eventos_manana_str}\n"
                "'Todo lo puedo en Cristo que me fortalece' — Fil 4:13"
            )
        await _enviar(texto, tipo="cierre_dia")
    except Exception as e:
        log.error(f"[COACH] _cierre_dia: {e}")


def _ranking_metas_descuidadas(
    mensajes: list[dict],
    conteo_tareas: dict[str, dict[str, int]] | None = None,
) -> list[dict]:
    """
    Ordena METAS_ACTIVAS de la menos atendida a la más. Score combinado:
    - menciones en chat (peso 1)
    - + tareas cumplidas en últimas 2 semanas (peso 3 — ejecutar > hablar)
    Empate → orden estable de METAS_ACTIVAS.
    """
    conteo_tareas = conteo_tareas or {}
    texto_total = " ".join(m.get("content", "") for m in mensajes).lower()
    conteos = []
    for meta in METAS_ACTIVAS:
        menciones = texto_total.count(meta["key"].lower())
        cumplidas = conteo_tareas.get(meta["key"], {}).get("cumplidas", 0)
        score = menciones + cumplidas * 3
        conteos.append((score, meta))
    conteos.sort(key=lambda x: x[0])
    return [m for _, m in conteos]


async def _check_in_emocional() -> None:
    """Miércoles 19:00 — check-in humano, no atado a una tarea específica.
    Pregunta cómo se siente, qué le trabó esta semana, qué está cargando.
    Usa el historial reciente para hilar con conversaciones previas."""
    try:
        mensajes_recientes = await m_db.mensajes_recientes(dias=7)
        # Resumen muy breve para contexto del LLM
        muestra = mensajes_recientes[-20:] if len(mensajes_recientes) > 20 else mensajes_recientes
        contexto = "\n".join(
            f"{m.get('role','?')}: {m.get('content','')[:140]}" for m in muestra
        ) if muestra else "(sin conversaciones recientes)"

        instr = (
            "Es miércoles 7 PM, mitad de semana. Mandale a Cristian un check-in HUMANO, "
            "no de tareas. No le preguntes por una tarea específica.\n\n"
            f"Conversaciones de los últimos 7 días (para que hagas seguimiento real):\n{contexto}\n\n"
            "Tono: amigo cercano que se preocupa, no coach corporativo. "
            "1) si en el contexto hay algo que mencionó (un problema, una preocupación, "
            "un avance), retómalo con preguntas específicas (no 'cómo va todo'), "
            "2) si no hay nada concreto, pregunta cómo está la semana, qué lo tiene cansado, "
            "qué disfrutó, qué le pesa. "
            "3) cierra con versículo de aliento. Máximo 5 líneas, ZERO lenguaje de productividad."
        )
        try:
            texto = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando check-in emocional: {e}")
            texto = (
                "Hey, mitad de semana. ¿Cómo vas tú, no las tareas? "
                "¿Qué te tiene la cabeza? Si quieres hablar de algo, aquí estoy.\n"
                "'Echa sobre Jehová tu carga, y él te sustentará' — Sal 55:22"
            )
        await _enviar(texto, tipo="check_in_emocional")
    except Exception as e:
        log.error(f"[COACH] _check_in_emocional: {e}")


async def _revision_semanal_metas() -> None:
    """Domingo 20:00 — el coach elige las 2 metas MENOS atendidas (chat + ejecución).
    Score = menciones en chat + cumplidas*3. Las metas con tareas reales pesan más.
    """
    try:
        hoy = datetime.now(TZ_LIMA).date()
        desde = hoy - timedelta(days=14)
        mensajes = await m_db.mensajes_recientes(dias=14)
        conteo_tareas: dict[str, dict[str, int]] = {}
        try:
            conteo_tareas = await r_db.conteo_tareas_por_meta(desde)
        except Exception as e:
            log.warning(f"[COACH] no se pudo obtener conteo por meta: {e}")
        ranking = _ranking_metas_descuidadas(mensajes, conteo_tareas)
        n = min(2, len(ranking))
        metas = ranking[:n]

        def _linea(m):
            b = conteo_tareas.get(m["key"], {"total": 0, "cumplidas": 0})
            return (
                f"- {m['descripcion']} "
                f"[últimas 2 semanas: {b['cumplidas']}/{b['total']} tareas cumplidas]"
            )

        descripciones = "\n".join(_linea(m) for m in metas)

        instr = (
            "Es domingo 8 PM, revisión semanal con Cristian. "
            "Estas son las metas que MENOS hemos atendido (poca conversación + poca ejecución) "
            "en las últimas 2 semanas. No inventes otras metas ni otros números:\n"
            f"{descripciones}\n\n"
            "Tono: amigo cercano, no jefe. Para cada meta: "
            "1) menciona el número concreto (X de Y tareas cumplidas) sin reproche, "
            "2) preguntale honestamente cómo va y si sigue siendo prioridad, "
            "3) qué paso concreto puede dar esta semana. "
            "Cierra con versículo breve. Máximo 8 líneas."
        )
        try:
            texto = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando revisión semanal: {e}")
            keys = ", ".join(m["key"] for m in metas)
            texto = (
                f"📅 Revisión semanal — domingo.\n"
                f"Hablemos de: {keys}.\n"
                "¿Cómo vas con cada una? ¿Qué haces esta semana?\n"
                "'Examínate a ti mismo' — 2 Cor 13:5"
            )
        await _enviar(texto, tipo="revision_semanal")
    except Exception as e:
        log.error(f"[COACH] _revision_semanal_metas: {e}")


async def _resumen_semanal() -> None:
    """Sábado 22:00 — comprime 7 días de conversación en bullets persistidos.
    Permite que el coach 'recuerde' meses atrás sin pagar tokens de miles de mensajes.
    Es silencioso (no manda WhatsApp), corre antes de la revisión semanal del domingo.
    """
    try:
        hoy = datetime.now(TZ_LIMA).date()
        desde = hoy - timedelta(days=7)

        if await res_db.existe_para_semana(hoy):
            log.info(f"[COACH] resumen semanal {hoy.isoformat()} ya existe, skip")
            return

        mensajes = await m_db.mensajes_recientes(dias=7)
        if not mensajes:
            log.info("[COACH] sin mensajes en últimos 7 días, no genero resumen")
            return

        transcripcion = "\n".join(
            f"{m.get('role','?')}: {m.get('content','')[:300]}" for m in mensajes
        )

        instr = (
            f"Resume la conversación con Cristian del {desde.isoformat()} al {hoy.isoformat()}.\n\n"
            f"TRANSCRIPCIÓN:\n{transcripcion}\n\n"
            "Genera un resumen EN BULLETS (5 a 10 puntos) capturando: "
            "1) qué metas tocó y cómo le fue (PTE, Azure, Maestría, MVP, Visa, Sydney), "
            "2) bloqueos o frustraciones que mencionó, "
            "3) compromisos concretos que tomó, "
            "4) cualquier tema personal o emocional relevante. "
            "NO incluyas saludos, versículos, ni elaboración — son hechos para futuro recordatorio. "
            "Cada bullet máximo 1 línea, factual."
        )
        try:
            resumen = await generar_mensaje(instr)
        except Exception as e:
            log.error(f"[COACH] error generando resumen semanal: {e}")
            return

        await res_db.guardar(desde, hoy, resumen)
        log.info(f"[COACH] resumen semanal guardado: {desde}..{hoy} ({len(resumen)} chars)")
    except Exception as e:
        log.error(f"[COACH] _resumen_semanal: {e}")
