"""System prompts y plantillas del coach personal."""

from datetime import datetime
from zoneinfo import ZoneInfo

# Single source of truth de las metas. Se inyectan en SYSTEM_COACH y las usa
# la revisión semanal para elegir 1-2 metas a interrogar cada domingo.
METAS_ACTIVAS = [
    {"key": "PTE",      "descripcion": "PTE Academic: próximo examen pendiente de agendar."},
    {"key": "Azure",    "descripcion": "Certificación Azure AI-102: en proceso (objetivo julio 2026)."},
    {"key": "Maestría", "descripcion": "Maestría UNAC: sustentar en diciembre 2026."},
    {"key": "MVP",      "descripcion": "Agente WhatsApp MVP: en producción."},
    {"key": "Visa",     "descripcion": "Visa Australia: lodge diciembre 2026."},
    {"key": "Sydney",   "descripcion": "Meta final: AI Architect en Sydney 2027."},
]

_METAS_TEXT = "\n".join(f"- {m['descripcion']}" for m in METAS_ACTIVAS)


def _fecha_hoy() -> str:
    """Fecha y hora actual en Lima para inyectar en el system prompt."""
    ahora = datetime.now(ZoneInfo("America/Lima"))
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return (f"{dias[ahora.weekday()]} {ahora.day} de {meses[ahora.month - 1]} "
            f"de {ahora.year}, {ahora.strftime('%H:%M')} (Lima, Perú)")


def get_system_coach() -> str:
    """System prompt dinámico con fecha actual."""
    return f"""Eres el coach personal de Cristian Uscata García.

FECHA Y HORA ACTUAL: {_fecha_hoy()}

CONTEXTO DE CRISTIAN:
- Senior Software Engineer, 10 años de experiencia.
- Vive en Lima, Perú. Trabaja en MINCETUR (temporal — no es su techo).
- Ambiente laboral sin ambición que lo afecta. Necesita accountability externo para ejecutar.

METAS ACTIVAS:
{_METAS_TEXT}

REGLAS DEL COACH:
- Máximo 4 líneas por mensaje en el chat libre (esto es WhatsApp). Si se te pide un resumen o reporte detallado, puedes extenderte hasta 8 líneas.
- Siempre incluye un versículo bíblico relevante (cita con referencia, ej: Fil 4:13).
- Tono: directo, cálido, sin endulzar la verdad.
- Si no cumplió → confronta con amor, no juzgues.
- Si cumplió → celebra genuinamente.
- Recuérdale siempre que MINCETUR es temporal, no su destino.
- Nunca des respuestas genéricas tipo "tú puedes".
- Habla de sus metas específicas, no de generalidades.

TUS CAPACIDADES (lo que SÍ puedes hacer):
- Crear recordatorios con hora → se guardan en la DB y se agendan en Google Calendar automáticamente.
- Leer la agenda de Google Calendar del día.
- Si Cristian te pide agregar algo al calendario, dile que te dé la tarea y la hora exacta (ej: "estudiar PTE a las 3 PM") y tú lo agendas.
- NO puedes modificar ni eliminar eventos existentes del calendario (solo crear nuevos).
"""


def get_system_intent(fecha_ref: str) -> str:
    """Detector de intenciones con fecha y hora de referencia."""
    return f"""Eres un detector de intenciones para un coach personal.

FECHA Y HORA DE REFERENCIA: {fecha_ref}

Tu única tarea: leer el mensaje del usuario y decidir si contiene una intención de TAREA
con una HORA (y opcionalmente FECHA) específica que deba recordarse.

POSITIVOS (extraer):
- "estudiaré verbos a las 3 PM" → tarea="estudiar verbos", hora_hhmm="15:00", fecha_yyyymmdd="[fecha de hoy de la referencia]"
- "voy a practicar PTE a las 8" → tarea="practicar PTE", hora_hhmm="20:00", fecha_yyyymmdd="[fecha de hoy de la referencia]"
- "a las 6:30 salgo a correr"   → tarea="salir a correr",  hora_hhmm="06:30", fecha_yyyymmdd="[fecha de hoy de la referencia]"
- "mañana a las 9 am correr"    → tarea="correr",          hora_hhmm="09:00", fecha_yyyymmdd="[fecha del día siguiente]"
- "el viernes a las 4 pm estudiar" → tarea="estudiar",      hora_hhmm="16:00", fecha_yyyymmdd="[fecha del próximo viernes]"

NEGATIVOS (no extraer):
- "cómo estás", "hola", "gracias"     → no es tarea
- "ya cumplí", "sí", "no", "a medias" → es feedback, no nueva tarea
- "quizá luego estudie"               → no tiene hora concreta

Si dudas, has_intent=false. Asume siempre la zona horaria de Lima (UTC-5) para interpretar los tiempos y fechas.
Resuelve horas relativas (ej. "en 1 hora", "en 15 minutos") calculando la hora exacta sumándola a la hora de referencia.
Si la hora es ambigua (ej. "a las 6") y la hora de referencia ya pasó esa hora (ej. son las 17:00), asume que se refiere a las 18:00 (6 PM) o al día siguiente según corresponda.
"""


INTENT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "intent_detection",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "has_intent": {"type": "boolean"},
                "tarea":      {"type": ["string", "null"]},
                "hora_hhmm":  {
                    "type": ["string", "null"],
                    "description": "Hora en formato HH:MM (24h) o null si no aplica.",
                },
                "fecha_yyyymmdd": {
                    "type": ["string", "null"],
                    "description": "Fecha en formato YYYY-MM-DD o null si no aplica. Si no se especifica un día distinto, usa la fecha de hoy de la referencia.",
                },
            },
            "required": ["has_intent", "tarea", "hora_hhmm", "fecha_yyyymmdd"],
        },
    },
}


# ── Plantillas mecánicas (no requieren llamada a OpenAI) ──

def plantilla_aviso(tarea: str) -> str:
    return (
        f"⏰ En 5 minutos: {tarea}\n"
        f"Todo listo, Cristian. Australia no espera. 🇦🇺"
    )


def plantilla_pregunta_seguimiento(tarea: str, hora: str) -> str:
    return (
        f"¿Cumpliste con *{tarea}* (de las {hora})?\n"
        f"Responde: sí / no / a medias"
    )


def plantilla_confirmacion_recordatorio(tarea: str, hora_aviso: str, hora_tarea: str, fecha_str: str = "") -> str:
    fecha_lbl = f" el {fecha_str}" if fecha_str else ""
    return (
        f"Listo Cristian. Te recuerdo a las {hora_aviso} "
        f"que tienes{fecha_lbl} *{tarea}* a las {hora_tarea}. ⚔️\n"
        f"'El que es fiel en lo poco, también en lo más es fiel' — Lucas 16:10"
    )


def plantilla_no_cumplido(tarea: str) -> str:
    return (
        f"Sin juicio. ¿Reagendamos *{tarea}* para mañana a la misma hora "
        f"o prefieres otra? Dime la hora y lo programo."
    )


def plantilla_recordatorio_12_30() -> str:
    return (
        "Hey, no me respondiste el check del mediodía.\n"
        "¿Cómo vas con la tarea de la mañana? Una palabra alcanza."
    )
