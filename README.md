# notificación

Asistente por WhatsApp para agendar recordatorios y eventos conversando con una IA (Claude), con varios usuarios (familia y negocio), y base del futuro sistema de gestión de **Monardez Soft**.

El plan completo está en [PLAN.md](PLAN.md).

## Estado: Fase 1 lista (base + recordatorios)

Lo que ya funciona:

- Le escribes al bot por WhatsApp en lenguaje natural ("recuérdame mañana a las 9 llamar a Pedro", "¿qué tengo hoy?", "posponlo 2 horas", "ya lo hice") y Claude crea, lista, pospone, cambia, completa o cancela recordatorios.
- **Asignar a otra persona**: "recuérdale a mi hijo que traiga cemento mañana a las 8". A esa persona le llega un aviso de inmediato y otro a la hora indicada; quien lo creó recibe un aviso cuando se completa.
- **Avisos a la hora** con botones ✅ Listo / ⏰ +1 hora / 📅 Mañana. Si la persona no le escribió al bot en las últimas 24 h, se usa una plantilla aprobada (regla de Meta).
- **Eventos** con aviso anticipado ("reunión con Acme el jueves a las 16, avísame 30 min antes").
- **Mensajes reenviados**: reenvíale al bot el mensaje de un cliente o de tu papá y lo convierte en recordatorio, con el detalle en lista.
- **Espacios y roles**: *Familia* y *Monardez Soft*, con roles dueño / empleado / familiar. Solo se puede asignar a alguien con quien se comparte un espacio. Los números que no están registrados se ignoran.
- Panel de administración de Django para ver y editar todo.

Viene en la Fase 2: audios, lista de compras de la obra, desglose con IA de pedidos largos, resumen diario y recordatorios recurrentes. Después: clientes, cobros, proyectos y dashboard (ver el plan).

## Probar en tu computador (sin Meta)

Necesitas [uv](https://docs.astral.sh/uv/) y Python 3.12 o superior.

```bash
uv sync
cp .env.example .env            # deja WHATSAPP_CLIENTE en ClienteConsola
uv run --env-file .env python manage.py migrate
uv run --env-file .env python manage.py createsuperuser
uv run --env-file .env python manage.py inicializar --usuario TU_USUARIO --whatsapp 569XXXXXXXX --nombre "Tu nombre"
uv run --env-file .env python manage.py runserver
```

- Admin: http://localhost:8000/admin. Ahí agregas a tu papá (Usuarios → con su WhatsApp y alias, por ejemplo `papá, viejo`) y lo sumas al espacio Familia con rol *Familiar*.
- Simular un mensaje sin pasar por WhatsApp (la respuesta aparece en la terminal). Para los mensajes de texto necesitas `ANTHROPIC_API_KEY` en el `.env`:

  ```bash
  uv run --env-file .env python manage.py simular_mensaje 569XXXXXXXX "recuérdame en 2 minutos tomar agua"
  uv run --env-file .env python manage.py simular_mensaje 569XXXXXXXX --boton rec:listo:1
  ```

- Enviar los avisos que ya tocan: `python manage.py enviar_avisos` una vez, o deja corriendo el worker `python manage.py qcluster` (revisa cada minuto).
- Tests: `uv run pytest` · Lint: `uv run ruff check .`

## Configurar WhatsApp (Meta)

1. En [developers.facebook.com](https://developers.facebook.com/) crea una app de tipo **Business** y agrégale el producto **WhatsApp**.
2. En *WhatsApp → API Setup*:
   - Copia el *Phone number ID* del número de prueba en `WHATSAPP_PHONE_NUMBER_ID`.
   - Agrega tu número y el de tu papá como destinatarios (hasta 5) y verifícalos con el código que llega por WhatsApp.
3. **Token permanente** (el de esa página dura 24 h):
   - Entra a *Configuración del negocio → Usuarios del sistema* y crea un usuario administrador.
   - Asígnale la app.
   - Genera un token con los permisos `whatsapp_business_messaging` y `whatsapp_business_management`, y ponlo en `WHATSAPP_TOKEN`.
4. Copia el **App secret** (*Configuración de la app → Básica*) en `WHATSAPP_APP_SECRET`. Con él se verifica que los mensajes vengan de Meta.
5. **Webhook** (*WhatsApp → Configuration*):
   - Callback URL: `https://TU-DOMINIO/whatsapp/webhook/`.
   - Verify token: el mismo texto de `WHATSAPP_VERIFY_TOKEN`.
   - Suscríbete al campo `messages`.
   - Para probar desde tu computador, expón el servidor con `cloudflared tunnel --url http://localhost:8000` (o ngrok) y agrega ese dominio a `DJANGO_ALLOWED_HOSTS`.
6. **Plantillas** (*WhatsApp Manager → Plantillas de mensajes*), categoría **Utilidad**, idioma **Español (es)**. Meta no acepta que el cuerpo empiece o termine con la variable:
   - `recordatorio`:
     - Cuerpo: `Tienes un recordatorio: {{1}}. Toca un botón para responder.`
     - 3 botones de **respuesta rápida**, en este orden: `Listo`, `+1 hora`, `Mañana`.
   - `aviso`:
     - Cuerpo: `Aviso de tu asistente: {{1}}. Escríbeme si necesitas algo.`
     - Sin botones.
7. Cambia `WHATSAPP_CLIENTE=apps.whatsapp.cliente.ClienteGraph`.

**Si el bot no te responde:** revisa el log. Si aparece `Mensaje de un número no autorizado: 54911...`, copia ese número exacto en el admin. En algunos países (Argentina, México) WhatsApp entrega el número con un dígito extra.

## Claude

- Crea una API key en [console.anthropic.com](https://console.anthropic.com/) y ponla en `ANTHROPIC_API_KEY`.
- `ASISTENTE_MODELO` viene en `claude-opus-5-5`. Para gastar menos puedes probar `claude-haiku-5-5`.
- `ASISTENTE_EFFORT=low` mantiene las respuestas rápidas y baratas.

## Publicar en Railway

1. *New Project → Deploy from GitHub repo* con este repositorio, y agrega una base **PostgreSQL**.
2. Servicio **web**:
   - Start command: `python manage.py collectstatic --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT`
   - Pre-deploy command: `python manage.py migrate`
   - Healthcheck: `/salud/`
   - Variables: las de `.env.example`, más `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS=TU-APP.up.railway.app` y `DJANGO_CSRF_TRUSTED_ORIGINS=https://TU-APP.up.railway.app`.
3. Servicio **worker** (mismo repo y variables): start command `python manage.py qcluster`.
4. Crea tu usuario y los espacios: `railway run python manage.py createsuperuser` y luego `railway run python manage.py inicializar ...`.

## Estructura

```
config/              settings, urls
apps/cuentas/        usuario propio (WhatsApp, alias, zona horaria), espacios, membresías y roles
apps/whatsapp/       webhook (firma, duplicados), parser, cliente de la API, envío según la ventana de 24 h
apps/recordatorios/  modelo, lógica (servicios.py), botones, avisos, tarea programada
apps/asistente/      conversación con Claude, herramientas, historial, procesamiento de mensajes
tests/               pytest
```

La lógica vive en los `servicios.py`. Las herramientas de la IA, los botones de WhatsApp y el admin la llaman, así que se prueba en un solo lugar.
