"""Tareas que ejecuta el worker de Django-Q2."""

import logging

from django.db.models import F
from django.utils import timezone

from apps.whatsapp import envio

from . import botones, formato, servicios
from .models import Recordatorio

logger = logging.getLogger(__name__)

MAX_INTENTOS = 5
MAX_POR_PASADA = 200


def enviar_vencidos(ahora=None):
    """Envía los avisos que ya tocan. Programada cada minuto (ver migración 0002)."""
    ahora = ahora or timezone.now()
    enviados = 0
    for recordatorio in servicios.pendientes_de_aviso(ahora)[:MAX_POR_PASADA]:
        # Se marca como enviado antes de enviar: si otro proceso ya lo tomó, update() devuelve 0
        # y no se manda dos veces.
        tomado = Recordatorio.objects.filter(
            pk=recordatorio.pk, estado=Recordatorio.Estado.PENDIENTE, avisar_en=recordatorio.avisar_en
        ).update(
            estado=Recordatorio.Estado.ENVIADO, aviso_enviado_en=ahora, intentos_envio=F("intentos_envio") + 1
        )
        if not tomado:
            continue
        recordatorio.refresh_from_db()
        try:
            envio.enviar(
                recordatorio.dueno,
                formato.texto_aviso(recordatorio, ahora),
                botones.botones_para(recordatorio),
                ahora=ahora,
            )
            enviados += 1
        except Exception:
            logger.exception("Falló el aviso del recordatorio #%s", recordatorio.pk)
            estado = (
                Recordatorio.Estado.FALLIDO
                if recordatorio.intentos_envio >= MAX_INTENTOS
                else Recordatorio.Estado.PENDIENTE
            )
            Recordatorio.objects.filter(pk=recordatorio.pk).update(estado=estado, aviso_enviado_en=None)
    return enviados
