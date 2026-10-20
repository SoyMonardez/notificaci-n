"""Procesa cada mensaje entrante de WhatsApp (se ejecuta en el worker)."""

import logging

from django.utils import timezone

from apps.cuentas.models import Usuario
from apps.cuentas.servicios import usuario_por_whatsapp
from apps.recordatorios import botones
from apps.whatsapp import envio
from apps.whatsapp.parser import MensajeEntrante

from . import agente

logger = logging.getLogger(__name__)

RESPUESTA_AUDIO = (
    "🎙️ Todavía no entiendo audios (llegan en la próxima versión). Por ahora escríbemelo, por favor."
)
RESPUESTA_OTRO = "Por ahora solo entiendo mensajes de texto 🙂"


def procesar_mensaje(datos):
    mensaje = MensajeEntrante.desde_dict(datos)
    usuario = usuario_por_whatsapp(mensaje.wa_id)
    if usuario is None:
        # No se responde: evita costos y no confirma a desconocidos que el número es un bot.
        logger.warning(
            "Mensaje de un número no autorizado: %s (%s). Si es alguien conocido, agrégalo en el admin.",
            mensaje.wa_id,
            mensaje.nombre_perfil,
        )
        return

    ahora = timezone.now()
    Usuario.objects.filter(pk=usuario.pk).update(ultimo_mensaje_entrante=ahora)
    usuario.ultimo_mensaje_entrante = ahora

    try:
        respuesta = responder_a(usuario, mensaje, ahora)
    except Exception:
        # Ej: falta ANTHROPIC_API_KEY o un error no previsto. La persona igual recibe respuesta.
        logger.exception("Error al procesar el mensaje %s", mensaje.id)
        respuesta = agente.RESPUESTA_ERROR
    if respuesta:
        envio.enviar(usuario, respuesta, ahora=ahora)


def responder_a(usuario, mensaje, ahora):
    if mensaje.tipo == MensajeEntrante.BOTON:
        return botones.manejar(usuario, mensaje.payload, ahora)
    if mensaje.tipo == MensajeEntrante.TEXTO:
        texto = mensaje.texto.strip()
        if not texto:
            return None
        if mensaje.reenviado:
            texto = f"[Reenviado]\n{texto}"
        return agente.responder(usuario, texto, ahora=ahora)
    if mensaje.tipo == MensajeEntrante.AUDIO:
        return RESPUESTA_AUDIO
    return RESPUESTA_OTRO
