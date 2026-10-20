from datetime import timedelta

import pytest

from apps.asistente import procesamiento
from apps.cuentas.models import Usuario
from apps.recordatorios import servicios
from apps.recordatorios.models import Recordatorio
from apps.whatsapp.parser import MensajeEntrante

pytestmark = pytest.mark.django_db


def mensaje(numero, **campos):
    datos = {"id": "wamid.x", "wa_id": numero, "tipo": MensajeEntrante.TEXTO, **campos}
    return MensajeEntrante(**datos).a_dict()


@pytest.fixture
def respuestas_ia(monkeypatch):
    recibidos = []

    def responder(usuario, texto, ahora=None):
        recibidos.append(texto)
        return f"IA: {texto}"

    monkeypatch.setattr(procesamiento.agente, "responder", responder)
    return recibidos


def test_numero_desconocido_no_recibe_respuesta(enviados, respuestas_ia, caplog):
    procesamiento.procesar_mensaje(mensaje("56900000000", texto="hola"))
    assert enviados == []
    assert respuestas_ia == []
    assert "no autorizado: 56900000000" in caplog.text


def test_texto_pasa_por_la_ia_y_abre_la_ventana(juan, enviados, respuestas_ia):
    procesamiento.procesar_mensaje(mensaje(juan.whatsapp, texto="  recuérdame algo  "))

    assert respuestas_ia == ["recuérdame algo"]
    assert enviados == [{"tipo": "texto", "destino": juan.whatsapp, "texto": "IA: recuérdame algo"}]
    assert Usuario.objects.get(pk=juan.pk).ultimo_mensaje_entrante is not None


def test_reenviado_se_marca_para_la_ia(juan, respuestas_ia):
    procesamiento.procesar_mensaje(mensaje(juan.whatsapp, texto="cambiar el logo", reenviado=True))
    assert respuestas_ia == ["[Reenviado]\ncambiar el logo"]


def test_boton_no_pasa_por_la_ia(juan, enviados, respuestas_ia):
    recordatorio = servicios.crear(juan, titulo="Pagar luz", fecha_hora=juan.date_joined + timedelta(days=1))
    procesamiento.procesar_mensaje(
        mensaje(juan.whatsapp, tipo=MensajeEntrante.BOTON, payload=f"rec:listo:{recordatorio.id}")
    )
    assert respuestas_ia == []
    assert enviados[0]["texto"] == "✅ Listo: *Pagar luz*"
    recordatorio.refresh_from_db()
    assert recordatorio.estado == Recordatorio.Estado.COMPLETADO


def test_audio_y_otros_tipos(juan, enviados, respuestas_ia):
    procesamiento.procesar_mensaje(mensaje(juan.whatsapp, tipo=MensajeEntrante.AUDIO, media_id="m1"))
    procesamiento.procesar_mensaje(mensaje(juan.whatsapp, tipo=MensajeEntrante.OTRO))
    assert [e["texto"] for e in enviados] == [procesamiento.RESPUESTA_AUDIO, procesamiento.RESPUESTA_OTRO]
    assert respuestas_ia == []


def test_error_inesperado_igual_responde(juan, enviados, monkeypatch, caplog):
    def falla(*args, **kwargs):
        raise TypeError("Could not resolve authentication method")

    monkeypatch.setattr(procesamiento.agente, "responder", falla)
    procesamiento.procesar_mensaje(mensaje(juan.whatsapp, texto="hola"))
    assert [e["texto"] for e in enviados] == [procesamiento.agente.RESPUESTA_ERROR]
    assert "Could not resolve authentication method" in caplog.text


def test_texto_vacio_no_responde(juan, enviados, respuestas_ia):
    procesamiento.procesar_mensaje(mensaje(juan.whatsapp, texto="   "))
    assert enviados == []
