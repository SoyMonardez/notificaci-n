# Plan: Asistente de agenda y recordatorios por WhatsApp con IA ("notificación")

## Contexto

Hoy los pedidos de clientes (cambios) y los encargos del papá para la obra se anotan sueltos en WhatsApp, y se pierden. La idea es tener un **asistente al que le hablas por WhatsApp** (texto o audio), en lenguaje natural:

- "Recuérdame mañana a las 9 llamar a Pedro por los cambios del logo"
- "El cliente de la casa de la calle Los Aromos quiere cambiar el piso del baño, mover el enchufe y cotizar ventanas" → lo guarda, te avisa y **la IA lo desglosa** en subtareas, preguntas para el cliente e ideas
- El papá: "recuérdale a mi hijo que traiga 3 sacos de cemento mañana a las 8" → te llega la notificación a ti
- "Agrega a la lista de la obra 2 rollos de alambre" / "¿qué falta comprar?"

Te llega la notificación al celular como mensaje de WhatsApp, con botones **✅ Listo / ⏰ +1 h / 📅 Mañana**.

El repo está vacío (solo `README.md`), así que se parte de cero.

**Decisiones ya tomadas:** canal WhatsApp · Python · audios + texto · multiusuario con recordatorios propios, asignar al otro y lista compartida de la obra.

---

## Arquitectura

```
 Celular (WhatsApp)
      │  mensaje / audio / botón
      ▼
 Meta WhatsApp Cloud API ──webhook HTTPS──▶  App Python (FastAPI)
      ▲                                      │
      │ respuestas y avisos                  ├─ audio → Transcripción (Whisper vía API)
      │                                      ├─ texto → Agente Claude (tool use)
      └──────────────────────────────────────┤        └─ herramientas: crear/listar/posponer/
                                             │           completar recordatorios, lista obra, desglose
                                             ├─ PostgreSQL (usuarios, recordatorios, lista, historial)
                                             └─ Scheduler (cada 30 s busca recordatorios vencidos y los envía)
```

Un solo proceso siempre encendido (webhook + scheduler) y una base de datos Postgres.

### Stack
| Pieza | Elección | Por qué |
|---|---|---|
| WhatsApp | **WhatsApp Cloud API oficial de Meta** (directo, sin Twilio) | Gratis para empezar, sin intermediarios. Las librerías no oficiales (whatsapp-web.js, Baileys, neonize) violan los términos y arriesgan que baneen el número: descartadas. |
| Servidor | FastAPI + Uvicorn | Webhook simple, asíncrono |
| IA | SDK `anthropic` (Python), **tool runner** (`client.beta.messages.tool_runner` + `@beta_tool`) | La IA decide qué herramienta usar; el código ejecuta y guarda |
| Modelo | `claude-opus-5-5` por defecto, configurable con `CLAUDE_MODEL` (ver Costos) | |
| Audio | Interfaz `transcribe(bytes) -> str`; implementación con Whisper por API (Groq u OpenAI) | La API de Claude no recibe audio; queda intercambiable |
| BD | PostgreSQL (SQLite en desarrollo) + SQLAlchemy 2 + Alembic | |
| Scheduler | APScheduler dentro del mismo proceso, consultando la BD | Los recordatorios viven en la BD → sobreviven reinicios |
| Fechas | `zoneinfo` + `python-dateutil` (recurrencias con RRULE) | |
| Hosting | Railway (app + Postgres, deploy desde GitHub, ~US$5/mes) | Siempre encendido (los planes gratis que "duermen" no sirven para el scheduler) |
| Tests | pytest + reloj inyectable + clientes falsos de WhatsApp/Claude | |

---

## Detalles clave de WhatsApp (lo que más condiciona el diseño)

1. **Ventana de 24 h:** si el usuario le escribió al bot en las últimas 24 h, el bot puede mandar mensajes libres (con botones). Fuera de esa ventana **solo puede enviar plantillas aprobadas por Meta**. Por eso:
   - Se crea una plantilla categoría *utility*, p. ej. `recordatorio`: "⏰ Recordatorio: {{1}}" con botones rápidos "Listo" / "Posponer".
   - Al enviar un aviso, el código revisa `ultimo_mensaje_entrante` del usuario: dentro de la ventana → mensaje interactivo; fuera → plantilla.
2. **Costos de Meta (cambio desde el 1-oct-2026, según [respond.io](https://respond.io/blog/whatsapp-pricing-change-2026.md); confirmar en la página de precios de Meta):** 1.000 mensajes de servicio gratis al mes por número; las plantillas *utility* se cobran por mensaje según el país (centavos de dólar). Para 2 personas debería salir en pocos dólares al mes.
3. **Número de prueba primero:** Meta da un número de prueba gratis que puede escribirle a **hasta 5 números verificados** ([guía de Meta](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)), suficiente para ti y tu papá mientras se desarrolla. Para uso definitivo: un número propio (un chip prepago que **no** esté usado en la app de WhatsApp). Las plantillas creadas con el número de prueba no se traspasan, así que hay que volver a crearlas.
4. **Webhook:** verificación GET con `verify_token`, validación de firma `X-Hub-Signature-256` con el app secret, responder 200 rápido y procesar en segundo plano, y descartar duplicados por `message.id` (Meta reintenta).
5. **Mensajes reenviados:** puedes **reenviarle al bot** el mensaje del cliente o del papá tal cual → lo convierte en recordatorio. Esto reemplaza el "anotarlo en WhatsApp".

---

## Modelo de datos (tablas)

- **usuarios**: `id`, `wa_id` (número), `nombre`, `alias` (["papá", "viejo"]), `zona_horaria`, `hora_resumen_diario`, `es_admin`, `ultimo_mensaje_entrante`, `activo`
- **recordatorios**: `id`, `dueño_id` (a quién se avisa), `creado_por_id`, `titulo`, `detalle`, `tipo` (recordatorio | evento), `fecha_hora` (UTC), `avisar_antes_min`, `recurrencia` (RRULE o null), `estado` (pendiente | enviado | completado | cancelado), `etiqueta` (p. ej. nombre del cliente), `veces_pospuesto`, timestamps
- **subtareas**: `id`, `recordatorio_id`, `texto`, `hecha`, `orden` (resultado del desglose IA)
- **desgloses**: `recordatorio_id`, `resumen`, `preguntas_cliente` (json), `ideas` (json)
- **listas** / **items_lista**: lista compartida "Obra" (y otras a futuro): `texto`, `cantidad`, `agregado_por_id`, `comprado`, `comprado_por_id`
- **mensajes**: historial por usuario (rol, texto) para darle contexto a la IA (últimos ~20 turnos)
- **mensajes_procesados**: `wa_message_id` para evitar duplicados

---

## La IA: agente con herramientas

Cada mensaje entrante → una llamada al tool runner con:
- **System prompt fijo** (en español, tono breve de WhatsApp): reglas para interpretar fechas ("mañana", "el lunes", "en 2 horas", "a la tarde" = 15:00 por defecto), confirmar siempre lo agendado con fecha legible, preguntar si falta la hora, usar los alias de usuarios.
- **Contexto por turno** en el mensaje del usuario (no en el system, para no romper el caché): fecha/hora actual en su zona horaria, nombre del usuario, usuarios a los que puede asignar.
- **Historial** como texto plano (sin bloques de *thinking* de turnos anteriores), ventana de los últimos turnos.

Herramientas (`@beta_tool`, con `strict: true` en el esquema):
| Herramienta | Qué hace |
|---|---|
| `crear_recordatorio(titulo, fecha_hora_iso, para?, detalle?, tipo?, avisar_antes_min?, recurrencia?, etiqueta?)` | `para` = alias de otro usuario → se le notifica de inmediato "Papá te dejó un recordatorio: …" |
| `listar_recordatorios(desde?, hasta?, etiqueta?, incluir_asignados?)` | "¿qué tengo hoy?", "¿qué cambios tengo pendientes del cliente X?" |
| `actualizar_recordatorio(id, …)` / `posponer_recordatorio(id, minutos o nueva_fecha)` | "cámbialo para las 5" |
| `completar_recordatorio(id)` / `cancelar_recordatorio(id)` | si lo creó otro, se le avisa al creador "Juan completó: …" |
| `agregar_item_lista(texto, cantidad?)`, `ver_lista()`, `marcar_comprado(item)` | lista de la obra compartida |
| `desglosar(recordatorio_id)` | dispara el desglose (abajo) |

Detalles técnicos (de la guía de la API de Claude):
- `tool_choice` en `auto` (Opus 5.5 rechaza forzar una herramienta) + `strict: true` para que los argumentos siempre sean válidos.
- `output_config.effort = "low"` para la conversación normal (rápido y barato).
- **Prompt caching** sobre system + herramientas.
- `fallbacks: "default"` con el beta `server-side-fallback-2026-07-01`, y revisar `stop_reason == "refusal"` antes de leer la respuesta.
- Errores de la API: cadena `RateLimitError` → `APIStatusError` → `APIConnectionError`; si falla, responder "No pude procesarlo, intenta de nuevo" y no perder el mensaje.
- Validación en el código: la fecha debe ser futura y con zona horaria; si no, se le devuelve el error a la IA (`is_error`) para que pregunte.

### Desglose con IA
Cuando el texto es largo, menciona a un cliente o el usuario dice "desglósalo":
- Llamada aparte con `effort: "high"` y **salida estructurada** (`output_config.format` con esquema JSON): `resumen`, `subtareas[]`, `preguntas_para_el_cliente[]`, `ideas[]`, `materiales[]` (si es de obra).
- Se guarda en `subtareas`/`desgloses` y se envía como segundo mensaje. Si hay materiales, ofrece "¿los agrego a la lista de la obra?".

### Audios
Webhook recibe `type: audio` → descarga el media con el token de Meta → `transcribe()` → se procesa igual que texto. El bot responde mostrando lo que entendió ("🎙️ Entendí: …") para detectar errores de transcripción.

---

## Notificaciones (scheduler)

- Job cada 30 s: busca `estado = pendiente AND fecha_hora - avisar_antes <= ahora`, bloquea la fila, envía y marca `enviado`.
- Recurrentes: al enviar, calcula la próxima fecha con la RRULE y crea/reprograma.
- Botones: `Listo` → completado; `+1 h` → reprograma; `Mañana` → mismo horario al día siguiente. Los clics llegan al webhook como respuestas de botón con un `payload` (`done:123`, `snooze:123:60`), y se resuelven **sin pasar por la IA**.
- **Resumen diario** opcional a la hora que elija cada usuario: "Buenos días ☀️ Hoy tienes: … · Lista obra: 4 cosas pendientes".
- Si un recordatorio enviado no se marca como hecho en X horas, un segundo aviso (configurable).

---

## Multiusuario

- Usuarios identificados por su número de WhatsApp. **Lista blanca:** números desconocidos se ignoran (protege tu cuenta de Claude y de Meta).
- Tú eres admin; agregas a tu papá con un comando: `/agregar +<código país><número> Papá alias:papá,viejo` (la zona horaria se pide al registrarlo).
- Asignar: el `dueño` recibe el aviso; el `creador` recibe la confirmación de que se completó.
- Recordatorios propios son privados; la lista de la obra es compartida y cada cambio puede avisar al otro (configurable para no llenar de mensajes).

---

## Estructura del proyecto

```
pyproject.toml · .env.example · Dockerfile · alembic/ · README.md
app/
  main.py              # FastAPI + lifespan (arranca el scheduler)
  config.py            # pydantic-settings (tokens, CLAUDE_MODEL, etc.)
  db.py · models.py
  whatsapp/
    webhook.py         # GET verificación, POST mensajes, firma, dedupe
    client.py          # send_text, send_buttons, send_template, download_media
    parser.py          # payload de Meta → IncomingMessage (texto/audio/botón)
  ai/
    agent.py           # tool runner, historial, contexto por turno
    tools.py           # @beta_tool → llaman a reminders/ y lists/
    breakdown.py       # desglose con salida estructurada
    prompts.py
  speech/transcribe.py
  reminders/service.py · scheduler.py · formatting.py   # lógica, envíos, fechas en español
  lists/service.py
  users/service.py     # lista blanca, alias, comandos admin
tests/  (service, scheduler, webhook, parser, tools)
```

Regla de diseño: **la lógica de negocio vive en `reminders/`, `lists/` y `users/`**; las herramientas de la IA y los botones son capas delgadas que la llaman. Así se testea sin IA ni WhatsApp.

---

## Costos estimados (2 personas, ~15 mensajes/día cada una)

| Ítem | Aprox. mensual |
|---|---|
| Hosting Railway (app + Postgres) | ~US$5 |
| WhatsApp (plantillas fuera de la ventana de 24 h) | pocos US$ (depende de la tarifa del país) |
| Transcripción de audios | < US$1 |
| Claude con `claude-opus-5-5` (US$4 / US$20 por millón de tokens, effort low + caché) | ~US$15–30 |
| *Alternativa:* Claude con `claude-haiku-5-5` (US$0,10 / US$0,50) | ~US$1 |

El modelo se cambia con una variable de entorno (`CLAUDE_MODEL`), así que puedes partir con Opus 5.5 y probar Haiku 5.5 para ver si te basta. La decisión es tuya.

---

## Fases

**Fase 0 – Cuentas (las haces tú, te guío paso a paso en el README):** cuenta de Meta for Developers + app de WhatsApp, número de prueba, verificar tu número y el de tu papá, token permanente (System User), API key de Anthropic con saldo, API key de transcripción, cuenta de Railway.

**Fase 1 – MVP (solo tú, texto):** esqueleto FastAPI + webhook + BD + agente con crear/listar/posponer/completar + scheduler + botones + plantilla `recordatorio`. Probado localmente con un túnel (cloudflared/ngrok).

**Fase 2 – Multiusuario + obra:** lista blanca, comandos admin, alias, asignar al otro, avisos al creador, lista compartida de la obra.

**Fase 3 – IA extra:** audios, desglose estructurado, etiquetas por cliente ("pendientes del cliente X"), resumen diario, recurrencias.

**Fase 4 – Producción:** deploy en Railway, número propio de WhatsApp, recrear plantillas, backups de la BD, logs y alertas de errores.

**Ideas a futuro:** mandar **foto** de una lista escrita a mano o de un plano → items en la lista de la obra (Claude lee imágenes); sincronizar con Google Calendar; panel web para ver todo.

---

## Verificación

- **Tests unitarios (pytest):** parser de payloads de Meta (texto, audio, botón, reenviado); servicio de recordatorios (crear, posponer, recurrencia, zona horaria, asignación y aviso al creador); scheduler con reloj falso (envía una sola vez, elige plantilla vs. mensaje libre según la ventana de 24 h); webhook (firma inválida → 403, mensaje duplicado → ignorado, número desconocido → ignorado); herramientas con BD de prueba.
- **Pruebas manuales end-to-end** con el número de prueba, desde los dos celulares:
  1. "Recuérdame en 2 minutos tomar agua" → llega a los 2 min con botones; "+1 h" lo reprograma.
  2. El papá: "recuérdale a Juan comprar clavos mañana 8:00" → te llega el aviso de inmediato y al día siguiente; al marcar Listo, el papá recibe la confirmación.
  3. Audio de 20 s con un pedido de cliente → transcripción + recordatorio + desglose.
  4. "Agrega cemento a la lista de la obra" desde un celular → "¿qué falta?" desde el otro lo muestra.
  5. Recordatorio para cuando no has escrito en más de 24 h → llega como plantilla.
  6. Reiniciar el servidor con recordatorios pendientes → igual se envían.
