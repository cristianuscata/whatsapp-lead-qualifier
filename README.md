# WhatsApp AI Sales Agent 🚀

Automated WhatsApp customer service agent built with **FastAPI**, **OpenAI (GPT-4o-mini)** for conversational intelligence, **Supabase** for long-term memory, and **Evolution API v2** as the WhatsApp bridge.

The bot automatically classifies leads into three tiers (Cold 🧊, Warm 🌤️, Hot 🔥) and alerts the human salesperson via WhatsApp when a customer is ready to buy.

---

## 📐 Architecture

```
┌─────────────┐     ┌──────────────────────────────┐     ┌──────────────┐
│  WhatsApp   │     │        Docker                 │     │  Your PC     │
│  Client     │────▶│  Evolution API v2 (:8081)     │────▶│  Uvicorn     │
│             │◀────│  (WhatsApp bridge)            │◀────│  FastAPI     │
│             │     │         │                     │     │  (:8000)     │
│             │     │  PostgreSQL (internal data)   │     │              │
└─────────────┘     └──────────────────────────────┘     └──────┬───────┘
                                                                │
                                                    ┌───────────┼───────────┐
                                                    │           │           │
                                               ┌────▼───┐ ┌────▼───┐ ┌────▼────┐
                                               │ OpenAI │ │Supabase│ │Lead     │
                                               │ GPT-4o │ │  (DB)  │ │Classif. │
                                               └────────┘ └────────┘ └─────────┘
```

### Why Ngrok is NOT needed 🤔

In the original design, **Ngrok** was considered as a public tunnel so Evolution API could send webhooks to your FastAPI. However, **it's not necessary for local development** because:

1. **Evolution API runs inside Docker** on your machine.
2. **Uvicorn (FastAPI) runs directly on your machine** (outside Docker).
3. Docker has a special hostname called `host.docker.internal` that resolves directly to your PC from inside any container.

So the flow is **completely local**:

```
Evolution API (Docker) ──http://host.docker.internal:8000/webhook──▶ Uvicorn (your PC)
```

> **Ngrok would only be needed if Evolution API were on a remote server** and your FastAPI somewhere else. In local development, `host.docker.internal` solves everything.

---

## 🛠️ Prerequisites

- [Python 3.11+](https://www.python.org/)
- [Docker and Docker Compose](https://www.docker.com/)
- [Supabase](https://supabase.com/) account (Database)
- [OpenAI](https://platform.openai.com/) API Key (GPT-4o-mini)

---

## ⚙️ Initial Setup (first time only)

### 1. Environment Variables (`.env`)

Create a `.env` file at the project root with the following values:

| Variable | Description | Example |
|---|---|---|
| `OPENAI_API_KEY` | Your OpenAI key | `sk-proj-...` |
| `EVOLUTION_URL` | Local Evolution API URL | `http://localhost:8081` |
| `EVOLUTION_API_KEY` | Password to protect the API | `crisagent2024` |
| `EVOLUTION_INSTANCE` | Your bot instance name | `mi-instancia` |
| `SUPABASE_URL` | Your Supabase project URL | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | Supabase anon key | `eyJ...` |
| `VENDEDOR_NUMERO` | Salesperson's number (country code + number, without `+`) | `51958213628` |
| `CRISTIAN_PHONE` | *(coach branch only)* JID of the personal phone that talks to the coach | `51XXXXXXXXX@s.whatsapp.net` |
| `COACH_ENABLED` | *(coach branch only)* Enable the coach module and its scheduler | `true` |

### 2. Database (Supabase)

Go to the **SQL Editor** panel in Supabase and run:

```sql
-- Lead agent (always required)
CREATE TABLE mensajes (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero     text NOT NULL,
    nombre     text,
    rol        text NOT NULL CHECK (rol IN ('user', 'assistant')),
    contenido  text NOT NULL,
    creado_en  timestamptz DEFAULT now()
);
```

If you are on the `private_coach` branch (personal coach feature), also run:

```sql
-- Personal coach: scheduled reminders
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

-- Personal coach: conversation history (separate from leads)
CREATE TABLE coach_mensajes (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role       text NOT NULL CHECK (role IN ('user', 'assistant')),
    content    text NOT NULL,
    tipo       text DEFAULT 'chat',
    created_at timestamptz DEFAULT now()
);
```

### 3. Python Dependencies

#### Option A: Standard `pip`
```bash
# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Option B: Fast setup with `uv` 🚀
```bash
# Create environment
uv venv

# Install dependencies
uv pip install -r requirements.txt
```

---

## 🚀 Startup Guide (Day to Day)

You have two ways to run the project: **fully dockerized** (recommended, all 3 services inside Docker) or **dev mode with hot reload** (Uvicorn locally + Evolution in Docker).

### 🐳 Option 1 — Fully Dockerized (recommended)

Brings up the three services (`agent` FastAPI, `evolution`, `evolution-postgres`) in one shot:

```bash
docker-compose up -d
```

Verify all three are running:

```bash
docker-compose ps
```

You should see something like:

```
NAME                                           STATUS
whatsapp-lead-qualifier-agent-1                Up
whatsapp-lead-qualifier-evolution-1            Up
whatsapp-lead-qualifier-evolution-postgres-1   Up
```

> ⚠️ **Common mistake:** running `docker-compose up evolution` (without `-d` and without naming the rest of the services) only starts Evolution, and the `agent` container stays down. Evolution will then receive WhatsApp messages but have no one to forward the webhook to → the bot won't reply. Always use `docker-compose up -d` (no service name) to bring up everything.

Health check on the agent:

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

### 💻 Option 2 — Dev mode (Uvicorn local + Evolution in Docker)

Useful when you're iterating on Python code and want hot reload. Needs **2 terminals**.

**Terminal 1 — Uvicorn (FastAPI):**
```bash
uvicorn main:app --reload
# Or with uv:
uv run uvicorn main:app --reload
```
✅ You should see: `Uvicorn running on http://127.0.0.1:8000`

**Terminal 2 — Docker Compose (Evolution only):**
```bash
docker-compose up evolution
```
✅ You should see: `HTTP - ON: 8080`

> The first time it'll take longer because it downloads Docker images (~1GB).

---

### 📱 Connect WhatsApp (first time only or when the session expires)

> 🚨 **CRITICAL — Which WhatsApp account to use:**
> The QR you're about to scan **vincula la cuenta de WhatsApp con la que escaneás como el bot**. Whoever scans is the bot.
>
> If your bot should respond from `+51 958 213 628`, you MUST scan the QR **from the WhatsApp app installed on the phone with that number** (Settings → Linked Devices → Link a Device).
>
> Scanning from the wrong WhatsApp account is the #1 reason "the bot doesn't reply" — Evolution stays connected just fine, but to a different number than the one you're sending test messages to. To verify which number got linked, see "Verify connection" below.

With the services running, open a **new PowerShell tab** and run:

#### A. Create the instance and get the QR code

```powershell
$body = @{
    instanceName = "mi-instancia"
    integration  = "WHATSAPP-BAILEYS"
    qrcode       = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8081/instance/create" `
    -Method Post `
    -Headers @{ "apikey" = "crisagent2024" } `
    -Body $body `
    -ContentType "application/json"
```

The response includes a `qrcode.base64` field with the encoded PNG. To open it as an image:

```powershell
$resp = Invoke-RestMethod -Uri "http://localhost:8081/instance/connect/mi-instancia" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }
$b64 = $resp.base64 -replace '^data:image/png;base64,', ''
[IO.File]::WriteAllBytes("qr.png", [Convert]::FromBase64String($b64))
Start-Process qr.png
```

Then scan `qr.png` **from the WhatsApp account you want to be the bot** (see warning above).

> 💡 You can also paste the base64 string into [Base64 to Image](https://base64.guru/converter/decode/image) to view it, or visit `http://localhost:8081/instance/connect/mi-instancia` in the browser (returns JSON with the base64).

#### B. Verify the connection AND which number got linked

```powershell
Invoke-RestMethod -Uri "http://localhost:8081/instance/fetchInstances" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }
```

Look for two fields in the response:

- `connectionStatus` should be `open` — confirms WhatsApp is paired.
- `ownerJid` should be `<your-bot-number>@s.whatsapp.net` (e.g. `51958213628@s.whatsapp.net`) — confirms the **right** account was linked.

If `ownerJid` is a different number than the one you want, you scanned from the wrong phone. Delete the instance, recreate it, and scan from the correct account:

```powershell
Invoke-RestMethod -Uri "http://localhost:8081/instance/delete/mi-instancia" `
    -Method Delete -Headers @{ "apikey" = "crisagent2024" }
# Then redo step A.
```

---

## 🔧 Useful Commands

### Logs and Monitoring

```bash
# View Evolution API logs in real time
docker-compose logs -f evolution

# View last 50 lines of Evolution logs
docker-compose logs --tail=50 evolution

# View PostgreSQL logs
docker-compose logs -f evolution-postgres

# View ALL services logs
docker-compose logs -f
```

### Docker Control

```bash
# Stop all services (preserves data)
docker-compose down

# Stop everything AND delete data (volumes) — requires re-scanning QR
docker-compose down -v

# Start in background (detached mode)
docker-compose up -d evolution

# View container status
docker-compose ps

# Restart only Evolution API
docker-compose restart evolution
```

### WhatsApp Management (PowerShell)

```powershell
# List all instances
Invoke-RestMethod -Uri "http://localhost:8081/instance/fetchInstances" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }

# Check connection state
Invoke-RestMethod -Uri "http://localhost:8081/instance/connectionState/mi-instancia" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }

# Delete instance (to reconnect from scratch)
Invoke-RestMethod -Uri "http://localhost:8081/instance/delete/mi-instancia" `
    -Method Delete -Headers @{ "apikey" = "crisagent2024" }

# Disconnect WhatsApp without deleting the instance
Invoke-RestMethod -Uri "http://localhost:8081/instance/logout/mi-instancia" `
    -Method Delete -Headers @{ "apikey" = "crisagent2024" }
```

### Test the webhook manually (without WhatsApp)

```powershell
$body = @{
    event = "messages.upsert"
    data = @{
        key = @{
            remoteJid = "5491100000000@s.whatsapp.net"
            fromMe = $false
        }
        pushName = "Test Client"
        message = @{
            conversation = "Hi, I'd like to know the price"
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8000/webhook" `
    -Method Post `
    -Body $body `
    -ContentType "application/json"
```

---

## 💡 Usage and Maintenance Notes

- **"Infinite Loop":** The bot **never** responds to its own messages (`fromMe: true` is ignored). To test, always send from **another phone** to the number that scanned the QR.

- **Reconnecting after restarting Docker:** If you only run `docker-compose down` (without `-v`), the WhatsApp session is kept in the `evolution_instances` volume. When you bring it back up, it should reconnect automatically.

- **⚠️ Never use `docker-compose down -v`** unless you intend to wipe the WhatsApp session. The `-v` flag deletes volumes, including `evolution_instances`, which forces you to re-scan the QR from scratch.

- **Python code changes:**
  - In **Option 2 (Uvicorn local)**: code reloads automatically thanks to `--reload`.
  - In **Option 1 (fully dockerized)**: rebuild the `agent` container with `docker-compose up -d --build agent`.

- **`.env` changes:** the `agent` container only reads `.env` at startup. After editing `.env`, run `docker-compose up -d --force-recreate agent` to pick up the new values.

---

## 🩺 Troubleshooting — "The bot doesn't reply"

Work through these checks in order. Most "bot is dead" cases are one of these four.

### 1. Are all three containers running?

```bash
docker-compose ps
```

You need `agent`, `evolution`, AND `evolution-postgres` all in `Up` state. If `agent` is missing, you probably ran `docker-compose up evolution` instead of `docker-compose up -d`. Fix:

```bash
docker-compose up -d
```

### 2. Is the WhatsApp instance linked to the RIGHT number?

```powershell
Invoke-RestMethod -Uri "http://localhost:8081/instance/fetchInstances" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }
```

Check `connectionStatus` (`open` = good) and `ownerJid` (must match the number you're sending test messages to). If `ownerJid` shows a different number, the QR was scanned from the wrong WhatsApp account → delete the instance and re-scan from the correct phone (see "Connect WhatsApp" section above).

If `fetchInstances` returns `[]`, the volume `evolution_instances` was wiped (e.g. by `docker-compose down -v`) — recreate the instance from scratch.

### 3. Are the inter-container URLs correct? (most common root cause)

When everything runs in Docker, `agent` and `evolution` must talk to each other by **service name + internal port**, not via `localhost` or `host.docker.internal`. Inside a container, `localhost` means the container itself, not the host.

| Caller | Target | Correct URL |
|---|---|---|
| `evolution` container | `agent` | `http://agent:8000/webhook` (in `docker-compose.yml` → `WEBHOOK_GLOBAL_URL`) |
| `agent` container | `evolution` | `http://evolution:8080` (in `.env` → `EVOLUTION_URL`) |
| Your terminal / PowerShell | Either | `http://localhost:8000` or `http://localhost:8081` (the port-forwards) |

Symptoms of mis-configuration:
- `evolution` logs show `AxiosError: timeout of 60000ms exceeded` → its `WEBHOOK_GLOBAL_URL` is wrong.
- `agent` logs show `Error de conexión enviando a ...: All connection attempts failed` → its `EVOLUTION_URL` is wrong.

If you switch back to **dev mode** (`uvicorn` local + only Evolution in Docker), invert both: `EVOLUTION_URL=http://localhost:8081` and `WEBHOOK_GLOBAL_URL=http://host.docker.internal:8000/webhook`.

### 4. Is Evolution actually hitting the webhook?

Tail the agent's logs and send a WhatsApp test message:

```bash
docker logs whatsapp-lead-qualifier-agent-1 --tail 50 -f
```

You should see log lines like `Mensaje de <name> (<number>): ...`. If nothing shows up when you send a message, Evolution isn't reaching the agent. Common cause: the global webhook isn't configured. Verify in `docker-compose.yml`:

```yaml
- WEBHOOK_GLOBAL_URL=http://host.docker.internal:8000/webhook
- WEBHOOK_GLOBAL_ENABLED=true
```

### 5. Did the Supabase credentials change?

If `.env` was updated (new `SUPABASE_URL` / `SUPABASE_KEY` / `OPENAI_API_KEY`) but the agent was already running, it's still using the old values. Force a reload:

```bash
docker-compose up -d --force-recreate agent
```

Then re-test. If you see errors in the agent logs about Supabase, double-check the URL/key and that the `mensajes` table exists (see "Database (Supabase)" in initial setup).

### 6. Frozen WhatsApp session

If the bot was working and suddenly stopped (no logs on webhook even though it was working before), WhatsApp may have closed the session. Recreate the instance:

```powershell
# Delete
Invoke-RestMethod -Uri "http://localhost:8081/instance/delete/mi-instancia" `
    -Method Delete -Headers @{ "apikey" = "crisagent2024" }
# Recreate (see "Connect WhatsApp" section above)
```

---

## 🏗️ Project Structure

```
whatsapp-agent/
├── main.py                  # FastAPI — webhook + message sending
├── agent/
│   ├── openai_agent.py      # Response generation with GPT-4o-mini
│   ├── classifier.py        # Lead classification (cold/warm/hot)
│   └── notifier.py          # Smart salesperson notifications
├── db/
│   └── supabase.py          # Save/retrieve message history
├── docker-compose.yml       # Evolution API v2 + PostgreSQL
├── Dockerfile               # For production (containerize the agent)
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (DO NOT commit to git)
└── README.md                # This file
```

---

## 🔔 Salesperson Notification System

The bot classifies each message and notifies the salesperson intelligently so they can prioritize their time:

| Temperature | Notification | What the salesperson receives |
|---|---|---|
| 🔥 **Hot** | ✅ Urgent alert | `🔥🔥🔥 HOT LEAD` + name + number + message. Must act immediately. |
| 🌤️ **Warm** | ✅ Summary info | `🌤️ Warm lead detected` + context. The bot already responded, they can step in if they want. |
| 🧊 **Cold** | ❌ Silent | No notification. Only saved to Supabase for later analysis. |

**Why this approach?** If the salesperson received an alert for EVERY message, they'd be overwhelmed and stop paying attention. With this system, when a 🔥 notification comes in, the salesperson knows they **must drop everything and respond**.

---

## 🌍 Production Guide

Taking this project to a real server requires the following changes:

### 1. Containerize EVERYTHING with Docker Compose

In production, **you no longer run Uvicorn separately**:

```bash
docker-compose up -d
```

This starts all 3 services: `agent` (FastAPI), `evolution` (WhatsApp), and `evolution-postgres` (DB).

### 2. Change `WEBHOOK_GLOBAL_URL` for internal communication

```yaml
# docker-compose.yml (production)
- WEBHOOK_GLOBAL_URL=http://agent:8000/webhook
```

### 3. Configure domain with HTTPS (Caddy)

```yaml
  caddy:
    image: caddy:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
```

```
# Caddyfile
api.yourcompany.com {
    reverse_proxy agent:8000
}
```

### 4. Enable Redis

```yaml
  redis:
    image: redis:alpine
    volumes:
      - redis_data:/data

  evolution:
    environment:
      - CACHE_REDIS_ENABLED=true
      - CACHE_REDIS_URI=redis://redis:6379/0
```

### 5. Development vs Production

| Aspect | Development (local) | Production (server) |
|---|---|---|
| **Uvicorn** | Local terminal with `--reload` | Inside Docker (`agent`) |
| **Webhook URL** | `http://host.docker.internal:8000` | `http://agent:8000` (internal) |
| **External access** | `localhost:8081` | `api.yourcompany.com` (HTTPS) |
| **Ngrok** | ❌ Not needed | ❌ Not needed |
| **Redis** | Disabled | Enabled |
| **Startup** | `uvicorn` + `docker-compose up evolution` | `docker-compose up -d` |

---

## 💰 Platforms and Subscriptions for Production

### Option A: Minimum Viable (~$12-20/month)

| Service | Platform | Cost | Purpose |
|---|---|---|---|
| **VPS Server** | [Hetzner Cloud](https://www.hetzner.com/cloud) CX22 | ~$4-6/month | Docker with all services |
| **OpenAI API** | [OpenAI](https://platform.openai.com/) GPT-4o-mini | ~$2-5/month | Generates responses (~1M tokens = ~$0.30) |
| **Supabase** | [Supabase](https://supabase.com/) Free tier | $0/month | 500MB free database |
| **Domain** | [Namecheap](https://namecheap.com/) or [Cloudflare](https://cloudflare.com/) | ~$10/year | `yourcompany.com` |
| **SSL** | Caddy (automatic) | $0 | Free HTTPS with Let's Encrypt |

**Total: ~$12-20/month** to get started with up to ~50 concurrent customers.

### Option B: Scalable (~$30-60/month)

| Service | Platform | Cost | Advantage |
|---|---|---|---|
| **Server** | [DigitalOcean](https://digitalocean.com/) 4GB Droplet | ~$24/month | More RAM for multiple instances |
| **OpenAI** | GPT-4o-mini high volume | ~$5-15/month | More conversations |
| **Supabase** | Pro Plan | $25/month | 8GB, daily backups |
| **Monitoring** | [UptimeRobot](https://uptimerobot.com/) | $0 | Alerts if server goes down |

### Option C: Managed Cloud (~$40-80/month)

| Service | Platform | Cost | Advantage |
|---|---|---|---|
| **FastAPI** | [Railway](https://railway.app/) or [Render](https://render.com/) | ~$7-20/month | Deploy with Git push |
| **Evolution API** | Dedicated VPS (Hetzner/DO) | ~$6-24/month | Requires direct Docker |
| **Database** | Supabase Pro or [Neon](https://neon.tech/) | $0-25/month | Managed PostgreSQL |

### ⚠️ Important: WhatsApp and Meta

- Evolution API uses the **unofficial** WhatsApp API (Baileys). It's free but **Meta can ban the number** if they detect aggressive usage.
- For a serious long-term business, evaluate the [official WhatsApp Business API](https://business.whatsapp.com/products/business-platform) via [Twilio](https://www.twilio.com/) or [360dialog](https://www.360dialog.com/). It costs ~$0.05-0.10 per message but is 100% legal.
- **Recommendation:** Start with Evolution API to validate. If the business grows, migrate to the official API.

---

## 📈 Tips for Selling This Product

### 🎯 Who to sell to

| Niche | Why it's useful | How to sell it |
|---|---|---|
| **Dental / aesthetic clinics** | Receive 50+ WhatsApp inquiries about prices and appointments | "Your virtual receptionist that never sleeps" |
| **Real estate agencies** | Leads ask about properties at all hours | "Qualifies leads and only alerts you for those ready to buy" |
| **E-commerce / online stores** | Questions about stock, prices, shipping | "Responds instantly while you sleep — 0 lost leads" |
| **Academies / courses** | "How much does it cost?" "When do classes start?" | "Converts inquiries into enrollments 24/7" |
| **Restaurants / delivery** | Orders via WhatsApp | "Takes orders automatically" |
| **Lawyers / consultants** | Filter serious clients from the curious | "Only notifies you when someone is ready to pay" |

### 💲 How to charge

| Model | Suggested price | For whom |
|---|---|---|
| **Setup + monthly fee** | $200-500 setup + $80-150/month | SMBs that want a managed service |
| **Monthly only** | $120-200/month (all included) | Clients who prefer simplicity |
| **Per conversation** | $0.10-0.30 per conversation handled | High volume, medium-sized companies |
| **Freemium** | Free up to 100 conv/month, then $99/month | To acquire customers massively |

### 🗣️ Sales phrases (sales script)

1. **The pain:** *"How many customers message you on WhatsApp at 11pm and you never reply? Every unanswered message is money going to your competition."*

2. **The solution:** *"Imagine having a salesperson that works 24/7, never gets sick, responds in 3 seconds, and instantly alerts you when someone wants to buy."*

3. **The proof:** *"Look, I'll send a message right now and watch how it responds..."* → **Live demo** (this is your most powerful weapon).

4. **The close:** *"If out of every 100 inquiries you receive, you recover 5 sales you were losing before — how much is that worth to your business?"*

### 🚀 Launch strategy

1. **Week 1-2:** Offer it **free to 3 friend businesses** for 2 weeks. Get testimonials and screenshots.

2. **Week 3-4:** Post results on LinkedIn/Instagram: *"This bot handled 200 customers in 14 days for [Business X] — without the owner lifting a finger."*

3. **Month 2:** Start charging. Use success stories as social proof.

4. **Month 3+:** Add differentiating features:
   - Web dashboard for clients to see their metrics
   - Google Calendar integration to schedule appointments
   - Product catalog with automatic pricing
   - Responses with images and PDFs

### 💡 Differentiators vs the competition

- **Full customization:** You control the AI prompt, flows, and logic. You're not limited to templates like Manychat or Chatfuel.
- **No per-message cost:** With Evolution API you don't pay per message (vs Twilio at $0.05-0.10 each).
- **Smart classification:** The salesperson doesn't waste time with curious people — only what matters comes through.
- **Full history:** The entire conversation is saved in Supabase — it can be analyzed to improve responses.

---

## 📄 License

Project for educational use — AI for Developers Course.
