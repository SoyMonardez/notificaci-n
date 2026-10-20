from django.contrib import admin

from .models import MensajeConversacion


@admin.register(MensajeConversacion)
class MensajeConversacionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "rol", "texto", "creado_en")
    list_filter = ("rol", "usuario")
    search_fields = ("texto",)
