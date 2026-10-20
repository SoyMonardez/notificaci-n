from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Espacio, Membresia, Usuario


class MembresiaEnUsuario(admin.TabularInline):
    model = Membresia
    extra = 0


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "first_name", "whatsapp", "alias", "is_active")
    search_fields = ("username", "first_name", "last_name", "whatsapp", "alias")
    fieldsets = (
        *UserAdmin.fieldsets,
        (
            "WhatsApp y asistente",
            {"fields": ("whatsapp", "alias", "zona_horaria", "ultimo_mensaje_entrante")},
        ),
    )
    add_fieldsets = (
        *UserAdmin.add_fieldsets,
        ("WhatsApp y asistente", {"fields": ("first_name", "whatsapp", "alias", "zona_horaria")}),
    )
    readonly_fields = ("ultimo_mensaje_entrante",)
    inlines = [MembresiaEnUsuario]


class MembresiaEnEspacio(admin.TabularInline):
    model = Membresia
    extra = 1


@admin.register(Espacio)
class EspacioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "creado_en")
    inlines = [MembresiaEnEspacio]
