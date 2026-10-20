"""Envío de mensajes a un usuario respetando la ventana de 24 h de WhatsApp.

Dentro de la ventana se manda un mensaje libre (con botones si corresponde).
Fuera de ella Meta solo acepta plantillas aprobadas (el README explica cómo crearlas):
- WHATSAPP_PLANTILLA_RECORDATORIO: una variable {{1}} y 3 botones de respuesta rápida
  en este orden: Listo, +1 hora, Mañana.
- WHATSAPP_PLANTILLA_AVISO: una variable {{1}}, sin botones.
"""

from django.conf import settings

from .cliente import obtener_cliente


def enviar(usuario, texto, botones=(), ahora=None):
    if not usuario.whatsapp:
        return
    cliente = obtener_cliente()
    if usuario.ventana_abierta(ahora):
        if botones:
            cliente.enviar_botones(usuario.whatsapp, texto, list(botones))
        else:
            cliente.enviar_texto(usuario.whatsapp, texto)
    elif botones:
        cliente.enviar_plantilla(
            usuario.whatsapp,
            settings.WHATSAPP_PLANTILLA_RECORDATORIO,
            [texto],
            payloads_botones=[b.id for b in botones],
        )
    else:
        cliente.enviar_plantilla(usuario.whatsapp, settings.WHATSAPP_PLANTILLA_AVISO, [texto])
