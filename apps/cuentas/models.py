from datetime import timedelta
from zoneinfo import ZoneInfo, available_timezones

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# Meta solo permite mensajes libres dentro de las 24 h siguientes al último mensaje del usuario.
# Se deja un margen para no enviar justo en el límite.
VENTANA_SERVICIO = timedelta(hours=24) - timedelta(minutes=10)


def zona_horaria_defecto():
    return settings.TIME_ZONE


def validar_zona_horaria(valor):
    if valor not in available_timezones():
        raise ValidationError(f"«{valor}» no es una zona horaria válida (ej: America/Santiago).")


def validar_whatsapp(valor):
    if not valor.isdigit() or not 8 <= len(valor) <= 15:
        raise ValidationError("Usa solo dígitos con código de país, sin + ni espacios (ej: 56912345678).")


class Usuario(AbstractUser):
    whatsapp = models.CharField(
        "WhatsApp",
        max_length=15,
        unique=True,
        null=True,
        blank=True,
        validators=[validar_whatsapp],
        help_text="Número tal como lo entrega WhatsApp: código de país + número, solo dígitos.",
    )
    alias = models.CharField(
        max_length=200,
        blank=True,
        help_text="Cómo lo nombran los demás al hablar con el bot, separado por comas (ej: papá, viejo).",
    )
    zona_horaria = models.CharField(
        max_length=64, default=zona_horaria_defecto, validators=[validar_zona_horaria]
    )
    ultimo_mensaje_entrante = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.nombre_visible

    @property
    def nombre_visible(self):
        return self.first_name or self.username

    @property
    def tz(self):
        return ZoneInfo(self.zona_horaria)

    def lista_alias(self):
        return [a.strip().lower() for a in self.alias.split(",") if a.strip()]

    def ventana_abierta(self, ahora=None):
        if self.ultimo_mensaje_entrante is None:
            return False
        ahora = ahora or timezone.now()
        return ahora - self.ultimo_mensaje_entrante < VENTANA_SERVICIO


class Espacio(models.Model):
    """Agrupa personas y datos: la familia por un lado, el negocio por otro."""

    class Tipo(models.TextChoices):
        FAMILIA = "familia", "Familia"
        NEGOCIO = "negocio", "Negocio"

    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    creado_en = models.DateTimeField(auto_now_add=True)
    miembros = models.ManyToManyField(Usuario, through="Membresia", related_name="espacios")

    class Meta:
        verbose_name = "espacio"
        verbose_name_plural = "espacios"

    def __str__(self):
        return self.nombre


class Membresia(models.Model):
    class Rol(models.TextChoices):
        DUENO = "dueno", "Dueño"
        EMPLEADO = "empleado", "Empleado"
        FAMILIAR = "familiar", "Familiar"

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="membresias")
    espacio = models.ForeignKey(Espacio, on_delete=models.CASCADE, related_name="membresias")
    rol = models.CharField(max_length=10, choices=Rol.choices)

    class Meta:
        verbose_name = "membresía"
        verbose_name_plural = "membresías"
        constraints = [
            models.UniqueConstraint(fields=["usuario", "espacio"], name="membresia_unica"),
        ]

    def __str__(self):
        return f"{self.usuario} en {self.espacio} ({self.get_rol_display()})"
