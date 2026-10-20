from django.contrib import admin

from .models import MensajeProcesado


@admin.register(MensajeProcesado)
class MensajeProcesadoAdmin(admin.ModelAdmin):
    list_display = ("wa_message_id", "recibido_en")
    search_fields = ("wa_message_id",)
