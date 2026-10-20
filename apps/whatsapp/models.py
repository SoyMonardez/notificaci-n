from django.db import models


class MensajeProcesado(models.Model):
    """Meta puede entregar el mismo mensaje más de una vez; se registra su id para procesarlo una sola vez."""

    wa_message_id = models.CharField(max_length=128, unique=True)
    recibido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mensaje procesado"
        verbose_name_plural = "mensajes procesados"

    def __str__(self):
        return self.wa_message_id
