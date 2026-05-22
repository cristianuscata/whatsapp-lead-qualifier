# Análisis de modelos LLM — decisión pendiente

Estado: **evaluación, no implementado**. El proyecto sigue corriendo `gpt-4o-mini` para todo.
Última revisión: 2026-05-22.

Si después de leer esto decidís migrar, actualizá CLAUDE.md (sección stack)
con el setup final y borrá o archivá este doc.

---

## Estado actual

Todo el coach usa `gpt-4o-mini` (ver `coach/agent/openai_coach.py:78, 91`).

**Costo real estimado:** ~$0.30–$0.50/mes.

**Gasto por día típico:**
- 2 calls fijos del scheduler (arranque 06:30, cierre 21:00).
- 1 call por mensaje de chat libre (incluye historial 30 msgs + eventos Calendar
  hoy/mañana + últimos 3 resúmenes semanales → ~3–5K tokens input).
- 1 call por intent detection cuando creás recordatorio.
- 1 call por feedback sí/no/medias.
- 2 calls extra por evento de Calendar externo (aviso + seguimiento).
- Avisos 5min antes / preguntas 30min después / check mediodía → **plantillas, no LLM**.

Con $5 de crédito en OpenAI, te duran ~10–15 meses.

---

## Dónde gpt-4o-mini se queda corto (uso real del coach)

| Caso de uso | Función | Mini está bien | Mini se queda corto |
|---|---|---|---|
| Intent detection | `detectar_recordatorio` | ✅ tarea estructurada | — |
| Avisos / preguntas | plantillas hardcoded | ✅ (no llama LLM) | — |
| Arranque/cierre del día | `_arranque_dia`, `_cierre_dia` | ✅ listas estructuradas | versículos algo genéricos |
| Celebración / follow-up feedback | `generar_mensaje` tras sí/no/medias | ⚠️ funciona | tono menos calibrado |
| **Chat libre** | `responder_chat` | ❌ | matices emocionales, hilar contexto |
| **Check-in emocional miércoles** | `_check_in_emocional` | ❌ | leer subtexto, retomar conversaciones previas |
| **Revisión semanal metas** | `_revision_semanal_metas` | ❌ | sintetizar patrones de 14 días |

Las 3 funciones en negrita son donde un modelo mejor cambia notoriamente la experiencia.

---

## Comparación de modelos para el chat libre

### Escenario de prueba

Cristian escribe: *"hermano, no pude levantarme hoy, otra vez. Siento que no avanzo nada, soy un fracaso."*

(Va a `responder_chat`. System prompt: amigo cercano, tuteo peruano, sin sermón, máx 4–5 líneas, versículo al cierre.)

### Respuestas caracterizadas

**`gpt-4o-mini`** (hoy)
> "Hermano, no eres un fracaso. Todos tenemos días así. Mañana es una nueva
> oportunidad para levantarte temprano. ¿Qué crees que te impidió hoy?
> 'Aunque caiga el justo, no quedará postrado' — Sal 37:24."

Correcto pero plantilla. Pregunta diagnóstica genérica.

**`gpt-4o`**
> "Para. Un día en cama no te define. Lo que sí me dice algo es que dijiste
> 'otra vez' — eso no es pereza, es algo más cargado. ¿Estás durmiendo bien,
> o llegás molido a las 11 de la noche? 'El que confía en Jehová prosperará' — Prov 28:25."

Capta el "otra vez" (subtexto), va al patrón no al evento, pregunta no genérica.

**`Claude Sonnet 4.6`**
> "Hermano, 'fracaso' es palabra grande para un día en cama. ¿Qué pasó anoche?
> Porque normalmente cuando uno no se puede parar, el problema empezó la noche
> anterior, no en la mañana. Cuéntame. 'Cansados estaréis, pero levantaréis
> vuelo como las águilas' — Is 40:31."

Reescribe la palabra cargada, insight de causa-noche-anterior, español más natural,
versículo contextual (cansancio, no caída moral).

**`Claude Haiku 4.5`**
> "Hermano, un día en cama no te hace fracaso. Pero dijiste 'otra vez' —
> ¿qué pasó esta semana que te tiene así? No huyas de la pregunta.
> 'No temas, porque yo estoy contigo' — Is 41:10."

Casi tan bueno como Sonnet en este caso, más directo. A 1/3 del costo de Sonnet.

**`Gemini 2.0 Flash`**
> "Cristian, no te llames fracaso por un día. Levantarse cuesta. Mañana intentas
> de nuevo, paso a paso. ¿Qué te ayudaría esta noche para acostarte temprano?
> 'Todo lo puedo en Cristo' — Fil 4:13."

Correcto, pero formal/neutro. Versículo reciclado. Tono menos peruano.

---

## Tabla de costos y fit

Precios aproximados a 2026-05 (verificá los actuales antes de migrar):

| Modelo | $ in/out por 1M tokens | Tu costo/mes estimado | Fit para tu coach |
|---|---|---|---|
| `gpt-4o-mini` (hoy) | $0.15 / $0.60 | ~$0.40 | ⭐⭐⭐ funciona para todo lo estructurado |
| `gpt-3.5-turbo` | $0.50 / $1.50 | ~$1 | ❌ peor que mini, no vale |
| `gpt-4o` | $2.50 / $10 | ~$6 | ⭐⭐⭐⭐ buen salto en matiz |
| `gpt-4-turbo` | $10 / $30 | ~$25 | ❌ obsoleto, gpt-4o lo iguala más barato |
| `Claude Haiku 4.5` | $1 / $5 | ~$3 | ⭐⭐⭐⭐ mejor español, casi como Sonnet |
| `Claude Sonnet 4.6` | $3 / $15 | ~$8 | ⭐⭐⭐⭐⭐ sweet spot para chat libre |
| `Claude Opus 4.7` | $15 / $75 | ~$40 | ❌ overkill |
| `Gemini 2.0 Flash` | ~$0.10 / $0.40 | ~$0.25 | ⭐⭐ barato pero plano emocional |
| `Gemini 2.5 Pro` | ~$1.25 / $5 | ~$3 | ⭐⭐⭐ razonamiento bueno, español OK |

---

## Plan híbrido recomendado

Parametrizar el modelo por función en lugar de migrar todo al mismo modelo:

| Función | Modelo sugerido | Razón |
|---|---|---|
| `detectar_recordatorio` | `gpt-4o-mini` | Estructurado, mini sobra |
| `responder_chat` | `Claude Sonnet 4.6` o `gpt-4o` | Donde más se nota la mejora |
| `generar_mensaje` (arranque, cierre, avisos) | `Claude Haiku 4.5` o `gpt-4o-mini` | Calor sin gastar mucho |
| `_check_in_emocional` (miércoles) | `Claude Sonnet 4.6` | Crítico, 4 veces/mes |
| `_revision_semanal_metas` (domingo) | `Claude Sonnet 4.6` | Síntesis de 14 días, ~4/mes |

**Costo total estimado del híbrido: ~$3–5/mes.**

---

## OpenRouter como integración

Para implementar el plan híbrido sin manejar dos SDKs y dos cuentas: usar
[OpenRouter](https://openrouter.ai) como proxy. Te permite usar el SDK de
OpenAI que ya tenés y cambiar de modelo con solo un string.

### Cambio en código

`coach/agent/openai_coach.py:12`:

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)
```

Y en cada llamada, pasar `model=...` distinto según la función. Cero refactor
de arquitectura.

### IDs de modelos en OpenRouter (verificar en https://openrouter.ai/models — cambian)

- `openai/gpt-4o-mini`
- `openai/gpt-4o`
- `anthropic/claude-sonnet-4.6`
- `anthropic/claude-haiku-4.5`
- `google/gemini-2.0-flash`

### Pros

- **Un solo SDK** (el de OpenAI). Cambio mínimo en el código.
- **Una sola factura, un solo saldo** que recargás.
- **Switch de modelo = cambiar un string** en cada función.
- Acceso a todos los proveedores sin abrir cuentas separadas.
- Fallback automático opcional (si Anthropic se cae, rutea a otro modelo).

### Trade-offs

- **Latencia extra**: +100–300ms por el hop. Imperceptible en chat conversacional.
- **Markup ~5%** al recargar saldo vía Stripe. Despreciable para tu volumen.
- **Punto único de falla**: si OpenRouter se cae, se caen TODOS los modelos.
  Aceptable para MVP personal, no para producción crítica.
- **Features avanzadas**: prompt caching de Anthropic (ahorra ~50% del system
  prompt grande), structured outputs de OpenAI, batch API — pueden no estar
  expuestos o comportarse distinto. Para chat completions normales (lo que
  usás hoy) no hay problema.
- **Privacidad**: tus mensajes pasan por servidores de OpenRouter. Tienen
  política de no-logging configurable, pero es una capa más en la ruta de
  datos. Vale tenerlo en mente para mensajes íntimos del coach.

### Cuándo NO usarlo

Si el coach deja de ser personal y se convierte en producto comercial, ir
directo a cada proveedor (elimina dependencia y latencia extra).

---

## Decisión

**Pendiente.** Opciones en orden de mi preferencia para este MVP:

1. **OpenRouter + híbrido** (~$3–5/mes): máxima flexibilidad, código limpio,
   podés experimentar.
2. **OpenAI directo, mover solo `responder_chat` y `_check_in_emocional` a
   `gpt-4o`** (~$3/mes): cero dependencia nueva, upgrade quirúrgico.
3. **Quedarse en `gpt-4o-mini`** ($0.40/mes): funciona bien, el upgrade es
   "calidad de vida" no "necesario".

Antes de decidir, vale la pena probar manualmente algunos prompts del coach
real en https://platform.openai.com/playground y https://console.anthropic.com
para ver la diferencia con tus propios ojos.
