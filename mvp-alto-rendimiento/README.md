# MVP · Coach de alto rendimiento — accountability de metas y recordatorios

MVP construido a partir del PoC de la sesión 5 (coach personal proactivo por
WhatsApp). Formaliza **una** capacidad validada del PoC —consultar el estado
de las metas y recordatorios del usuario— como dos **tools MCP de solo
lectura**, y la expone a través de un agente LangChain, un backend FastAPI y
una interfaz estática.

> **Ruta del PoC:** B (workflow / cadena). En el MVP la capacidad de consulta
> se envuelve como tool FastMCP, tal como pide la guía para las rutas B/C.

## Qué hace y qué no

- **Sí:** responde preguntas sobre el avance de las metas (PTE, Azure,
  Maestría, MVP, Visa, Sydney) y sobre recordatorios (pendientes, cumplidos,
  vencidos), apoyándose siempre en datos verificados por sus tools.
- **No:** no crea, modifica ni borra nada (solo lectura); no maneja
  información laboral del usuario, ni datos de terceros, ni Google Calendar;
  no inventa datos — si no hay evidencia, lo dice.

## Arquitectura

```
Usuario (navegador)
  -> index.html + static/app.js        interfaz estática
  -> api/chat.py (FastAPI)             sirve la UI y expone POST /api/chat
  -> agent.py                         agente LangChain, descubre tools vía MCP
  -> api/mcp.py (FastMCP, stateless)   expone consultar_metas / consultar_recordatorios
  -> data/*.csv                       fuente de verdad (datos sintéticos)
```

El agente **descubre** las tools por MCP (`MultiServerMCPClient`); no importa
la función Python directamente.

## Requisitos

- Python 3.10+
- Una clave de OpenRouter (modelo gratuito `nvidia/nemotron-3-ultra-550b-a55b:free`)
  u otro proveedor compatible con la API de OpenAI.

## Instalación

```bash
python -m venv .venv
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env      # y completa OPENROUTER_API_KEY
```

## Ejecución (local, dos terminales)

**Terminal 1 — servidor MCP (tools):**
```bash
uvicorn api.mcp:app --reload --port 8001
# queda en http://127.0.0.1:8001/
```

**Terminal 2 — backend + UI:**
```bash
uvicorn api.chat:app --reload --port 8000
# abre http://127.0.0.1:8000
```

## Pruebas

- **Tools (offline, sin modelo ni red):**
  ```bash
  python tests/test_tools.py
  ```
  Cubre caso feliz, caso límite sin evidencia y entrada inválida.

- **Humo de punta a punta (requiere MCP en 8001 + clave):**
  ```bash
  python tests/test_smoke.py
  ```

## Casos de aceptación (para la demo)

| Caso | Pregunta de ejemplo | Comportamiento esperado |
|---|---|---|
| Feliz | `¿cómo voy con PTE?` | usa `consultar_metas`, responde con avance real |
| Feliz | `¿qué tengo pendiente?` | usa `consultar_recordatorios`, lista pendientes |
| Límite | `¿cómo voy con francés?` | meta inexistente → dice que no hay evidencia, no inventa |
| Fuera de alcance | `resúmeme mis correos del trabajo` | declina: fuera de alcance (no laboral) |
| Tool inválida | (interno) estado de recordatorio no válido | error claro, la app no se cae |
| MCP no disponible | apaga la Terminal 1 y pregunta algo | la UI muestra un error legible, sin caerse |

## Seguridad y datos

- `data/*.csv` son **sintéticos**; no hay datos personales reales ni secretos.
- La clave vive solo en `.env` (ignorado por Git). Nunca en código ni en el README.
- Tools de **solo lectura**; permisos mínimos.

## Registro de decisiones (PoC → MVP)

- **Reutilizado del PoC:** el dominio (metas/recordatorios del coach), el
  proveedor de modelo (OpenRouter + Nemotron) y la política de no invención.
- **Formalizado como tool MCP:** la consulta de estado de metas/recordatorios.
- **Dejado fuera del MVP:** captura de intención y escritura de recordatorios
  (el PoC lo hacía; aquí el alcance es solo consulta), el motor de reglas
  proactivo, Supabase/Evolution reales y Google Calendar.

## Despliegue opcional en Vercel

No es requisito de entrega. `api/index.py` trae la versión unificada
(backend + MCP en una sola app) lista para intentar el paso 8 de la guía.

## Estado de verificación (2026-09-10)

Verificado en un entorno limpio (`.venv`) con el set fijado en `requirements.txt`:

- **`python tests/test_tools.py` → 4/4 OK** (caso feliz, límite, recordatorios,
  entrada inválida). Reproducible, sin modelo ni red.
- **Servidor FastMCP corriendo (stateless_http):** `uvicorn api.mcp:app --port 8001`
  levanta y expone las tools por el protocolo MCP.
- **El agente descubre las tools vía `MultiServerMCPClient`** (no las importa
  directo): `client.get_tools()` devuelve `['consultar_metas',
  'consultar_recordatorios']`, y al invocarlas responden con datos reales
  (p.ej. `consultar_metas('Azure')` → meta Azure, avance 30 %).
- **Chat de punta a punta — VERIFICADO:** con `OPENROUTER_API_KEY` configurada,
  la pregunta *"¿Cómo voy con la meta PTE?"* recorrió agente → tool MCP
  `consultar_metas` → modelo, y devolvió una respuesta apoyada en los datos
  (Avance 5/8 tareas → **62 %**), sin inventar. El modelo gratuito Nemotron es
  lento y el endpoint devuelve 502 intermitentes (reintenta si ocurre).

### Nota de versiones (importante)

Las versiones de `fastmcp` / `mcp` / `langchain-mcp-adapters` están **fijadas**
en `requirements.txt` a un set verificado (`fastmcp==2.13.1`, `mcp==1.30.0`,
`langchain-mcp-adapters==0.3.1`) porque el ecosistema MCP cambia rápido y
mezclar versiones deja imports rotos. **Instala siempre en un entorno limpio**
(`python -m venv .venv`); reinstalar fastmcp/mcp sobre un entorno ya usado puede
dejar el paquete `fastmcp` inconsistente. Es el riesgo que la guía advierte
("las APIs cambian rápido; fija versiones").
