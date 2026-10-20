from datetime import timedelta

import pytest
from django.core.management import call_command

from apps.cuentas.models import Espacio, Membresia, Usuario
from apps.cuentas.servicios import buscar_companero, companeros, elegir_espacio, usuario_por_whatsapp


@pytest.mark.django_db
def test_usuario_por_whatsapp_normaliza_y_exige_activo(juan):
    assert usuario_por_whatsapp("+56 9 1111 1111") == juan
    assert usuario_por_whatsapp("56900000000") is None
    juan.is_active = False
    juan.save()
    assert usuario_por_whatsapp("56911111111") is None


@pytest.mark.django_db
def test_companeros_solo_de_espacios_compartidos(juan, papa, pedro):
    assert set(companeros(juan)) == {papa, pedro}
    assert list(companeros(papa)) == [juan]
    assert list(companeros(pedro)) == [juan]


@pytest.mark.django_db
def test_buscar_companero_por_alias_sin_tildes(juan, papa, pedro):
    assert buscar_companero(juan, "Papa") == papa
    assert buscar_companero(juan, "viejo") == papa
    assert buscar_companero(juan, "pedro") == pedro
    # Papá no comparte espacio con Pedro.
    assert buscar_companero(papa, "pedro") is None
    assert buscar_companero(juan, "") is None


@pytest.mark.django_db
def test_elegir_espacio(juan, papa, familia, negocio):
    assert elegir_espacio(juan, juan, "negocio") == negocio
    assert elegir_espacio(juan, juan, "familia") == familia
    assert elegir_espacio(juan, papa, "negocio") == familia  # solo comparten la familia
    assert elegir_espacio(papa, papa, None) == familia


@pytest.mark.django_db
def test_ventana_de_24_horas(juan, ahora):
    assert not juan.ventana_abierta(ahora)
    juan.ultimo_mensaje_entrante = ahora - timedelta(hours=23)
    assert juan.ventana_abierta(ahora)
    juan.ultimo_mensaje_entrante = ahora - timedelta(hours=24)
    assert not juan.ventana_abierta(ahora)


@pytest.mark.django_db
def test_comando_inicializar():
    Usuario.objects.create_superuser("yo", password="x")
    call_command("inicializar", "--usuario", "yo", "--whatsapp", "+56 9 4444 4444", "--nombre", "Juan")

    yo = Usuario.objects.get(username="yo")
    assert yo.whatsapp == "56944444444"
    assert yo.first_name == "Juan"
    assert set(Espacio.objects.values_list("tipo", flat=True)) == {"familia", "negocio"}
    assert Membresia.objects.filter(usuario=yo, rol=Membresia.Rol.DUENO).count() == 2

    # Se puede ejecutar de nuevo sin duplicar nada.
    call_command("inicializar", "--usuario", "yo", "--whatsapp", "56944444444")
    assert Espacio.objects.count() == 2
