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
```

⚠️ Cambios al `.env` requieren recrear el container: `docker compose up -d --force-recreate agent`. Un simple restart NO toma las variables nuevas (env se lee al crear el container).

---

## Recomendación de despliegue (decidido el 2026-05-17)

**Plan elegido: Hetzner Cloud CX22 (VPS, ~$4-6/mes)**, NO Railway.

**Razón:** este stack es Docker-compose con 3 servicios y estado persistente (sesión de WhatsApp en volumen). Un VPS replica exactamente lo que ya anda en local sin reinventar nada. Railway está pensado para apps de un solo container; con 3 servicios + volúmenes se vuelve caro (~$10-15/mes) y complejo de configurar (cada servicio aparte, volúmenes manuales, networking interno con sintaxis distinta).

**Pasos para deploy en Hetzner (cuando volvamos a esto):**

1. Crear VPS CX22 en [hetzner.com/cloud](https://www.hetzner.com/cloud) con Ubuntu 24.04. Anotar IP pública.
2. `ssh root@TU_IP`
3. Instalar Docker: `curl -fsSL https://get.docker.com | sh`
4. `git clone <repo> && cd whatsapp-lead-qualifier && git checkout private_coach`
5. Crear `.env` en el server con los valores reales (`nano .env`).
6. `docker compose up -d`
7. **Escanear QR de nuevo** (la sesión no se puede copiar desde local cómodamente). Desde tu laptop: `ssh -L 8081:localhost:8081 root@TU_IP`, después en otra terminal local seguir los pasos del README sección "Connect WhatsApp" con `http://localhost:8081`.
8. Listo, queda corriendo 24/7.

**Lo que NO cambia en producción:** Supabase, OpenAI, y conceptualmente el número de WhatsApp (aunque la sesión hay que regenerarla en el server).

**Cuándo migrar a Railway:** si en algún momento querés CI/CD automático (`git push` → deploy) y vale la pena pagar el doble. No es prioridad para MVP.

---

## Próximo trabajo pendiente — Google Calendar (decidido 2026-05-17)

**Dirección elegida: Opción A — solo escribir.** El coach crea eventos en Calendar cuando se guarda un recordatorio. No lee Calendar todavía. (Si más adelante se quiere bidireccional, agregar `listar_eventos_del_dia()` y hookear en el `_arranque_dia()` del scheduler).

**Setup que necesita Cristian antes de la sesión:**
1. Proyecto en [Google Cloud Console](https://console.cloud.google.com).
2. Habilitar Google Calendar API.
3. OAuth 2.0 Client tipo **Desktop**. Descargar `credentials.json`.

**Plan de implementación:**
- Agregar a `requirements.txt`: `google-auth-oauthlib`, `google-api-python-client`.
- Crear `coach/integrations/calendar.py` con:
  - `crear_evento(tarea: str, fecha: date, hora: time, duracion_min: int = 30) -> str` (devuelve event_id)
  - Internamente: maneja el flujo OAuth con `credentials.json` + `token.json`.
- Carpeta `google/` montada como volumen en `docker-compose.yml`: `./google:/app/google` para que `credentials.json` y `token.json` sobrevivan rebuilds.
- Hook en `coach/agent/coach.py::_crear_y_confirmar()`: después del `await r_db.crear_recordatorio(...)`, llamar `calendar.crear_evento(...)` con try/except (un fallo de Calendar NO debe tirar la creación del recordatorio).
- Opcional: guardar el `event_id` devuelto en una columna nueva `google_event_id` en `recordatorios` (requiere migration en Supabase).
- Variables nuevas en `.env`: `GOOGLE_CALENDAR_ID=primary` (o un calendar específico), `GOOGLE_CREDS_DIR=/app/google`.

**Primera corrida (auth one-time):**
- Hace falta correr el flow de OAuth UNA vez para generar `token.json`. Plan: agregar un script CLI `python -m coach.integrations.calendar_auth` que abra el browser, deje el `token.json`, y después el container ya lo consume. O hacerlo en local antes de subir el archivo.

---

## Cómo retomar el trabajo

1. `docker compose ps` — ver si los 3 servicios están arriba.
2. Si falta `agent`, levantarlo: `docker compose up -d`.
3. `docker logs whatsapp-lead-qualifier-agent-1 --tail 30` — buscar línea `[COACH] scheduler iniciado` para confirmar que el coach arrancó.
4. Verificar WhatsApp: `Invoke-RestMethod http://localhost:8081/instance/fetchInstances -Headers @{apikey="crisagent2024"}` → `connectionStatus=open` y `ownerJid=51958213628@s.whatsapp.net`.
5. Mandar un mensaje desde tu celular personal (51965373728) al bot. Mirar logs para `[COACH]`.

Si nada de eso anda, mirá la sección "Troubleshooting" del README — el orden ahí está priorizado por frecuencia real.
