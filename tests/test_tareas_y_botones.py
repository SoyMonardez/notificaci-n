from datetime import timedelta

import pytest

from apps.recordatorios import botones, servicios, tareas
from apps.recordatorios.models import Recordatorio

pytestmark = pytest.mark.django_db


def test_envia_solo_los_vencidos_y_una_sola_vez(juan, ahora, enviados):
    vencido = servicios.crear(juan, titulo="Ya toca", fecha_hora=ahora, ahora=ahora)
    servicios.crear(juan, titulo="Más tarde", fecha_hora=ahora + timedelta(hours=1), ahora=ahora)

    assert tareas.enviar_vencidos(ahora) == 1
    assert tareas.enviar_vencidos(ahora) == 0

    vencido.refresh_from_db()
    assert vencido.estado == Recordatorio.Estado.ENVIADO
    assert vencido.aviso_enviado_en == ahora
    assert len(enviados) == 1


def test_fuera_de_la_ventana_usa_plantilla_con_botones(juan, ahora, enviados):
    recordatorio = servicios.crear(juan, titulo="Pagar luz", fecha_hora=ahora, ahora=ahora)
    tareas.enviar_vencidos(ahora)

    [aviso] = enviados
    assert aviso["tipo"] == "plantilla"
    assert aviso["nombre"] == "recordatorio"
    assert aviso["parametros"] == ["⏰ *Pagar luz*"]
    assert aviso["payloads"] == [
        f"rec:listo:{recordatorio.id}",
        f"rec:1h:{recordatorio.id}",
        f"rec:manana:{recordatorio.id}",
    ]


def test_dentro_de_la_ventana_usa_botones_interactivos(juan, ahora, enviados):
    juan.ultimo_mensaje_entrante = ahora - timedelta(hours=2)
    juan.save()
    servicios.crear(juan, titulo="Pagar luz", fecha_hora=ahora, ahora=ahora)
    tareas.enviar_vencidos(ahora)

    [aviso] = enviados
    assert aviso["tipo"] == "botones"
    assert [b.titulo for b in aviso["botones"]] == ["✅ Listo", "⏰ +1 hora", "📅 Mañana"]


def test_evento_avisa_con_anticipacion(juan, ahora, enviados):
    servicios.crear(
        juan,
        titulo="Reunión",
        fecha_hora=ahora + timedelta(minutes=30),
        tipo="evento",
        avisar_antes_min=30,
        ahora=ahora,
    )
    assert tareas.enviar_vencidos(ahora - timedelta(minutes=1)) == 0
    assert tareas.enviar_vencidos(ahora) == 1


def test_si_falla_el_envio_reintenta_y_luego_se_rinde(juan, ahora, monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError("WhatsApp caído")

    monkeypatch.setattr(tareas.envio, "enviar", falla)
    recordatorio = servicios.crear(juan, titulo="Algo", fecha_hora=ahora, ahora=ahora)

    tareas.enviar_vencidos(ahora)
    recordatorio.refresh_from_db()
    assert recordatorio.estado == Recordatorio.Estado.PENDIENTE
    assert recordatorio.intentos_envio == 1

    for _ in range(tareas.MAX_INTENTOS - 1):
        tareas.enviar_vencidos(ahora)
    recordatorio.refresh_from_db()
    assert recordatorio.estado == Recordatorio.Estado.FALLIDO


def test_boton_listo(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Pagar luz", fecha_hora=ahora, ahora=ahora)
    assert botones.manejar(juan, f"rec:listo:{recordatorio.id}", ahora) == "✅ Listo: *Pagar luz*"
    recordatorio.refresh_from_db()
    assert recordatorio.estado == Recordatorio.Estado.COMPLETADO


def test_boton_una_hora_despues_del_aviso(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Pagar luz", fecha_hora=ahora, ahora=ahora)
    tareas.enviar_vencidos(ahora)
    despues = ahora + timedelta(minutes=5)

    respuesta = botones.manejar(juan, f"rec:1h:{recordatorio.id}", despues)
    recordatorio.refresh_from_db()
    assert recordatorio.fecha_hora == despues + timedelta(hours=1)
    assert recordatorio.estado == Recordatorio.Estado.PENDIENTE
    assert respuesta == "⏰ Te lo recuerdo hoy a las 11:05: *Pagar luz*"


def test_boton_manana(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Pagar luz", fecha_hora=ahora, ahora=ahora)
    respuesta = botones.manejar(juan, f"rec:manana:{recordatorio.id}", ahora)
    recordatorio.refresh_from_db()
    assert recordatorio.fecha_hora == ahora + timedelta(days=1)
    assert "mañana jueves 22 a las 10:00" in respuesta


@pytest.mark.parametrize("payload", ["", "Listo", "rec:listo", "rec:listo:x", "otro:listo:1", "rec:volar:1"])
def test_botones_invalidos(juan, ahora, payload):
    servicios.crear(juan, titulo="Algo", fecha_hora=ahora, ahora=ahora)
    assert "No entendí" in botones.manejar(juan, payload, ahora)


def test_boton_de_recordatorio_ajeno(juan, papa, ahora):
    recordatorio = servicios.crear(juan, titulo="Privado", fecha_hora=ahora, ahora=ahora)
    assert botones.manejar(papa, f"rec:listo:{recordatorio.id}", ahora).startswith("No encontré")


def test_cambiar_la_hora_en_el_admin_reactiva_el_aviso(juan, ahora, admin_client):
    recordatorio = servicios.crear(juan, titulo="Algo", fecha_hora=ahora, ahora=ahora)
    tareas.enviar_vencidos(ahora)
    recordatorio.refresh_from_db()
    assert recordatorio.estado == Recordatorio.Estado.ENVIADO

    nueva = (ahora + timedelta(days=1)).astimezone(juan.tz)
    respuesta = admin_client.post(
        f"/admin/recordatorios/recordatorio/{recordatorio.id}/change/",
        {
            "espacio": recordatorio.espacio_id,
            "dueno": juan.id,
            "creado_por": juan.id,
            "titulo": "Algo",
            "detalle": "",
            "tipo": "recordatorio",
            "fecha_hora_0": nueva.strftime("%d/%m/%Y"),
            "fecha_hora_1": nueva.strftime("%H:%M:%S"),
            "avisar_antes_min": 0,
            "estado": Recordatorio.Estado.ENVIADO,
            "etiqueta": "",
        },
    )
    assert respuesta.status_code == 302, respuesta.content.decode()[:2000]
    recordatorio.refresh_from_db()
    assert recordatorio.estado == Recordatorio.Estado.PENDIENTE
    assert recordatorio.avisar_en == nueva
