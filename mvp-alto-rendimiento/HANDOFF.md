# HANDOFF — Proyecto Coach (léeme primero)

> Documento de traspaso para un agente nuevo. Objetivo: entender el proyecto y
> poder **probar el MVP** en minutos. Escrito el 2026-09-10.

---

## 0. TL;DR (30 segundos)

- **Qué es:** un *coach de alto rendimiento* personal para un único usuario
  (Cristian). Le pregunta por sus **metas** y **recordatorios** y responde
  **solo con datos reales** consultados por herramientas — nunca inventa.
- **Qué vas a probar (mañana):** el **MVP** de la Sesión 6, que está en **esta
  carpeta** (`session6/mvp_coach_whatsapp/`). Es un servidor **FastMCP** +
  agente **LangChain** (descubre tools por **MCP**) + backend **FastAPI** +
  frontend estático.
- **Ya está verificado funcionando de punta a punta** (ver §6). Si algo falla,
  casi siempre es (a) entorno de Python sucio o (b) el endpoint gratuito del
  modelo devolviendo `502` transitorios. Ver §5 y §7.
- **Arranque rápido:** §4.

---

## 1. Mapa del proyecto (dónde está todo)

**Local:** `C:\dev\Cursos IA\bsgi\sessionFinal\`
- `session3/` — Ficha 1 (caso de uso) en Word. Completada.
- `session4/` — Ficha 2 (arquitectura cognitiva) en Word + material. Completada.
- `session5/` — PoC en notebook (`PoC_..._completed.executed.ipynb`), **ejecutado, 3/3 PASS**.
- `session6/mvp_coach_whatsapp/` — **EL MVP (esto es lo que se prueba).**

**Repo GitHub:** `https://github.com/cristianuscata/whatsapp-lead-qualifier`
- `master` — agente de leads (producto comercial, no tocar).
- `private_coach` — **coach v1 en PRODUCCIÓN** (VPS Hetzner). No tocar salvo intención.
- `coach-mvp` — **rama nueva** con este MVP en la subcarpeta `mvp-alto-rendimiento/`,
  creada desde `private_coach` **sin modificar la v1**. Commit limpio (autor Cristian).

**Evolución del producto:** v1 (producción) → PoC (Sesión 5) → MVP (Sesión 6, "coach de alto rendimiento").

---

## 2. Cómo funciona el MVP (arquitectura)

```
Usuario (navegador)
  -> index.html + static/app.js       interfaz estática (solo pinta, no toca datos)
  -> api/chat.py (FastAPI)            sirve la UI y expone POST /api/chat
  -> agent.py (LangChain)            agente: system prompt + descubre tools por MCP
  -> api/mcp.py (FastMCP, stateless) expone las tools por el protocolo MCP
  -> mcp_server.py                   define las 2 tools (solo lectura)
  -> data/*.csv                      fuente de verdad (datos SINTÉTICOS)
```

**Clave del patrón:** el agente **descubre** las tools vía
`MultiServerMCPClient` (MCP), **no** importa la función Python directamente.

**Las 2 tools (solo lectura):**
- `consultar_metas(meta="")` → estado y **avance** de una meta (PTE, Azure,
  Maestría, MVP, Visa, Sydney): estado, fecha objetivo, prioridad, % de tareas.
  Sin `meta` → resumen de todas.
- `consultar_recordatorios(estado="")` → recordatorios por estado
  (`pendiente` / `cumplido` / `vencido`), o todos si vacío.

**Límites por diseño:** solo lectura (no crea/edita/borra); si no hay evidencia
lo dice (no inventa); rechaza fuera de alcance (info laboral, terceros, Google
Calendar).

---

## 3. Archivos del MVP (qué es cada uno)

| Archivo | Rol |
|---|---|
| `mcp_server.py` | Define las 2 tools FastMCP + lógica pura (`buscar_metas`, `buscar_recordatorios`). |
| `agent.py` | Agente LangChain (`create_agent`) + `MultiServerMCPClient`. Expone `responder()`. |
| `api/mcp.py` | Sirve `mcp_server` como servicio HTTP (uvicorn, puerto 8001, `stateless_http=True`). |
| `api/chat.py` | Backend FastAPI: sirve la UI y `POST /api/chat` (puerto 8000). |
| `api/index.py` | Versión unificada (backend + MCP en una app) para **Vercel opcional**. |
| `config.py` | Variables de entorno. |
| `prompts.py` | System prompt del coach (alcance + no invención). |
| `index.html`, `static/` | Frontend estático. |
| `data/metas_demo.csv`, `data/recordatorios_demo.csv` | Datos **sintéticos**. |
| `tests/test_tools.py` | Pruebas **offline** de las tools (sin modelo ni red). |
| `tests/test_smoke.py` | Prueba **e2e** (requiere MCP + clave del modelo). |
| `AGENTS.md` | Contexto breve para agentes de código (antes `CLAUDE.md`). |
| `requirements.txt` | Dependencias **pineadas** al set verificado. |

---

## 4. CÓMO PROBARLO (paso a paso) — lo más importante

> **Regla de oro: usa SIEMPRE un entorno virtual LIMPIO.** Mezclar versiones de
> `fastmcp`/`mcp` en un entorno ya usado deja imports rotos (ver §5).

```powershell
cd mvp-alto-rendimiento   # (en el repo; en local: session6/mvp_coach_whatsapp)

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# edita .env y pon tu OPENROUTER_API_KEY (ver §7 sobre la clave)
```

**Prueba offline (rápida, sin modelo — para confirmar que todo está bien):**
```powershell
python tests\test_tools.py      # debe imprimir 4 OK
```

**Demo completa (2 terminales):**
```powershell
# Terminal 1 (servidor MCP / tools):
uvicorn api.mcp:app --reload --port 8001

# Terminal 2 (backend + UI):
uvicorn api.chat:app --reload --port 8000
# abre http://127.0.0.1:8000
```

**Preguntas de demo:**
- `¿cómo voy con PTE?` → usa `consultar_metas`, responde con avance real (~62 %).
- `¿qué tengo pendiente?` → usa `consultar_recordatorios`.
- `¿cómo voy con francés?` → meta inexistente → dice que no hay evidencia (no inventa).
- `resúmeme mis correos del trabajo` → declina (fuera de alcance).
- Apaga la Terminal 1 y pregunta algo → la UI muestra un error legible, sin caerse.

**Prueba e2e por consola (alternativa a la UI):**
```powershell
$env:PYTHONIOENCODING="utf-8"   # importante en Windows (emojis en la respuesta)
python tests\test_smoke.py      # requiere Terminal 1 arriba + clave en .env
```

---

## 5. Versiones que SÍ funcionan (crítico)

`requirements.txt` está **pineado** a este set verificado:
```
fastmcp==2.13.1
mcp==1.30.0
langchain-mcp-adapters==0.3.1
```
(+ fastapi, uvicorn[standard], langchain, langchain-openai, python-dotenv)

**LECCIÓN aprendida (importante):** al instalar/desinstalar versiones repetidas
en el **Python global**, el paquete `fastmcp` quedó corrupto y parecía haber un
"conflicto irresoluble" entre `fastmcp` y `langchain-mcp-adapters`. **No era
real.** En un **venv limpio**, el set de arriba co-instala y funciona. →
**Nunca bisecar versiones sobre un entorno ya contaminado; crear venv nuevo.**

---

## 6. Estado de verificación (qué ya se probó, 2026-09-10)

Todo verificado en un venv limpio con el set pineado:
- ✅ `test_tools.py` → **4/4 OK** (feliz, límite, recordatorios, entrada inválida).
- ✅ Servidor MCP levanta (`StarletteWithLifespan`) y expone las tools por el protocolo.
- ✅ El agente **descubre e invoca** las tools vía `MultiServerMCPClient`.
- ✅ **Chat de punta a punta:** *"¿Cómo voy con PTE?"* → agente → `consultar_metas`
  → modelo → *"PTE activa, avance 5/8 → **62 %**"*, con datos reales, sin inventar.

---

## 7. Gotchas (las cosas que te van a morder)

1. **OpenRouter + Nemotron gratis es LENTO** (~35–110 s por llamada) y el endpoint
   devuelve `502 Service temporarily overloaded` intermitentes. **Reintenta.** No
   es bug del código. (Mismo comportamiento que en el PoC de la Sesión 5.)
2. **Consola de Windows + emojis:** la respuesta del coach trae emojis; imprimir
   sin `PYTHONIOENCODING=utf-8` lanza `UnicodeEncodeError`. Setéalo antes de correr scripts.
3. **No mezclar versiones** `fastmcp`/`mcp` en un entorno usado (ver §5). Venv limpio siempre.
4. **La clave del modelo:** `OPENROUTER_API_KEY` va SOLO en `.env` (ignorado por Git)
   o como variable de entorno. NUNCA en código, notebook, README ni commits.
   ⚠️ **Rotar la clave** que se usó durante el desarrollo (se compartió en chat):
   https://openrouter.ai/keys
5. El modelo del curso es `nvidia/nemotron-3-ultra-550b-a55b:free` (en `config.py` /
   `.env`). Se puede cambiar a cualquier proveedor compatible con la API de OpenAI.

---

## 8. Contexto del sistema v1 (solo si tocas producción — branch `private_coach`)

- **Qué es:** coach personal proactivo por WhatsApp, 1 usuario, en producción
  continua desde 2026-05-18 en un VPS Hetzner CX22.
- **Stack v1:** Supabase/PostgreSQL (coach_mensajes, recordatorios, coach_resumenes),
  Evolution API v2 (gateway WhatsApp/Baileys), GPT-4o-mini, Google Calendar.
- **Lógica v1:** router reactivo de 4 ramas (feedback sí/no/medias por regex,
  consulta Calendar, intención de tarea, chat libre) + APScheduler con 9 jobs por
  reloj (arranque 06:30, check 12:00, cierre 21:00, etc.). Metas en código
  (`METAS_ACTIVAS` en `coach/agent/prompts.py`).
- **Plan v2 (documentado en las fichas):** reemplazar el reloj por un **policy
  engine** determinístico, mover metas a tabla, añadir tabla `intervenciones`
  (anti-repetición), retirar Google Calendar.
- ⚠️ **Riesgo de seguridad conocido en v1:** hay clave de Evolution API, números
  de teléfono e IP del servidor en documentación versionada → conviene rotar y
  limpiar el historial de git antes de compartir el repo.

---

## 9. Decisiones de diseño clave (para no re-litigar)

- **Nivel de autonomía = Cadena/Workflow**, NO agente único. El "cuándo
  intervenir" lo decide código determinístico, no el LLM. Confirmado por el usuario.
- **MVP = ruta B (workflow)** de la guía. Capacidad migrada del PoC = *consultar
  estado de metas/recordatorios* (solo lectura), formalizada como tool MCP.
- **Dejado fuera del MVP** (a propósito): captura de intención y escritura de
  recordatorios, motor proactivo, Supabase/Evolution reales, Google Calendar.

---

## 10. Próximos pasos sugeridos (si el usuario quiere avanzar)

1. Conectar `data/*.csv` a la Supabase real (misma forma de tool, cambia la fuente).
2. Añadir tools de **escritura** con confirmación explícita (crear/actualizar recordatorio, upsert meta).
3. Incorporar el **motor de reglas proactivo** (v2) como servicio aparte.
4. Deploy **opcional en Vercel** (`api/index.py` ya está listo; guía §8).
5. Congelar un **eval set** de intención antes de tocar prompts (evitar regresiones).

---

## 11. Comandos de emergencia / diagnóstico

```powershell
# ¿el MCP responde? (con Terminal 1 arriba)
python -c "import asyncio; from fastmcp import Client; asyncio.run((lambda: None)())"

# recrear entorno desde cero si algo se rompió:
Remove-Item -Recurse -Force .venv ; python -m venv .venv ; .venv\Scripts\Activate.ps1 ; pip install -r requirements.txt

# correr solo las tools (no necesita modelo ni red):
python tests\test_tools.py
```

Si el chat falla con `502` / `overloaded`: es el endpoint gratuito saturado.
Espera y reintenta, o cambia `MODEL_ID` en `.env` a otro proveedor.
