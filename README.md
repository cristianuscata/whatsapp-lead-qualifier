# WhatsApp AI Sales Agent 🚀

Agente de atención al cliente de WhatsApp automatizado construido con **FastAPI**, **OpenAI (GPT-4o-mini)** para inteligencia conversacional, **Supabase** para memoria a largo plazo y **Evolution API v2** como puente a WhatsApp.

El bot clasifica automáticamente a los leads en tres niveles (Frío 🧊, Tibio 🌤️, Caliente 🔥) y alerta al vendedor humano por WhatsApp cuando un cliente está listo para comprar.

---

## 📐 Arquitectura

```
┌─────────────┐     ┌──────────────────────────────┐     ┌──────────────┐
│  Cliente     │     │        Docker                 │     │  Tu PC       │
│  WhatsApp    │────▶│  Evolution API v2 (:8081)     │────▶│  Uvicorn     │
│              │◀────│  (puente WhatsApp)            │◀────│  FastAPI     │
│              │     │         │                     │     │  (:8000)     │
│              │     │  PostgreSQL (datos internos)  │     │              │
└─────────────┘     └──────────────────────────────┘     └──────┬───────┘
                                                                │
                                                    ┌───────────┼───────────┐
                                                    │           │           │
                                               ┌────▼───┐ ┌────▼───┐ ┌────▼────┐
                                               │ OpenAI │ │Supabase│ │Clasifi- │
                                               │ GPT-4o │ │  (DB)  │ │ cador   │
                                               └────────┘ └────────┘ └─────────┘
```

### ¿Por qué NO se necesita Ngrok? 🤔

En la versión original, se planteó usar **Ngrok** como túnel público para que Evolution API pudiera enviar webhooks a tu FastAPI. Pero resulta que **no es necesario en desarrollo local** porque:

1. **Evolution API corre dentro de Docker** en tu máquina.
2. **Uvicorn (FastAPI) corre directamente en tu máquina** (fuera de Docker).
3. Docker tiene un hostname especial llamado `host.docker.internal` que resuelve directamente a tu PC desde dentro de cualquier contenedor.

Entonces el flujo es **completamente local**:

```
Evolution API (Docker) ──http://host.docker.internal:8000/webhook──▶ Uvicorn (tu PC)
```

> **Ngrok solo sería necesario si Evolution API estuviera en un servidor remoto** y tu FastAPI en otro lado. En desarrollo local, `host.docker.internal` resuelve todo.

---

## 🛠️ Requisitos Previos

- [Python 3.11+](https://www.python.org/)
- [Docker y Docker Compose](https://www.docker.com/)
- Cuenta en [Supabase](https://supabase.com/) (Base de datos)
- API Key de [OpenAI](https://platform.openai.com/) (GPT-4o-mini)

---

## ⚙️ Configuración Inicial (solo la primera vez)

### 1. Variables de Entorno (`.env`)

Copia el archivo `.env.example` y renómbralo a `.env`. Rellena los valores:

| Variable | Descripción | Ejemplo |
|---|---|---|
| `OPENAI_API_KEY` | Tu clave de OpenAI | `sk-proj-...` |
| `EVOLUTION_URL` | URL local de Evolution API | `http://localhost:8081` |
| `EVOLUTION_API_KEY` | Contraseña para proteger la API | `crisagent2024` |
| `EVOLUTION_INSTANCE` | Nombre de tu instancia del bot | `mi-instancia` |
| `SUPABASE_URL` | URL de tu proyecto Supabase | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | Clave anon de Supabase | `eyJ...` |
| `VENDEDOR_NUMERO` | Número del vendedor (código de país + número, sin `+`) | `51958213628` |

### 2. Base de Datos (Supabase)

Ve al panel de **SQL Editor** en Supabase y ejecuta:

```sql
CREATE TABLE mensajes (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero     text NOT NULL,
    nombre     text,
    rol        text NOT NULL CHECK (rol IN ('user', 'assistant')),
    contenido  text NOT NULL,
    creado_en  timestamptz DEFAULT now()
);
```

### 3. Dependencias Python

```bash
# Opcional: crea y activa un entorno virtual
python -m venv venv
venv\Scripts\activate

# Instala dependencias
pip install -r requirements.txt
```

---

## 🚀 Guía de Arranque (Día a Día)

Para levantar el proyecto necesitas **2 terminales abiertas simultáneamente**, siguiendo este orden:

### 💻 Terminal 1 — Uvicorn (FastAPI)

Arranca primero el cerebro lógico del bot:

```bash
uvicorn main:app --reload
```

✅ Debe aparecer: `Uvicorn running on http://127.0.0.1:8000`

---

### 🐳 Terminal 2 — Docker Compose (Evolution API + PostgreSQL)

Levanta el gateway de WhatsApp:

```bash
docker-compose up evolution
```

✅ Debe aparecer: `HTTP - ON: 8080`

> **Nota:** La primera vez tardará más porque descarga las imágenes de Docker (~1GB).

---

### 📱 Conectar WhatsApp (solo la primera vez o si la sesión expira)

Con ambas terminales corriendo, abre una **tercera terminal** (o una pestaña nueva de PowerShell) y ejecuta:

#### A. Crear la instancia y obtener el QR

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

En la respuesta verás un campo `base64` con el QR codificado. Cópialo y pégalo en [Base64 to Image](https://base64.guru/converter/decode/image) para escanearlo con tu celular.

> 💡 **Tip:** También puedes obtener el QR desde el navegador visitando:
> `http://localhost:8081/instance/connect/mi-instancia`

#### B. Verificar que la conexión está activa

```powershell
Invoke-RestMethod -Uri "http://localhost:8081/instance/connectionState/mi-instancia" `
    -Method Get `
    -Headers @{ "apikey" = "crisagent2024" }
```

✅ Debe decir `state=open`.

---

## 🔧 Comandos Útiles

### Logs y Monitoreo

```bash
# Ver logs de Evolution API en tiempo real
docker-compose logs -f evolution

# Ver últimas 50 líneas de logs de Evolution
docker-compose logs --tail=50 evolution

# Ver logs de PostgreSQL
docker-compose logs -f evolution-postgres

# Ver logs de TODOS los servicios
docker-compose logs -f
```

### Control de Docker

```bash
# Bajar todos los servicios (conserva datos)
docker-compose down

# Bajar todo Y borrar datos (volúmenes) — requiere re-escanear QR
docker-compose down -v

# Levantar todo en segundo plano (modo detached)
docker-compose up -d evolution

# Ver estado de los contenedores
docker-compose ps

# Reiniciar solo Evolution API
docker-compose restart evolution
```

### Gestión de WhatsApp (PowerShell)

```powershell
# Ver todas las instancias
Invoke-RestMethod -Uri "http://localhost:8081/instance/fetchInstances" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }

# Ver estado de conexión
Invoke-RestMethod -Uri "http://localhost:8081/instance/connectionState/mi-instancia" `
    -Method Get -Headers @{ "apikey" = "crisagent2024" }

# Eliminar instancia (para reconectar desde cero)
Invoke-RestMethod -Uri "http://localhost:8081/instance/delete/mi-instancia" `
    -Method Delete -Headers @{ "apikey" = "crisagent2024" }

# Desconectar WhatsApp sin eliminar la instancia
Invoke-RestMethod -Uri "http://localhost:8081/instance/logout/mi-instancia" `
    -Method Delete -Headers @{ "apikey" = "crisagent2024" }
```

### Probar el webhook manualmente (sin WhatsApp)

```powershell
$body = @{
    event = "messages.upsert"
    data = @{
        key = @{
            remoteJid = "5491100000000@s.whatsapp.net"
            fromMe = $false
        }
        pushName = "Cliente Test"
        message = @{
            conversation = "Hola, quiero saber el precio"
        }
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8000/webhook" `
    -Method Post `
    -Body $body `
    -ContentType "application/json"
```

---

## 💡 Notas de Uso y Mantenimiento

- **"Loop Infinito":** El bot **nunca** responde a sus propios mensajes (`fromMe: true` se ignora). Para probar, siempre envía desde **otro celular** al número que escaneó el QR.

- **Sesión de WhatsApp Congelada:** Si el bot deja de contestar, probablemente la sesión se cerró. Elimina la instancia y vuelve a crearla:
  ```powershell
  # Eliminar
  Invoke-RestMethod -Uri "http://localhost:8081/instance/delete/mi-instancia" `
      -Method Delete -Headers @{ "apikey" = "crisagent2024" }
  # Volver a crear (ver paso A arriba)
  ```

- **Reconectar tras reiniciar Docker:** Si solo haces `docker-compose down` (sin `-v`), la sesión de WhatsApp se mantiene guardada en el volumen `evolution_instances`. Al volver a subir, debería reconectarse automáticamente.

- **Cambios en el código Python:** Uvicorn corre con `--reload`, así que cualquier cambio en `main.py`, `agent/`, o `db/` se aplica automáticamente sin reiniciar nada.

---

## 🏗️ Estructura del Proyecto

```
whatsapp-agent/
├── main.py                  # FastAPI — webhook + envío de mensajes
├── agent/
│   ├── openai_agent.py      # Generación de respuestas con GPT-4o-mini
│   ├── classifier.py        # Clasificación de leads (frío/tibio/caliente)
│   └── notifier.py          # Notificaciones inteligentes al vendedor
├── db/
│   └── supabase.py          # Guardar/obtener historial de mensajes
├── docker-compose.yml       # Evolution API v2 + PostgreSQL
├── Dockerfile               # Para producción (contenerizar el agente)
├── requirements.txt         # Dependencias Python
├── .env                     # Variables de entorno (NO subir a git)
└── README.md                # Este archivo
```

---

## 🔔 Sistema de Notificaciones al Vendedor

El bot clasifica cada mensaje y notifica al vendedor de forma inteligente para que pueda priorizar su tiempo:

| Temperatura | Notificación | Qué recibe el vendedor |
|---|---|---|
| 🔥 **Caliente** | ✅ Alerta urgente | `🔥🔥🔥 LEAD CALIENTE` + nombre + número + mensaje. Debe actuar inmediatamente. |
| 🌤️ **Tibio** | ✅ Info resumida | `🌤️ Lead tibio detectado` + contexto. El bot ya respondió, puede intervenir si quiere. |
| 🧊 **Frío** | ❌ Silencioso | Sin notificación. Solo se guarda en Supabase para análisis posterior. |

**¿Por qué este enfoque?** Si el vendedor recibiera una alerta por CADA mensaje, se saturaría y dejaría de prestarles atención. Con este sistema, cuando suena una notificación 🔥, el vendedor sabe que **debe dejar todo y atender**.

---

## 🌍 Guía para Producción

Llevar este proyecto a un servidor real requiere los siguientes cambios:

### 1. Contenerizar TODO con Docker Compose

En producción, **ya no corres Uvicorn por separado**:

```bash
docker-compose up -d
```

Esto levanta los 3 servicios: `agent` (FastAPI), `evolution` (WhatsApp), y `evolution-postgres` (DB).

### 2. Cambiar `WEBHOOK_GLOBAL_URL` para comunicación interna

```yaml
# docker-compose.yml (producción)
- WEBHOOK_GLOBAL_URL=http://agent:8000/webhook
```

### 3. Configurar dominio con HTTPS (Caddy)

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
api.tuempresa.com {
    reverse_proxy agent:8000
}
```

### 4. Habilitar Redis

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

### 5. Desarrollo vs Producción

| Aspecto | Desarrollo (local) | Producción (servidor) |
|---|---|---|
| **Uvicorn** | Terminal local con `--reload` | Dentro de Docker (`agent`) |
| **Webhook URL** | `http://host.docker.internal:8000` | `http://agent:8000` (interna) |
| **Acceso externo** | `localhost:8081` | `api.tuempresa.com` (HTTPS) |
| **Ngrok** | ❌ No necesario | ❌ No necesario |
| **Redis** | Deshabilitado | Habilitado |
| **Arranque** | `uvicorn` + `docker-compose up evolution` | `docker-compose up -d` |

---

## 💰 Plataformas y Suscripciones para Producción

### Opción A: Mínimo Viable (~$12-20/mes)

| Servicio | Plataforma | Costo | Para qué |
|---|---|---|---|
| **Servidor VPS** | [Hetzner Cloud](https://www.hetzner.com/cloud) CX22 | ~$4-6/mes | Docker con todos los servicios |
| **OpenAI API** | [OpenAI](https://platform.openai.com/) GPT-4o-mini | ~$2-5/mes | Genera respuestas (~1M tokens = ~$0.30) |
| **Supabase** | [Supabase](https://supabase.com/) Free tier | $0/mes | 500MB base de datos gratis |
| **Dominio** | [Namecheap](https://namecheap.com/) o [Cloudflare](https://cloudflare.com/) | ~$10/año | `tuempresa.com` |
| **SSL** | Caddy (automático) | $0 | HTTPS gratis con Let's Encrypt |

**Total: ~$12-20/mes** para arrancar con hasta ~50 clientes concurrentes.

### Opción B: Escalable (~$30-60/mes)

| Servicio | Plataforma | Costo | Ventaja |
|---|---|---|---|
| **Servidor** | [DigitalOcean](https://digitalocean.com/) Droplet 4GB | ~$24/mes | Más RAM para múltiples instancias |
| **OpenAI** | GPT-4o-mini alto volumen | ~$5-15/mes | Más conversaciones |
| **Supabase** | Pro Plan | $25/mes | 8GB, backups diarios |
| **Monitoreo** | [UptimeRobot](https://uptimerobot.com/) | $0 | Alerta si el servidor se cae |

### Opción C: Cloud Gestionado (~$40-80/mes)

| Servicio | Plataforma | Costo | Ventaja |
|---|---|---|---|
| **FastAPI** | [Railway](https://railway.app/) o [Render](https://render.com/) | ~$7-20/mes | Deploy con Git push |
| **Evolution API** | VPS dedicado (Hetzner/DO) | ~$6-24/mes | Necesita Docker directo |
| **Base de datos** | Supabase Pro o [Neon](https://neon.tech/) | $0-25/mes | PostgreSQL gestionado |

### ⚠️ Importante: WhatsApp y Meta

- Evolution API usa la **API no-oficial** de WhatsApp (Baileys). Es gratuita pero **Meta puede banear el número** si detectan uso agresivo.
- Para un negocio serio a largo plazo, evalúa la [API oficial de WhatsApp Business](https://business.whatsapp.com/products/business-platform) vía [Twilio](https://www.twilio.com/) o [360dialog](https://www.360dialog.com/). Cuesta ~$0.05-0.10 por mensaje pero es 100% legal.
- **Recomendación:** Arranca con Evolution API para validar. Si el negocio crece, migra a la API oficial.

---

## 📈 Tips para Vender este Producto

### 🎯 A quién venderle

| Nicho | Por qué les sirve | Cómo venderlo |
|---|---|---|
| **Clínicas dentales / estéticas** | Reciben 50+ consultas por WhatsApp sobre precios y citas | "Tu recepcionista virtual que nunca duerme" |
| **Inmobiliarias** | Leads preguntan por departamentos a toda hora | "Califica leads y te avisa solo los que quieren comprar" |
| **E-commerce / tiendas online** | Preguntas de stock, precios, envío | "Responde al instante mientras duermes — 0 leads perdidos" |
| **Academias / cursos** | "¿Cuánto cuesta?" "¿Cuándo empiezan?" | "Convierte consultas en matrículas 24/7" |
| **Restaurantes / delivery** | Pedidos por WhatsApp | "Toma pedidos automáticamente" |
| **Abogados / consultores** | Filtrar clientes serios de curiosos | "Solo te notifica cuando alguien está listo para pagar" |

### 💲 Cómo cobrar

| Modelo | Precio sugerido | Para quién |
|---|---|---|
| **Setup + mensualidad** | $200-500 setup + $80-150/mes | PyMEs que quieren servicio gestionado |
| **Solo mensualidad** | $120-200/mes (todo incluido) | Clientes que prefieren simplicidad |
| **Por conversación** | $0.10-0.30 por conversación atendida | Alto volumen, empresas medianas |
| **Freemium** | Gratis hasta 100 conv/mes, luego $99/mes | Para captar clientes masivamente |

### 🗣️ Frases que venden (script de venta)

1. **El dolor:** *"¿Cuántos clientes te escriben por WhatsApp a las 11pm y nunca les contestas? Cada mensaje sin responder es dinero que se va a tu competencia."*

2. **La solución:** *"Imagina que tienes un vendedor que trabaja 24/7, nunca se enferma, responde en 3 segundos y te avisa al instante cuando alguien quiere comprar."*

3. **La prueba:** *"Mira, te mando un mensaje ahora y mira cómo responde..."* → **Demo en vivo** (esto es tu arma más poderosa).

4. **El cierre:** *"Si de cada 100 consultas que recibes, recuperas 5 ventas que antes perdías, ¿cuánto vale eso para tu negocio?"*

### 🚀 Estrategia de lanzamiento

1. **Semana 1-2:** Ofrécelo **gratis a 3 negocios amigos** durante 2 semanas. Consigue testimoniales y capturas de pantalla.

2. **Semana 3-4:** Publica los resultados en LinkedIn/Instagram: *"Este bot atendió 200 clientes en 14 días para [Negocio X] — sin que el dueño levantara un dedo"*.

3. **Mes 2:** Empieza a cobrar. Usa los casos de éxito como prueba social.

4. **Mes 3+:** Agrega features diferenciadores:
   - Dashboard web para que el cliente vea sus métricas
   - Integración con Google Calendar para agendar citas
   - Catálogo de productos con precios automáticos
   - Respuestas con imágenes y PDFs

### 💡 Diferenciadores vs la competencia

- **Personalización total:** Controlas el prompt de IA, los flujos y la lógica. No estás limitado a plantillas como Manychat o Chatfuel.
- **Sin costo por mensaje:** Con Evolution API no pagas por mensaje (vs Twilio que cobra $0.05-0.10 cada uno).
- **Clasificación inteligente:** El vendedor no pierde tiempo con curiosos — solo le llega lo que importa.
- **Historial completo:** Toda la conversación se guarda en Supabase — se puede analizar para mejorar las respuestas.

---

## 📄 Licencia

Proyecto para uso educativo — Curso IA for Developers.
