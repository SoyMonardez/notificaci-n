import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_q.tasks import async_task

from .firma import firma_valida
from .models import MensajeProcesado
from .parser import parsear_webhook

logger = logging.getLogger(__name__)

TAREA_PROCESAR = "apps.asistente.procesamiento.procesar_mensaje"


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook(request):
    if request.method == "GET":
        return _verificar_suscripcion(request)

    if not settings.WHATSAPP_APP_SECRET:
        if not settings.DEBUG:
            logger.error("Webhook rechazado: falta WHATSAPP_APP_SECRET")
            return HttpResponseForbidden()
        logger.warning("WHATSAPP_APP_SECRET vacío: se omite la verificación de firma (solo en DEBUG)")
    elif not firma_valida(
        request.body, request.headers.get("X-Hub-Signature-256", ""), settings.WHATSAPP_APP_SECRET
    ):
        logger.warning("Webhook con firma inválida")
        return HttpResponseForbidden()

    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()

    for mensaje in parsear_webhook(payload):
        _, nuevo = MensajeProcesado.objects.get_or_create(wa_message_id=mensaje.id)
        if nuevo:
            # Se responde 200 de inmediato; el worker hace el trabajo lento (IA, envíos).
            async_task(TAREA_PROCESAR, mensaje.a_dict())
    return HttpResponse("ok")


def _verificar_suscripcion(request):
    modo = request.GET.get("hub.mode")
    token = request.GET.get("hub.verify_token", "")
    desafio = request.GET.get("hub.challenge", "")
    esperado = settings.WHATSAPP_VERIFY_TOKEN
    if modo == "subscribe" and esperado and hmac.compare_digest(token, esperado):
        return HttpResponse(desafio)
    return HttpResponseForbidden()
