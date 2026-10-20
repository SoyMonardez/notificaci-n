"""Conversación con Claude: arma el contexto, ejecuta las herramientas y devuelve el texto de respuesta."""

import logging
from datetime import timedelta

import anthropic
from django.conf import settings
from django.utils import timezone

from apps.cuentas.servicios import companeros
from apps.recordatorios.formato import fecha_larga

from .herramientas import Herramientas
from .models import MensajeConversacion
from .prompts import SISTEMA

logger = logging.getLogger(__name__)

MAX_PASOS = 8
MAX_TOKENS = 8000
MAX_HISTORIAL = 20
VENTANA_HISTORIAL = timedelta(hours=24)
# Si el modelo rechaza por política, la API reintenta en el modelo de respaldo que Anthropic recomienda.
BETA_FALLBACK = "server-side-fallback-2026-07-01"

RESPUESTA_ERROR = "Uy, no pude procesar tu mensaje ahora 😕. Intenta de nuevo en un rato."
RESPUESTA_ERROR_PARCIAL = "⚠️ Se me cortó la conexión, pero alcancé a guardar los cambios. Pregúntame «¿qué tengo pendiente?» para revisar."
RESPUESTA_RECHAZO = "No puedo ayudarte con eso. Si es un recordatorio, ¿me lo dices de otra forma?"
RESPUESTA_ENREDO = "Me enredé con eso 😅. ¿Me lo dices de nuevo, más simple?"

_cliente = None


def cliente_claude():
    global _cliente
    if _cliente is None:
        _cliente = anthropic.Anthropic(timeout=60.0, max_retries=2)
    return _cliente


def contexto(usuario, ahora):
    tz = usuario.tz
    desfase = ahora.astimezone(tz).strftime("%z")
    lineas = [
        "[Contexto]",
        f"Ahora: {fecha_larga(ahora, tz)} ({usuario.zona_horaria}, UTC{desfase[:3]}:{desfase[3:]})",
        f"Usuario: {usuario.nombre_visible}",
    ]
    personas = []
    for persona in companeros(usuario):
        alias = persona.lista_alias()
        personas.append(persona.nombre_visible + (f" (alias: {', '.join(alias)})" if alias else ""))
    lineas.append(
        f"Puede asignar recordatorios a: {'; '.join(personas) if personas else 'nadie más por ahora'}"
    )
    ambitos = sorted(set(usuario.espacios.values_list("tipo", flat=True)))
    lineas.append(f"Ámbitos: {', '.join(ambitos) if ambitos else 'ninguno'}")
    return "\n".join(lineas)


def historial(usuario, ahora):
    """Últimos mensajes en texto plano, alternando roles y empezando por el usuario."""
    recientes = MensajeConversacion.objects.filter(
        usuario=usuario, creado_en__gte=ahora - VENTANA_HISTORIAL, creado_en__lte=ahora
    ).order_by("-creado_en", "-id")[:MAX_HISTORIAL]
    mensajes = []
    for mensaje in reversed(list(recientes)):
        if mensajes and mensajes[-1]["role"] == mensaje.rol:
            mensajes[-1]["content"] += "\n\n" + mensaje.texto
        else:
            mensajes.append({"role": mensaje.rol, "content": mensaje.texto})
    while mensajes and mensajes[0]["role"] != MensajeConversacion.Rol.USUARIO:
        mensajes.pop(0)
    return mensajes


def _contenido_vigente(contenido):
    """Si hubo un cambio de modelo a mitad de respuesta, se descarta lo previo salvo el texto."""
    cortes = [i for i, bloque in enumerate(contenido) if bloque.type == "fallback"]
    if not cortes:
        return list(contenido)
    corte = cortes[-1]
    return [b for b in contenido[:corte] if b.type == "text"] + list(contenido[corte + 1 :])


def responder(usuario, texto, *, ahora=None, cliente=None):
    ahora = ahora or timezone.now()
    cliente = cliente or cliente_claude()

    mensajes = historial(usuario, ahora)
    nuevo = [{"type": "text", "text": contexto(usuario, ahora)}, {"type": "text", "text": texto}]
    if mensajes and mensajes[-1]["role"] == MensajeConversacion.Rol.USUARIO:
        # La respuesta anterior se perdió (error): se junta con el mensaje nuevo.
        nuevo.insert(0, {"type": "text", "text": mensajes.pop()["content"]})
    mensajes.append({"role": "user", "content": nuevo})
    MensajeConversacion.objects.create(
        usuario=usuario, rol=MensajeConversacion.Rol.USUARIO, texto=texto, creado_en=ahora
    )

    herramientas = Herramientas(usuario, ahora)
    try:
        respuesta_final = _conversar(cliente, mensajes, herramientas)
    except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError):
        logger.exception("Falló la llamada a Claude")
        return RESPUESTA_ERROR_PARCIAL if herramientas.hubo_cambios else RESPUESTA_ERROR

    MensajeConversacion.objects.create(
        usuario=usuario, rol=MensajeConversacion.Rol.ASISTENTE, texto=respuesta_final, creado_en=ahora
    )
    return respuesta_final


def _conversar(cliente, mensajes, herramientas):
    for _ in range(MAX_PASOS):
        respuesta = cliente.beta.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=SISTEMA,
            tools=herramientas.definiciones(),
            messages=mensajes,
            output_config={"effort": settings.CLAUDE_EFFORT},
            cache_control={"type": "ephemeral"},
            betas=[BETA_FALLBACK],
            fallbacks="default",
        )
        _registrar_uso(respuesta)

        if respuesta.stop_reason == "refusal":
            return RESPUESTA_RECHAZO

        contenido = _contenido_vigente(respuesta.content)
        usos = [b for b in contenido if b.type == "tool_use"]
        if respuesta.stop_reason == "tool_use" and usos:
            mensajes.append({"role": "assistant", "content": contenido})
            resultados = []
            for uso in usos:
                texto, es_error = herramientas.ejecutar(uso.name, uso.input)
                resultado = {"type": "tool_result", "tool_use_id": uso.id, "content": texto}
                if es_error:
                    resultado["is_error"] = True
                resultados.append(resultado)
            mensajes.append({"role": "user", "content": resultados})
            continue

        texto = "\n".join(b.text for b in contenido if b.type == "text").strip()
        return texto or "👍"
    return RESPUESTA_ENREDO


def _registrar_uso(respuesta):
    uso = getattr(respuesta, "usage", None)
    if uso is None:
        return
    logger.info(
        "Claude %s stop=%s entrada=%s cache_leido=%s salida=%s",
        getattr(respuesta, "model", "?"),
        respuesta.stop_reason,
        getattr(uso, "input_tokens", None),
        getattr(uso, "cache_read_input_tokens", None),
        getattr(uso, "output_tokens", None),
    )
