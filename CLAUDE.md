# Contexto para Claude — whatsapp-lead-qualifier

Notas que sobreviven entre sesiones y máquinas. Si recién abrís este repo,
leé esto antes de cualquier cambio.

---

## Estado del proyecto

Dos branches con propósitos distintos:

- **`master`** → agente de leads (clasifica frío/tibio/caliente, notifica al vendedor). Producto comercial.
- **`private_coach`** ← **este branch** — coach personal privado de Cristian. **Ya no contiene código del agente de leads** (se limpió el 2026-05-17). Es independiente.

En `private_coach`, `main.py` solo procesa mensajes de `CRISTIAN_PHONE`. Cualquier otro número se ignora silenciosamente (log + 200 OK).

`COACH_ENABLED=false` en `.env` desactiva el scheduler y descarta mensajes (kill switch para mantenimiento sin tirar el container).

---

## Stack y servicios

Tres containers en `docker-compose.yml`:

| Servicio | Puerto interno | Port-forward | Qué hace |
|---|---|---|---|
| `agent` | 8000 | 8000 | FastAPI + scheduler del coach |
| `evolution` | 8080 | 8081 | Gateway WhatsApp (EvolutionAPI v2, Baileys) |
| `evolution-postgres` | 5432 | — | DB interna de Evolution (separada de Supabase) |

Externos:
- **Supabase** — DB de app (tablas `mensajes`, `recordatorios`, `coach_mensajes`).
- **OpenAI** — GPT-4o-mini para clasificación, intent detection y respuestas.

---

## Gotcha #1 — URLs entre containers (CRÍTICO)

**Esto causó más de una hora de debug. Si el bot no responde y todo parece estar arriba, revisá esto PRIMERO.**

Cuando todo corre en Docker, los containers se hablan por **nombre de servicio + puerto interno**. `localhost` adentro de un container es el container mismo, no el host.

| Caller | Target | URL correcta |
|---|---|---|
| `agent` container | `evolution` | `EVOLUTION_URL=http://evolution:8080` en `.env` |
| `evolution` container | `agent` | `WEBHOOK_GLOBAL_URL=http://agent:8000/webhook` en `docker-compose.yml` |
| Vos (terminal/PowerShell en el host) | cualquiera | `http://localhost:8000` o `http://localhost:8081` |

Síntomas:
- `evolution` log: `AxiosError: timeout of 60000ms exceeded` → su `WEBHOOK_GLOBAL_URL` está mal.
- `agent` log: `Error de conexión enviando a ...: All connection attempts failed` → su `EVOLUTION_URL` está mal.

Si volvés a **modo dev** (uvicorn local + solo evolution en Docker), invertir: `EVOLUTION_URL=http://localhost:8081` y `WEBHOOK_GLOBAL_URL=http://host.docker.internal:8000/webhook`.

---

## Gotcha #2 — QR de WhatsApp

El QR vincula la cuenta de WhatsApp del **celular que escanea** como el bot. Cualquiera con WhatsApp puede ser el bot. Si escaneás del celular equivocado, Evolution queda `connected: open` pero al número equivocado, y nada responde porque los mensajes llegan a otra parte.

Verificar siempre con:
```powershell
Invoke-RestMethod -Uri "http://localhost:8081/instance/fetchInstances" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }
```
`ownerJid` debe ser el número que vos esperás que sea el bot (actualmente `51958213628`).

El número del coach (`CRISTIAN_PHONE` en `.env`) es **el remitente** (tu celular personal `51965373728@s.whatsapp.net`), NO el bot. El bot escucha; el coach responde a un remitente específico.

---

## Gotcha #3 — `.env`

Solo existe `.env` (no `.env.example`). Ya tiene todos los secretos reales. Está en `.gitignore`. Cuando reinstales en otra máquina, hay que recrearlo manualmente con los valores reales. Variables actuales:

```
OPENAI_API_KEY=...
EVOLUTION_URL=http://evolution:8080      # ← modo Docker, NO localhost
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE=mi-instancia
SUPABASE_URL=...
SUPABASE_KEY=...                          # service_role key
CRISTIAN_PHONE=51965373728@s.whatsapp.net
COACH_ENABLED=true
GOOGLE_CALENDAR_ID=primary
GOOGLE_CREDS_DIR=/app/google
```

⚠️ Cambios al `.env` requieren recrear el container: `docker compose up -d --force-recreate agent`. Un simple restart NO toma las variables nuevas (env se lee al crear el container).

---

## Despliegue — Hetzner Cloud CX22 (producción desde 2026-05-18)

**VPS:** IP `178.105.163.82`, Ubuntu 24.04, CX22 (~$4-6/mes). Ya está corriendo.

**Para retomar en el server:**
```bash
ssh root@178.105.163.82
cd whatsapp-lead-qualifier
docker compose ps
```

**Deploy desde cero en otra máquina:**
1. Crear VPS CX22 en Hetzner con Ubuntu 24.04.
2. `curl -fsSL https://get.docker.com | sh`
3. `git clone <repo> && cd whatsapp-lead-qualifier && git checkout private_coach`
4. Crear `.env` con todos los valores (ver Gotcha #3).
5. `scp -r google/ root@IP:/root/whatsapp-lead-qualifier/` (copiar credenciales de Calendar).
6. `docker compose up -d --build`
7. Escanear QR de WhatsApp: `ssh -L 8081:localhost:8081 root@IP` → Postman/curl a `POST http://localhost:8081/instance/create` con body `{"instanceName":"mi-instancia","integration":"WHATSAPP-BAILEYS","qrcode":true}` → `GET http://localhost:8081/instance/connect/mi-instancia` → escanear.
8. Verificar: `GET http://localhost:8081/instance/fetchInstances` → `connectionStatus=open`, `ownerJid=51958213628@s.whatsapp.net`.

**Gotcha deploy:** después de `git pull` siempre hacer `docker compose up -d --build`, no solo `up -d`. Si el módulo no aparece en el container, es que el build usó caché vieja.

---

## Google Calendar — implementado 2026-05-18

**Estado:** funcionando en producción. El coach crea un evento en Calendar cada vez que se guarda un recordatorio (Opción A — solo escritura).

**Archivos:**
- `coach/integrations/calendar.py` — `crear_evento(tarea, fecha, hora, duracion_min=30)`
- `coach/integrations/calendar_auth.py` — script one-time para generar `token.json`
- `google/credentials.json` y `google/token.json` — en el server en `/root/whatsapp-lead-qualifier/google/`, montados como volumen en `/app/google`. **Nunca se suben a GitHub** (están en `.gitignore`).

**Hook:** `coach/agent/coach.py::_crear_y_confirmar()` llama `crear_evento()` con try/except — un fallo de Calendar no rompe el recordatorio.

**Gotchas de Calendar (proceso complejo, documentar bien):**
1. En Google Cloud Console: proyecto → habilitar Calendar API → OAuth 2.0 Client tipo **Desktop** → descargar `credentials.json`.
2. En OAuth consent screen: agregar el Gmail del usuario como **Test user** (sin esto da `Error 403: access_denied`).
3. Correr `python -m coach.integrations.calendar_auth` en local (abre browser) → genera `token.json`.
4. Copiar carpeta `google/` al server con `scp -r google/ root@IP:/root/whatsapp-lead-qualifier/`.
5. El `token.json` se auto-refresca con el refresh_token — no hay que repetir el flow OAuth.

**Pendiente opcional:** guardar `event_id` en columna `google_event_id` de la tabla `recordatorios` (requiere migration en Supabase). Actualmente se loguea pero no se persiste.

**Próxima mejora posible:** leer Calendar en `_arranque_dia()` del scheduler para mostrar agenda del día (bidireccional). Requiere agregar scope `calendar.readonly` y función `listar_eventos_del_dia()`.

---

## Cómo retomar el trabajo

```bash
ssh root@178.105.163.82
cd whatsapp-lead-qualifier
docker compose ps                                              # los 3 deben estar Up
docker logs whatsapp-lead-qualifier-agent-1 --tail 30        # buscar [COACH] scheduler iniciado
```

Verificar WhatsApp (desde laptop con túnel SSH activo o directo en el server):
```bash
curl http://localhost:8081/instance/fetchInstances -H "apikey: crisagent2024"
# connectionStatus=open, ownerJid=51958213628@s.whatsapp.net
```

Mandar un mensaje desde `51965373728` al bot y mirar logs para `[COACH]` y `[CALENDAR]`.

Si nada de eso anda, mirá la sección "Troubleshooting" del README — el orden ahí está priorizado por frecuencia real.
