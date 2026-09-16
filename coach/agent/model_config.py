"""Configuración del modelo del coach, conmutable por la env `COACH_MODEL`.

Los modelos de razonamiento (gpt-5.x / serie o / luna) tienen dos reglas distintas
a los modelos normales (gpt-4o-mini):

1. `temperature` solo acepta el valor por defecto (1): mandar 0 o 0.7 da error 400.
2. En `/v1/chat/completions` con function tools exigen `reasoning_effort='none'`
   (si no, error 400 "Function tools with reasoning_effort are not supported").

Este módulo centraliza esas diferencias para que cambiar `COACH_MODEL` entre
`gpt-4o-mini` y `gpt-5.6-luna` NO obligue a tocar cada llamada al modelo.
"""
import os

DEFAULT_MODEL = "gpt-4o-mini"

# Prefijos de modelos de razonamiento (no soportan temperature != 1).
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def get_model() -> str:
    """Modelo activo según la env (default seguro: gpt-4o-mini)."""
    return os.getenv("COACH_MODEL", DEFAULT_MODEL)


def is_reasoning_model(model: str | None = None) -> bool:
    """True si el modelo es de razonamiento (luna, gpt-5.x, serie o)."""
    m = (model or get_model()).lower()
    return m.startswith(_REASONING_PREFIXES) or "luna" in m


def chat_kwargs(temperature: float = 1.0) -> dict:
    """kwargs para `client.chat.completions.create()` según el modelo activo.

    - Modelo normal: incluye `model` + `temperature`.
    - Modelo de razonamiento: incluye `model` + `reasoning_effort='none'` y OMITE
      `temperature` (solo acepta 1). `none` mantiene la latencia baja y hace
      compatibles las function tools.
    """
    model = get_model()
    kw: dict = {"model": model}
    if is_reasoning_model(model):
        kw["reasoning_effort"] = "none"
    else:
        kw["temperature"] = temperature
    return kw


def chat_openai_kwargs(temperature: float = 0.3) -> dict:
    """kwargs para construir `langchain_openai.ChatOpenAI(...)` según el modelo.

    ChatOpenAI siempre envía `temperature`; para un modelo de razonamiento se fija
    en 1 (único valor válido) y se añade `reasoning_effort='none'`.
    """
    model = get_model()
    kw: dict = {"model": model}
    if is_reasoning_model(model):
        kw["reasoning_effort"] = "none"
        kw["temperature"] = 1
    else:
        kw["temperature"] = temperature
    return kw
