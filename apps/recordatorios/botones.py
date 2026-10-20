"""Botones de los avisos. Se resuelven directamente, sin pasar por la IA.

El payload tiene la forma "rec:<accion>:<id>". El orden de los botones debe coincidir con el de la
plantilla de WhatsApp (Listo, +1 hora, Mañana).
"""

from django.utils import timezone

from apps.whatsapp.cliente import Boton

from . import servicios
from .formato import fecha_legible
from .servicios import ErrorRecordatorio

LISTO = "listo"
UNA_HORA = "1h"
MANANA = "manana"


def botones_para(recordatorio):
    return [
        Boton(f"rec:{LISTO}:{recordatorio.id}", "✅ Listo"),
        Boton(f"rec:{UNA_HORA}:{recordatorio.id}", "⏰ +1 hora"),
        Boton(f"rec:{MANANA}:{recordatorio.id}", "📅 Mañana"),
    ]


def manejar(usuario, payload, ahora=None):
    """Aplica la acción del botón y devuelve el texto de respuesta."""
    ahora = ahora or timezone.now()
    partes = (payload or "").split(":")
    if len(partes) != 3 or partes[0] != "rec" or not partes[2].isdigit():
        return "No entendí ese botón. Dime qué quieres hacer con el recordatorio."
    accion, recordatorio_id = partes[1], int(partes[2])

    try:
        recordatorio = servicios.obtener(usuario, recordatorio_id)
        if accion == LISTO:
            servicios.completar(recordatorio, usuario, ahora)
            return f"✅ Listo: *{recordatorio.titulo}*"
        if accion == UNA_HORA:
            servicios.posponer(recordatorio, minutos=60, ahora=ahora)
        elif accion == MANANA:
            servicios.posponer(
                recordatorio,
                nueva_fecha=servicios.mismo_horario_dia_siguiente(recordatorio, ahora),
                ahora=ahora,
            )
        else:
            return "No entendí ese botón. Dime qué quieres hacer con el recordatorio."
    except ErrorRecordatorio as error:
        return str(error)

    cuando = fecha_legible(recordatorio.fecha_hora, usuario.tz, ahora)
    return f"⏰ Te lo recuerdo {cuando}: *{recordatorio.titulo}*"
