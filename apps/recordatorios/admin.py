from django.contrib import admin

from .models import Recordatorio


@admin.register(Recordatorio)
class RecordatorioAdmin(admin.ModelAdmin):
    list_display = ("titulo", "dueno", "creado_por", "fecha_hora", "estado", "etiqueta", "espacio")
    list_filter = ("estado", "tipo", "espacio")
    search_fields = ("titulo", "detalle", "etiqueta")
    date_hierarchy = "fecha_hora"
    readonly_fields = ("avisar_en", "aviso_enviado_en", "completado_en", "veces_pospuesto", "intentos_envio")
    autocomplete_fields = ("dueno", "creado_por")

    def save_model(self, request, obj, form, change):
        # Si se cambia la hora de uno que ya avisó (o falló), vuelve a quedar pendiente de aviso.
        cambio_hora = {"fecha_hora", "avisar_antes_min"} & set(form.changed_data)
        if (
            change
            and cambio_hora
            and obj.estado in {Recordatorio.Estado.ENVIADO, Recordatorio.Estado.FALLIDO}
        ):
            obj.estado = Recordatorio.Estado.PENDIENTE
            obj.aviso_enviado_en = None
            obj.intentos_envio = 0
        super().save_model(request, obj, form, change)
