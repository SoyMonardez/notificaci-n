# Plan: "notificación" — Asistente por WhatsApp + sistema web de gestión para Monardez Soft

## Contexto

Dos necesidades que comparten la misma base:

1. **Día a día (ya planificado):** dejar recordatorios y eventos conversando por WhatsApp (texto o audio). La IA los agenda, avisa con botones y desglosa los pedidos largos. Tu papá también lo usa: te asigna encargos y comparten la lista de la obra.
2. **Negocio (nuevo):** Monardez Soft ya tiene clientes y un empleado, y va a crecer. Necesitas un **sistema web con dashboard** que diga: qué cambios pidió cada cliente, cuándo te paga cada uno, cuándo se entrega cada sistema y en qué fase va, y la analítica del negocio. ¿Cuánto trabajo entra? ¿Cuánto debería entrar de plata? ¿Cuánto pierdes? ¿Cuánto pagas? ¿Estás creciendo de un mes a otro, o en 4 meses? ¿Qué canal de captación funciona? WhatsApp sigue siendo la puerta de entrada rápida ("el cliente X me pagó la cuota 2") y el canal de avisos ("mañana vence el pago de Y").

**Decisiones tomadas:**
- WhatsApp Cloud API oficial de Meta.
- **Django**, todo en Python.
- Audios y texto.
- Familia: recordatorios propios, asignar al otro y lista de la obra.
- El empleado solo ve **sus proyectos y tareas**, nunca las finanzas.
- Cobros mixtos: cuotas/hitos por proyecto, **mensualidades recurrentes (SaaS, mantención)** y pago único (venta única).
- Orden: **primero recordatorios, con la base lista para el negocio**.

El repo solo tiene `README.md` y `PLAN.md`. Este archivo reemplaza a `PLAN.md`.

---

## Arquitectura

```
 WhatsApp (tú, papá, empleado)                Navegador (tú, empleado)
        │                                              │
        ▼                                              ▼
 Meta Cloud API ──webhook──▶ ┌──────────── Proyecto Django ─────────────┐
        ▲                    │ whatsapp/   asistente/ (Claude + tools)  │
        │  avisos            │ recordatorios/ listas/                   │
        └────────────────────│ clientes/ captacion/ proyectos/ finanzas/│
                             │ analitica/ (dashboard)  cuentas/ (roles) │
                             └───────┬──────────────────────┬───────────┘
                                     │                      │
                              PostgreSQL            Worker Django-Q2
                                                    (procesa mensajes,
                                                     envía avisos cada
                                                     minuto, genera cobros
                                                     mensuales, resúmenes)
```

Dos procesos del mismo código: **web** (gunicorn: webhook + sitio + admin) y **worker** (`qcluster`). Una base Postgres.

### Stack
| Pieza | Elección |
|---|---|
| Framework | **Django 5.2 LTS** (soporte hasta 2028). Login, permisos, admin y migraciones incluidos |
| Tareas y agenda | **Django-Q2** con la BD como cola (sin Redis). Tareas asíncronas para procesar mensajes y tareas programadas cada minuto. Si el negocio crece mucho se cambia a Celery |
| Web / dashboard | Plantillas Django + **HTMX** (filtros sin recargar) + **Tailwind CSS** + **Chart.js** |
| Carga de datos | **Django Admin** personalizado desde el día 1. Vistas propias donde haga falta |
| IA | SDK `anthropic` con un ciclo de herramientas propio (control de fallbacks, errores y tests), modelo configurable con `ASISTENTE_MODELO` (por defecto `claude-opus-5-5`) |
| Audio | Interfaz `transcribir(bytes)` con Whisper por API (intercambiable) |
| BD | PostgreSQL (SQLite en desarrollo). Montos en `Decimal` |
| Hosting | Railway: servicio web + worker + Postgres (~US$5–10/mes) |
| Tests | pytest-django + factory-boy + reloj inyectable + clientes falsos de WhatsApp/Claude |

---

## Usuarios, espacios y roles

- **Modelo de usuario propio desde el día 1** (`AUTH_USER_MODEL`): número de WhatsApp, zona horaria, hora del resumen diario. Hacerlo después en Django es muy doloroso. Tu papá puede existir sin contraseña (solo WhatsApp).
- **Espacios:** `Familia` (tú + papá) y `Monardez Soft` (tú + empleado). Cada recordatorio, lista y dato del negocio pertenece a un espacio. Tu papá nunca ve datos del negocio y el empleado nunca ve los de la familia. Además deja la puerta abierta a vender esto como SaaS en el futuro (cada cliente sería un espacio).
- **Membresía con rol por espacio:** `dueño`, `empleado`, `familiar`.
  - Dueño (tú): todo.
  - Empleado: proyectos, fases, cambios y tareas **asignados a él**, y sus recordatorios. Sin clientes completos ni finanzas ni analítica.
  - Familiar: recordatorios, asignaciones y lista de la obra.
- Los permisos se aplican **en las consultas** (querysets filtrados por rol), no solo ocultando botones. Lo mismo vale para las herramientas de la IA: cada rol solo recibe las que le corresponden.
- Lista blanca: número de WhatsApp desconocido = se ignora.

---

## Módulo 1 — Recordatorios y familia (sin cambios de fondo)

- **Recordatorio**: `espacio`, `dueño`, `creado_por`, `titulo`, `detalle`, `tipo` (recordatorio/evento), `fecha_hora` (UTC), `avisar_antes_min`, `recurrencia` (RRULE), `estado`, `etiqueta`, y vínculos opcionales a `cliente`/`proyecto`/`cobro` (así los avisos del negocio también son recordatorios). Además `Subtarea` y `Desglose` (resumen, preguntas para el cliente, ideas, materiales).
- **Lista / ItemLista**: lista compartida "Obra" (texto, cantidad, agregado_por, comprado).
- **Avisos:**
  - Tarea programada cada minuto: busca vencidos, envía y marca.
  - Recurrentes con RRULE.
  - Botones ✅ Listo / ⏰ +1 h / 📅 Mañana, resueltos sin IA mediante el payload del botón.
  - Resumen diario opcional y segundo aviso si no se marcó hecho.
- **Asignar al otro:** el dueño del recordatorio recibe el aviso y el creador recibe "completado".

## Módulo 2 — Negocio Monardez Soft (nuevo)

**clientes/**
- `Cliente`: nombre, empresa, WhatsApp, email, rubro, **origen** (referido, Instagram, Facebook, web, WhatsApp, otro), estado (activo/inactivo/perdido), fecha de alta.
- `Interaccion` (seguimiento): fecha, tipo (llamada, reunión, mensaje), nota y **próxima acción con fecha**. La próxima acción crea automáticamente un recordatorio.

**captacion/**
- `Oportunidad`: prospecto o cliente, servicio, monto estimado, **etapa** (nuevo → contactado → propuesta enviada → negociación → ganada/perdida), origen, motivo de pérdida, fecha de cierre.
- Al ganarla se crea el `Proyecto` o la `Suscripcion`.
- Vista **kanban** por etapa.

**proyectos/**
- `Proyecto`: cliente, nombre, tipo (a medida / SaaS / venta única), monto total, inicio, **entrega comprometida**, estado, responsable.
- `Fase`: nombre, orden, estado, % de avance, fechas, asignado a.
- `SolicitudCambio`: lo que pide el cliente, fase, estado, asignado a, **¿se cobra?** y monto extra. Viene de WhatsApp con su desglose IA.

**finanzas/** (lo que te deben, lo que entra y lo que sale):
- `Cobro`: la unidad que se espera cobrar. Cliente, **origen** (cuota de proyecto / mensualidad / pago único / cambio extra), monto, moneda, **vencimiento**, estado (pendiente / pagado / parcial / vencido / anulado).
- `PlanDeCuotas` del proyecto: genera sus `Cobro`. Una cuota puede vencer en una fecha o al terminar una fase (hito).
- `Suscripcion` (SaaS / mantención): cliente, producto, monto mensual, día de cobro, inicio, **fecha de baja**, estado. Una tarea programada genera el `Cobro` de cada mes (una sola vez; si el día de cobro es 31 en un mes de 30 días, usa el último día del mes).
- `Pago`: el dinero que realmente llegó (fecha, monto, medio). Puede ser parcial y se aplica a un `Cobro`.
- `Gasto`: categoría (sueldo, software/herramientas, hosting, publicidad, impuestos, otros), monto, fecha, proveedor, ¿recurrente?, proyecto opcional (para calcular el margen por proyecto). Los recurrentes se generan solos cada mes.
- Moneda principal configurable (`MONEDA_PRINCIPAL`). Cada monto guarda su moneda; la conversión multimoneda queda para después.

## Módulo 3 — Analítica y dashboard (nuevo)

Las métricas se calculan con consultas en `analitica/servicios.py` (funciones puras y testeadas). Al cierre de cada mes una tarea guarda un `ResumenMensual` (ingresos, gastos, MRR, clientes activos, etc.) para tener la historia aunque después se editen datos.

**Tarjetas (KPIs) del período:** cobrado · gastos · **ganancia** · **MRR** (ingreso recurrente mensual de suscripciones activas) · por cobrar a 30 días · **vencido** · clientes activos · proyectos activos · tasa de conversión.

**Tus preguntas → qué muestra:**
| Pregunta | Métrica / gráfico |
|---|---|
| ¿Cuánto trabajo me llega? | Oportunidades nuevas, proyectos nuevos y solicitudes de cambio por mes. Carga actual: fases en curso, próximas entregas y proyectos atrasados |
| ¿Cuánto debería entrarme? | Por cobrar a 30/60/90 días (cuotas + mensualidades + únicos), MRR y su evolución, ingreso recurrente vs. único |
| ¿Cuánto estoy perdiendo? | Morosidad (vencido y días de atraso por cliente), oportunidades perdidas (monto y motivo), **churn** (suscripciones dadas de baja y MRR perdido), **cambios hechos sin cobrar** |
| ¿Cuánto estoy pagando? | Gastos por mes y categoría, sueldo, margen total y por proyecto |
| ¿Estoy creciendo? (1 a 4 meses) | Selector de período: este mes vs. anterior, últimos 3 y 4 meses, con % de variación. Líneas mensuales de ingresos, gastos, ganancia, MRR y clientes |
| ¿Qué captación funciona? | Clientes y monto ganado por origen, conversión por canal, tiempo promedio de cierre |

**Otras vistas:**
- Ficha de cliente: proyectos, cobros, historial de seguimiento y cambios.
- Ficha de proyecto: fases con barra de avance, cambios y cuotas.
- Calendario de cobros y entregas.
- Vista "Mis tareas" del empleado.

**Resumen con IA:** el lunes llega por WhatsApp (y aparece en el dashboard) un análisis breve: "Este mes cobraste $X (+20% vs. septiembre), tienes $Y vencido con 2 clientes y la entrega de Z es en 3 días". **Los números los calcula el código.** La IA solo los redacta, así no inventa cifras.

---

## WhatsApp + IA conectados al negocio

**Herramientas según rol** (`asistente/herramientas.py` arma la lista por usuario y espacio):
- **Todos:** crear/listar/posponer/completar recordatorios. Familia: lista de la obra.
- **Dueño, además:**
  - `registrar_pago` ("Pérez me pagó la cuota 2", "llegó la mensualidad de Acme")
  - `registrar_cambio` ("el cliente X pidió cambiar el login y agregar reportes" → SolicitudCambio + desglose)
  - `nuevo_prospecto` ("Juan de la ferretería, por Instagram, quiere un sistema de inventario")
  - `registrar_gasto`, `registrar_seguimiento`
  - `consultar_negocio` ("¿cuánto me deben?", "¿cómo voy este mes?", "¿qué entregas tengo esta semana?"), que responde con los números calculados por `analitica/`
- **Empleado:** ver sus tareas, actualizar el avance de una fase y marcar un cambio como hecho.

**Avisos automáticos del negocio (para ti):**
- "Mañana vence la cuota 2 de Pérez ($…)"
- "Acme tiene un pago vencido hace 5 días"
- "Entrega del sistema de Z en 3 días (fase Pruebas al 60%)"
- "Hace 10 días que no hablas con el prospecto Juan"
- Resumen semanal

La IA elige el espacio según el contenido: si menciona un cliente o proyecto → Monardez Soft; si no → Familia. Si hay duda, pregunta.

### Detalles técnicos de WhatsApp
- **Ventana de 24 h:**
  - Si el usuario le escribió al bot en las últimas 24 h, el bot puede mandar mensajes libres con botones.
  - Fuera de esa ventana solo puede enviar **plantillas aprobadas por Meta**: `recordatorio` ("⏰ Recordatorio: {{1}}" con botones Listo/Posponer) y `aviso_negocio`, ambas categoría *utility*.
  - El código revisa `ultimo_mensaje_entrante` para decidir cuál usar.
- **Costos de Meta:** desde el 1-oct-2026 hay 1.000 mensajes de servicio gratis al mes por número y las plantillas *utility* se cobran por mensaje según el país. Fuente: [respond.io](https://respond.io/blog/whatsapp-pricing-change-2026.md); confirmar en la página de precios de Meta.
- **Número de prueba:** gratis y puede escribirle a **hasta 5 números verificados** ([guía de Meta](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/)), suficiente para ti, tu papá y tu empleado. En producción hace falta un número propio (un chip que no use la app de WhatsApp) y volver a crear las plantillas.
- **Webhook:**
  - Verificación GET con `verify_token`.
  - Firma `X-Hub-Signature-256` con el app secret.
  - Responder 200 al instante y procesar en el worker.
  - Deduplicar por `message.id`.
- **Audios:** se descarga el media con el token de Meta y se transcribe. El bot responde "🎙️ Entendí: …".
- **Mensajes reenviados:** reenviarle al bot el mensaje de un cliente o de tu papá lo convierte en recordatorio o en cambio.
- **No usar** librerías no oficiales (whatsapp-web.js, Baileys, neonize): violan los términos y arriesgan que baneen el número.

### Detalles técnicos de Claude
- **Herramientas:** `tool_choice: auto` (Opus 5.5 no permite forzar una herramienta) + `strict: true` en los esquemas.
- **Effort:** `low` para el chat; `high` + salida estructurada (`output_config.format`) para el desglose y el resumen semanal.
- **Prompt caching** sobre system + herramientas. La fecha y hora actual, el usuario y el espacio van en el mensaje del turno, no en el system.
- **Historial** en texto plano (sin bloques de *thinking* de turnos anteriores), con los últimos ~20 turnos.
- **Errores y rechazos:**
  - `fallbacks: "default"` con el beta `server-side-fallback-2026-07-01`, y revisar `stop_reason == "refusal"`.
  - Capturar `RateLimitError` → `APIStatusError` → `APIConnectionError`, y si falla responder "no pude procesarlo".
- **Validación en el código:** la fecha debe ser futura, el monto mayor a 0 y el cliente debe existir. Si algo falla, se le devuelve a la IA con `is_error` para que pregunte.

---

## Estructura del proyecto

```
manage.py · pyproject.toml · .env.example · Procfile (web + worker) · README.md
config/            settings (variables de entorno) + settings_test, urls, wsgi
apps/
  cuentas/         Usuario propio, Espacio, Membresia, roles, mixins de permisos
  whatsapp/        webhook (vista), firma, dedupe, cliente (enviar texto/botones/plantilla/media), parser
  asistente/       agente Claude, herramientas por rol, historial, desglose, transcripción
  recordatorios/   modelos, servicios, tareas programadas (avisos, recurrencias, resumen diario)
  listas/          listas compartidas
  clientes/        Cliente, Interaccion
  captacion/       Oportunidad, kanban
  proyectos/       Proyecto, Fase, SolicitudCambio
  finanzas/        Cobro, PlanDeCuotas, Suscripcion, Pago, Gasto (+ generación mensual)
  analitica/       servicios.py (métricas), ResumenMensual, vistas del dashboard
templates/ · static/
tests/             por app + permisos + métricas
```

Regla: **la lógica vive en `servicios.py` de cada app.** Las vistas web, el admin, las herramientas de la IA y los botones de WhatsApp la llaman. Así se testea una sola vez y nada se duplica.

---

## Fases

| Fase | Contenido | Resultado usable |
|---|---|---|
| **0 – Cuentas** (tú) | Meta for Developers + número de prueba + verificar números · API key de Anthropic · API key de transcripción · Railway | — |
| **1 – Base + recordatorios** ✅ código listo | Proyecto Django, usuario propio, espacios, roles, admin, Django-Q2, webhook, agente con herramientas de recordatorios, asignar a otra persona, avisos con botones, plantillas. Deploy en Railway (pendiente: requiere tus cuentas) | Tú agendas por WhatsApp y te llegan los avisos |
| **2 – Familia** | Papá, lista de la obra, audios, desglose IA, resumen diario, recurrentes | Lo usan los dos |
| **3 – Negocio: datos** | Clientes, proyectos, fases, cambios, cobros (cuotas, mensualidades, únicos), pagos, gastos. Carga vía admin + WhatsApp. Avisos de cobros y entregas. Empleado con login y "Mis tareas" | Todo el negocio registrado y con avisos |
| **4 – Dashboard** | KPIs, gráficos mensuales, comparativa 1–4 meses, por cobrar, morosidad, MRR/churn, gastos, margen por proyecto, fichas, calendario, resumen semanal IA | Ves si estás creciendo |
| **5 – Captación + producción** | Pipeline kanban, origen y conversión por canal, seguimientos automáticos, número propio de WhatsApp, backups, 2FA para tu cuenta, monitoreo de errores | Sistema completo |

**Ideas a futuro:**
- Avisos de cobro enviados al cliente (opt-in, con plantilla).
- Pasarela de pago que marque los pagos sola.
- Facturación electrónica.
- Formulario de la web de Monardez Soft que cree prospectos automáticamente.
- Portal donde el cliente ve el avance de su proyecto.
- Foto de una lista o boleta → ítems o gastos (Claude lee imágenes).
- Exportar a Excel.
- Vender el sistema como SaaS (los espacios ya lo permiten).

---

## Costos estimados (mensual)

| Ítem | Aprox. |
|---|---|
| Railway (web + worker + Postgres) | US$5–10 |
| WhatsApp (plantillas fuera de la ventana de 24 h; 1.000 mensajes de servicio gratis al mes desde oct-2026, confirmar la tarifa del país en Meta) | pocos US$ |
| Transcripción | < US$1 |
| Claude `claude-opus-5-5` (3 personas, effort low + caché) | ~US$20–40 |
| Alternativa `claude-haiku-5-5` | ~US$1–2 |

El modelo se cambia con `ASISTENTE_MODELO`; la decisión es tuya.

---

## Verificación

**Tests (pytest-django):**
- **Permisos:**
  - El empleado no accede a finanzas ni analítica por URL, admin ni herramientas de la IA.
  - Tu papá no ve nada de Monardez Soft.
  - Un número desconocido se ignora.
- **Finanzas:**
  - La suscripción genera un solo cobro por mes, incluido el caso del día 31.
  - La cuota vinculada a una fase vence al terminar esa fase.
  - Un pago parcial deja el cobro en estado "parcial".
  - Un cobro vencido aparece en morosidad.
- **Analítica:** con datos de prueba conocidos (4 meses con valores fijos), los KPIs, el MRR, el churn y el % de variación dan exactamente lo esperado.
- **Recordatorios y WhatsApp:**
  - El scheduler envía una sola vez.
  - Elige plantilla o mensaje libre según la ventana de 24 h.
  - Webhook: firma inválida → 403, mensaje duplicado → se ignora.
  - Parser de texto, audio, botón y mensaje reenviado.

**Manual:**
1. Comando `python manage.py cargar_datos_demo` con clientes, proyectos, cobros y gastos ficticios de 4 meses. Abrir el dashboard y comparar las cifras con una planilla hecha a mano.
2. Por WhatsApp: "Pérez me pagó la cuota 2" → el cobro queda pagado y el dashboard se actualiza. "Mañana vence…" llega a la hora.
3. Entrar como empleado: solo aparecen sus proyectos y tareas, y las URLs de finanzas responden 403.
4. Los flujos de la familia del plan anterior: recordatorio en 2 minutos, papá asigna, audio, lista de la obra, plantilla fuera de las 24 h, reinicio del servidor sin perder avisos.
