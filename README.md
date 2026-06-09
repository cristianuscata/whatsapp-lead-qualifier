# WhatsApp Personal Coach 🎯

Coach personal por WhatsApp para Cristian. Solo responde a un número específico (`CRISTIAN_PHONE`), detecta intenciones de tareas con hora, envía recordatorios proactivos en momentos clave del día y mantiene una conversación con tono de coach (versículos bíblicos + accountability directo).

**Stack:** FastAPI · OpenAI GPT-4o-mini · Supabase · Google Calendar · APScheduler · Evolution API v2 (WhatsApp gateway) · Docker.

---

## 📐 Arquitectura

```
┌──────────────┐    ┌───────────────────────────────┐    ┌──────────────┐
│  WhatsApp    │───▶│  Evolution API (:8081 ext,    │───▶│  agent       │
│  (Cristian)  │    │   :8080 interno) — Baileys    │◀───│  FastAPI     │
│              │◀───│                               │    │  (:8000)     │
└──────────────┘    └────────────┬──────────────────┘    └──────┬───────┘
                                 │                              │
                          ┌──────▼──────┐               ┌───────┴────────┐
                          │ PostgreSQL  │               │ OpenAI         │
                          │ (Evolution) │               │ Supabase       │
                          └─────────────┘               │ Google Calendar│
                                                        │ APScheduler    │
                                                        └────────────────┘
```

Tres containers en `docker-compose.yml`:

| Servicio | Puerto interno | Port-forward | Rol |
|---|---|---|---|
| `agent` | 8000 | 8000 | FastAPI + scheduler del coach |
| `evolution` | 8080 | 8081 | Gateway WhatsApp (Baileys) |
| `evolution-postgres` | 5432 | — | DB interna de Evolution |

Externos:
- **Supabase** — DB de app (tablas `recordatorios` y `coach_mensajes`).
- **Google Calendar** — eventos bidireccional (crear al armar recordatorio, leer para briefing del día y detección de conflictos). Scope `calendar.events`.

---

## 🛠️ Prerequisitos

- Docker Desktop
- Cuenta en [Supabase](https://supabase.com) (free tier sobra)
- API key de [OpenAI](https://platform.openai.com) con saldo
- Proyecto en [Google Cloud Console](https://console.cloud.google.com) con Calendar API habilitada y OAuth Client tipo **Desktop** (genera `credentials.json`)
- Dos WhatsApp distintos: uno será el **bot**, el otro es **vos** (`CRISTIAN_PHONE`)

---

## ⚙️ Setup inicial

### 1. `.env`

Crear `.env` en la raíz con:

```
# OpenAI
OPENAI_API_KEY=sk-proj-...

# EvolutionAPI (URLs Docker — agent llama por nombre de servicio)
EVOLUTION_URL=http://evolution:8080
EVOLUTION_API_KEY=crisagent2024
EVOLUTION_INSTANCE=mi-instancia

# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJ...                # service_role key

# Coach
CRISTIAN_PHONE=51XXXXXXXXX@s.whatsapp.net   # tu número personal (remitente)
COACH_ENABLED=true

# Google Calendar
GOOGLE_CALENDAR_ID=primary
GOOGLE_CREDS_DIR=/app/google                 # path DENTRO del container
```

> `EVOLUTION_URL` usa `http://evolution:8080` (nombre de servicio + puerto interno), no `localhost`. Si volvés a modo dev con uvicorn local, cambiar a `http://localhost:8081`.

### 2. Tablas en Supabase

En **SQL Editor** correr:

```sql
CREATE TABLE recordatorios (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tarea            text NOT NULL,
    hora_recordar    time NOT NULL,
    hora_seguimiento time NOT NULL,
    fecha            date NOT NULL,
    avisado          boolean DEFAULT false,
    cumplido         boolean DEFAULT NULL,
    reprogramado     boolean DEFAULT false,
    created_at       timestamptz DEFAULT now()
);

CREATE TABLE coach_mensajes (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role       text NOT NULL CHECK (role IN ('user', 'assistant')),
    content    text NOT NULL,
    tipo       text DEFAULT 'chat',
    created_at timestamptz DEFAULT now()
);
```

### 3. Google Calendar (token OAuth)

Necesitás generar `google/token.json` **una sola vez** desde tu laptop (requiere browser). Después el container lo monta y se auto-refresca.

```powershell
# Instalar deps de Google en tu Python local
python -m pip install google-auth-oauthlib google-api-python-client python-dotenv

# Indicar la carpeta local (sobrescribe el path del container que vive en .env)
$env:GOOGLE_CREDS_DIR = "C:\dev\MVP\whatsapp-lead-qualifier\google"

# Generar token (abre browser → autorizar con tu Gmail)
python -m coach.integrations.calendar_auth
```

Asegurate de que `google/credentials.json` exista antes de correr el script (lo bajás de Google Cloud Console). El resultado es `google/token.json` — el container lo lee del volumen montado.

> 🚨 **Publicá tu OAuth app.** En Google Cloud Console → OAuth consent screen → **PUBLISH APP**. Si la dejás en modo "Testing", el refresh token expira cada **7 días** y vas a tener que regenerar `token.json` cada semana. Publicada, no expira (salvo cambio de password de Gmail, revocación manual, o inactividad >6 meses).

### 4. Levantar todo

```bash
docker compose up -d
```

Verificar:
```bash
docker compose ps
curl http://localhost:8000/health
docker logs whatsapp-lead-qualifier-agent-1 --tail 20 | grep COACH
# → debe aparecer: [COACH] scheduler iniciado (TZ=America/Lima)
```

### 5. Vincular WhatsApp (primera vez)

> 🚨 **El QR vincula al WhatsApp del celular que escanea como el BOT.** Si escaneás desde tu celular personal, tu personal se convierte en el bot y los recordatorios te llegarían "de vos mismo". **Escaneá desde el celular del bot** (otro número distinto a `CRISTIAN_PHONE`).

```powershell
# Crear instancia
$body = @{ instanceName = "mi-instancia"; integration = "WHATSAPP-BAILEYS"; qrcode = $true } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8081/instance/create" -Method Post `
    -Headers @{ "apikey" = "crisagent2024" } -Body $body -ContentType "application/json"

# Traer el QR como imagen
$resp = Invoke-RestMethod -Uri "http://localhost:8081/instance/connect/mi-instancia" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }
$b64 = $resp.base64 -replace '^data:image/png;base64,', ''
[IO.File]::WriteAllBytes("qr.png", [Convert]::FromBase64String($b64))
Start-Process qr.png

# Verificar (debe mostrar connectionStatus=open y ownerJid del bot)
Invoke-RestMethod -Uri "http://localhost:8081/instance/fetchInstances" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }
```

---

## 🚀 Cómo opera el coach

### Mensajes proactivos (zona horaria America/Lima)

| Hora | Qué hace |
|---|---|
| **06:30** | Arranque del día: tareas del día **+ eventos de Google Calendar** + versículo + pregunta de acción |
| **12:00** | Check de la tarea de la mañana (si había alguna) |
| **12:30** | Si no respondiste el check de las 12:00 → recordatorio |
| **21:00** | Cierre del día: balance + reprograma no cumplidas + **vista de mañana con eventos de Calendar** + versículo |
| **Domingos 20:00** | Revisión semanal de metas: toma 2 metas al azar de `METAS_ACTIVAS` y pregunta cómo vas |
| **Cada minuto** | Revisa recordatorios pendientes (5 min antes / 30 min después) |
| **Cada 5 min** | Tick de eventos de Calendar (avisa cuando empieza un evento del día) |

### Flujo de un recordatorio

Vos escribís: *"voy a practicar PTE a las 8 PM"*
1. El coach detecta la intención (tarea + hora) y la guarda en `recordatorios`.
2. Consulta Google Calendar — si hay un evento que choca con esa hora, te lo advierte (no bloquea, solo informa).
3. Crea el evento en tu Calendar y te confirma con versículo.
4. A las 19:55 → aviso: *"⏰ En 5 minutos: practicar PTE"*.
5. A las 20:30 → pregunta: *"¿Cumpliste con practicar PTE?"*.
6. Respondés **sí / no / a medias** y el coach reacciona:
   - **sí** → celebra con versículo
   - **no** → ofrece reagendar a la misma hora mañana
   - **a medias** → confronta con amor, empuja a ejecución completa

### Conversación libre

Cualquier otro mensaje cae a chat libre. El coach responde usando el `SYSTEM_COACH` (contexto de Cristian, metas, tono, reglas), recordando los últimos 10 mensajes.

---

## 🩺 Troubleshooting — "El coach no responde"

En orden de frecuencia real:

### 1. ¿Están arriba los 3 containers?
```bash
docker compose ps
```
Si falta `agent`: `docker compose up -d`.

### 2. ¿WhatsApp está vinculado al número correcto?
```powershell
Invoke-RestMethod -Uri "http://localhost:8081/instance/fetchInstances" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }
```
`connectionStatus=open` y `ownerJid=<el bot>@s.whatsapp.net`. Si está en otro número, escaneaste desde el celular equivocado.

### 3. ¿Las URLs entre containers están bien? (causa más común post-cambios)

| Caller | Target | URL correcta |
|---|---|---|
| `evolution` → `agent` | webhook | `WEBHOOK_GLOBAL_URL=http://agent:8000/webhook` en `docker-compose.yml` |
| `agent` → `evolution` | enviar mensaje | `EVOLUTION_URL=http://evolution:8080` en `.env` |
| Vos desde el host | cualquiera | `http://localhost:8000` o `:8081` |

Síntomas:
- `evolution` log: `AxiosError: timeout of 60000ms exceeded` → su `WEBHOOK_GLOBAL_URL` está mal.
- `agent` log: `All connection attempts failed` al enviar → su `EVOLUTION_URL` está mal.

### 4. ¿Cambiaste `.env`?
`.env` se lee al **crear** el container, no al restart. Recreá:
```bash
docker compose up -d --force-recreate agent
```

### 5. ¿Sesión de WhatsApp caída?
Si ya no aparece la instancia o `connectionStatus != open`, borrar y volver a escanear:
```powershell
Invoke-RestMethod -Uri "http://localhost:8081/instance/delete/mi-instancia" `
    -Method Delete -Headers @{ "apikey" = "crisagent2024" }
# después rehacer paso 4 del Setup
```

⚠️ **Nunca usar `docker compose down -v`** salvo que quieras wipear la sesión de WhatsApp. El `-v` borra el volumen `evolution_instances`.

---

## 🩺 Troubleshooting — Google Calendar

### Síntoma: el bot responde normal pero los eventos no se crean / no lee Calendar

Calendar falla con **soft-fail** — el código atrapa la excepción, loguea `[CALENDAR] no pude listar eventos: ...` y sigue respondiendo. Por eso parece que "todo anda" pero los eventos nunca se crean.

```bash
docker logs whatsapp-lead-qualifier-agent-1 --since 24h 2>&1 | grep CALENDAR | tail -20
```

#### Error `invalid_grant: Bad Request`

El refresh token fue revocado. Causas:

1. **OAuth app en modo "Testing"** — Google revoca tokens cada 7 días. **Fix definitivo:** Google Cloud Console → OAuth consent screen → **PUBLISH APP**.
2. Cambio de password de Gmail.
3. Revocación manual desde [myaccount.google.com/permissions](https://myaccount.google.com/permissions).
4. Inactividad >6 meses.

**Cómo regenerar el `token.json`:**

```powershell
# En tu laptop
Remove-Item C:\dev\MVP\whatsapp-lead-qualifier\google\token.json
$env:GOOGLE_CREDS_DIR = "C:\dev\MVP\whatsapp-lead-qualifier\google"
python -m coach.integrations.calendar_auth   # abre browser → autorizar
scp C:\dev\MVP\whatsapp-lead-qualifier\google\token.json root@<IP_SERVER>:/root/whatsapp-lead-qualifier/google/
```

```bash
# En el server
cd /root/whatsapp-lead-qualifier && docker compose restart agent
docker logs whatsapp-lead-qualifier-agent-1 --tail 30 -f
# esperá un tick (cada 5 min :30) sin warning de CALENDAR
```

#### Error `No hay token de Google Calendar` / `FileNotFoundError`

El volumen `./google` no está montado o el archivo no existe dentro del container.

```bash
docker compose exec agent ls -la /app/google/
# debe mostrar credentials.json y token.json
```

Si falta, copiar de nuevo: `scp -r google/ root@<IP>:/root/whatsapp-lead-qualifier/`.

---

## 🏗️ Estructura del proyecto

```
.
├── main.py                       # FastAPI: webhook + lifespan del scheduler
├── whatsapp.py                   # cliente compartido para enviar por Evolution
├── coach/
│   ├── main.py                   # es_cristian() + iniciar_coach()
│   ├── scheduler.py              # APScheduler con los 5 jobs
│   ├── agent/
│   │   ├── prompts.py            # SYSTEM_COACH + SYSTEM_INTENT + plantillas
│   │   ├── intent.py             # detección de intenciones (json_schema strict)
│   │   ├── openai_coach.py       # responder_chat() + generar_mensaje()
│   │   └── coach.py              # pipeline: feedback → intent → chat libre
│   ├── db/
│   │   ├── recordatorios.py      # CRUD recordatorios + queries del scheduler
│   │   └── mensajes.py           # historial coach_mensajes
│   └── integrations/
│       ├── calendar.py           # crear_evento / listar_eventos / detectar_conflicto
│       └── calendar_auth.py      # script one-time para generar token.json
├── google/                       # credentials.json + token.json (gitignored)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── CLAUDE.md                     # contexto para sesiones de Claude Code
└── README.md                     # este archivo
```

---

## 🌍 Deploy a producción

**Recomendado: Hetzner Cloud CX22 (~$4-6/mes)** — VPS Ubuntu, instalás Docker y replicás exactamente el setup local. Ver `CLAUDE.md` para los pasos detallados.

Railway funciona pero cuesta el doble (~$10-15/mes) y requiere definir cada servicio por separado. Solo vale la pena si querés CI/CD automático.

---

## 🛠️ Próximos pasos pendientes

- [ ] Persistir `event_id` de Calendar en columna `google_event_id` de `recordatorios` (hoy solo se loguea; permitiría editar/borrar el evento cuando se reprograma)
- [ ] Envolver llamadas síncronas de Google SDK en `asyncio.to_thread()` (`listar_eventos` bloquea el event loop ~1s — aceptable para v1, no escala si crece el uso)
- [ ] Evaluar migración de parte del pipeline a Sonnet/gpt-4o vía OpenRouter (ver `MODELOS_LLM.md`)
