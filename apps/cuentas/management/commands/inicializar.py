from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cuentas.models import Espacio, Membresia, Usuario, validar_whatsapp
from apps.cuentas.servicios import normalizar_numero


class Command(BaseCommand):
    help = "Crea los espacios Familia y Negocio y deja a un usuario existente como dueño de ambos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--usuario", required=True, help="Nombre de usuario (creado con createsuperuser)."
        )
        parser.add_argument("--whatsapp", required=True, help="Número con código de país, ej: 56912345678.")
        parser.add_argument("--nombre", help="Nombre con el que te saluda el bot.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        try:
            usuario = Usuario.objects.get(username=opciones["usuario"])
        except Usuario.DoesNotExist as exc:
            raise CommandError(
                f"No existe el usuario «{opciones['usuario']}». Créalo con createsuperuser."
            ) from exc

        numero = normalizar_numero(opciones["whatsapp"])
        try:
            validar_whatsapp(numero)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        usuario.whatsapp = numero
        if opciones.get("nombre"):
            usuario.first_name = opciones["nombre"]
        usuario.save()

        for nombre, tipo in (
            ("Familia", Espacio.Tipo.FAMILIA),
            (settings.NOMBRE_NEGOCIO, Espacio.Tipo.NEGOCIO),
        ):
            espacio, creado = Espacio.objects.get_or_create(tipo=tipo, defaults={"nombre": nombre})
            Membresia.objects.update_or_create(
                usuario=usuario, espacio=espacio, defaults={"rol": Membresia.Rol.DUENO}
            )
            estado = "creado" if creado else "ya existía"
            self.stdout.write(f"Espacio «{espacio.nombre}» {estado}; {usuario} es dueño.")

        self.stdout.write(
            self.style.SUCCESS("Listo. Agrega a tu papá y a tu empleado desde el admin (Espacios).")
        )
