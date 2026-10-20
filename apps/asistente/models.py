from django.conf import settings
from django.db import models
from django.utils import timezone


class MensajeConversacion(models.Model):
    """Historial en texto plano que se le da a la IA como contexto de la conversación."""

    class Rol(models.TextChoices):
        USUARIO = "user", "Usuario"
        ASISTENTE = "assistant", "Asistente"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversacion"
    )
    rol = models.CharField(max_length=10, choices=Rol.choices)
    texto = models.TextField()
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "mensaje de conversación"
        verbose_name_plural = "conversación"
        ordering = ["creado_en", "id"]

    def __str__(self):
        return f"{self.usuario} ({self.rol}): {self.texto[:50]}"
