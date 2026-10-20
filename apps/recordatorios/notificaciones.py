"""Avisos entre personas (asignaciones, completados). Un fallo de envío nunca deshace la acción."""

import logging

from apps.whatsapp import envio

from .formato import fecha_legible

logger = logging.getLogger(__name__)


def _enviar(usuario, texto, ahora):
    try:
        envio.enviar(usuario, texto, ahora=ahora)
    except Exception:
        logger.exception("No se pudo avisar a %s", usuario)


def asignacion(recordatorio, ahora=None):
    cuando = fecha_legible(recordatorio.fecha_hora, recordatorio.dueno.tz, ahora)
    _enviar(
        recordatorio.dueno,
        f"📌 {recordatorio.creado_por.nombre_visible} te dejó un recordatorio para {cuando}: *{recordatorio.titulo}*",
        ahora,
    )


def completado(recordatorio, por, ahora=None):
    _enviar(recordatorio.creado_por, f"✅ {por.nombre_visible} completó: *{recordatorio.titulo}*", ahora)


def cancelado(recordatorio, por, destinatario, ahora=None):
    _enviar(destinatario, f"🚫 {por.nombre_visible} canceló: *{recordatorio.titulo}*", ahora)
