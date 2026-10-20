from datetime import timedelta

from django.conf import settings
from django.db import models


class Recordatorio(models.Model):
    class Tipo(models.TextChoices):
        RECORDATORIO = "recordatorio", "Recordatorio"
        EVENTO = "evento", "Evento"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADO = "enviado", "Aviso enviado"
        COMPLETADO = "completado", "Completado"
        CANCELADO = "cancelado", "Cancelado"
        FALLIDO = "fallido", "No se pudo enviar"

    espacio = models.ForeignKey("cuentas.Espacio", on_delete=models.CASCADE, related_name="recordatorios")
    dueno = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recordatorios",
        verbose_name="para",
        help_text="Quién recibe el aviso.",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recordatorios_creados"
    )
    titulo = models.CharField(max_length=200)
    detalle = models.TextField(blank=True)
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.RECORDATORIO)
    fecha_hora = models.DateTimeField()
    avisar_antes_min = models.PositiveIntegerField(
        "avisar antes (min)", default=0, help_text="Para eventos: cuántos minutos antes avisar."
    )
    avisar_en = models.DateTimeField(editable=False, db_index=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    etiqueta = models.CharField(max_length=100, blank=True, help_text="Ej: nombre del cliente o proyecto.")
    veces_pospuesto = models.PositiveIntegerField(default=0, editable=False)
    intentos_envio = models.PositiveSmallIntegerField(default=0, editable=False)
    aviso_enviado_en = models.DateTimeField(null=True, blank=True, editable=False)
    completado_en = models.DateTimeField(null=True, blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "recordatorio"
        verbose_name_plural = "recordatorios"
        ordering = ["fecha_hora"]
        indexes = [models.Index(fields=["estado", "avisar_en"])]

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        self.avisar_en = self.fecha_hora - timedelta(minutes=self.avisar_antes_min)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and (
            "fecha_hora" in update_fields or "avisar_antes_min" in update_fields
        ):
            kwargs["update_fields"] = {*update_fields, "avisar_en"}
        super().save(*args, **kwargs)

    @property
    def es_asignado(self):
        return self.creado_por_id != self.dueno_id

    @property
    def activo(self):
        return self.estado in {self.Estado.PENDIENTE, self.Estado.ENVIADO}
