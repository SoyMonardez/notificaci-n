import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.asistente.procesamiento import procesar_mensaje
from apps.whatsapp.parser import MensajeEntrante


class Command(BaseCommand):
    help = (
        "Simula un mensaje de WhatsApp entrante sin pasar por Meta. Con WHATSAPP_CLIENTE=ClienteConsola "
        "la respuesta se muestra en la terminal."
    )

    def add_arguments(self, parser):
        parser.add_argument("numero", help="Número del remitente, ej: 56912345678.")
        parser.add_argument("texto", nargs="?", default="", help="Texto del mensaje.")
        parser.add_argument("--boton", help="Simula tocar un botón con este payload, ej: rec:listo:3.")
        parser.add_argument("--reenviado", action="store_true", help="Marca el mensaje como reenviado.")

    def handle(self, *args, **opciones):
        if not opciones["texto"] and not opciones["boton"]:
            raise CommandError("Indica un texto o --boton.")
        if opciones["boton"]:
            mensaje = MensajeEntrante(
                id=f"sim-{uuid.uuid4()}",
                wa_id=opciones["numero"],
                tipo=MensajeEntrante.BOTON,
                payload=opciones["boton"],
            )
        else:
            mensaje = MensajeEntrante(
                id=f"sim-{uuid.uuid4()}",
                wa_id=opciones["numero"],
                tipo=MensajeEntrante.TEXTO,
                texto=opciones["texto"],
                reenviado=opciones["reenviado"],
            )
        procesar_mensaje(mensaje.a_dict())
