from django.core.management.base import BaseCommand

from apps.recordatorios.tareas import enviar_vencidos


class Command(BaseCommand):
    help = "Envía una vez los avisos que ya tocan (lo mismo que hace el worker cada minuto)."

    def handle(self, *args, **opciones):
        enviados = enviar_vencidos()
        self.stdout.write(f"Avisos enviados: {enviados}")
