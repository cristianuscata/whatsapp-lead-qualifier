# Contexto de proyecto — MVP Coach de alto rendimiento

## Producto
Equipo: Cristian Uscata (individual). MVP para un único usuario que da
accountability sobre sus metas de largo plazo y recordatorios. Continúa el
PoC de la sesión 5 (coach personal proactivo por WhatsApp).

## Alcance
- SÍ hace: consultar el estado/avance de metas (PTE, Azure, Maestría, MVP,
  Visa, Sydney) y de recordatorios (pendiente/cumplido/vencido), con datos
  verificados por tools.
- NO hace: crear/modificar/borrar (solo lectura), información laboral, datos
  de terceros, Google Calendar, ni inventar datos.

## Arquitectura
- Frontend: HTML + JS estático en index.html / static/ (sin frameworks)
- Backend: FastAPI en api/chat.py, expone POST /api/chat
- Orquestador: agent.py (LangChain, create_agent, MultiServerMCPClient)
- Servidor de herramientas: FastMCP en api/mcp.py, stateless_http=True
- Fuente de datos: CSV sintéticos en data/
- Despliegue opcional: Vercel (api/index.py) — no intentar hasta que todo corra en local

## Reglas de desarrollo
- No inventes paquetes, APIs ni parámetros.
- Lee primero los archivos relevantes y propone un plan antes de editar.
- No borres archivos, datos ni configuraciones sin confirmación.
- No agregues dependencias sin justificar.
- Una sola responsabilidad por archivo.
- Actualiza pruebas cuando cambies comportamiento.
- Nunca escribas secretos en código, logs, README o commits.
- Ejecuta las pruebas y reporta qué funcionó y qué falta.

## Criterios de aceptación
1. Feliz: "¿cómo voy con PTE?" → usa consultar_metas y responde con avance real.
2. Límite: "¿cómo voy con francés?" → meta inexistente → no hay evidencia, no inventa.
3. Fuera de alcance: "resúmeme mis correos del trabajo" → declina con claridad.
