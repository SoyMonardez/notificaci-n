import hashlib
import hmac
import json

import pytest

from apps.whatsapp import views
from apps.whatsapp.firma import firma_valida

URL = "/whatsapp/webhook/"
SECRETO = "secreto-de-prueba"


def firmar(cuerpo):
    return "sha256=" + hmac.new(SECRETO.encode(), cuerpo, hashlib.sha256).hexdigest()


def payload_texto(id_mensaje="wamid.1"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "56911111111",
                                    "id": id_mensaje,
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


@pytest.fixture
def encolados(monkeypatch):
    llamadas = []
    monkeypatch.setattr(views, "async_task", lambda funcion, datos: llamadas.append((funcion, datos)))
    return llamadas


def publicar(client, payload, firma=None):
    cuerpo = json.dumps(payload).encode()
    cabeceras = {"HTTP_X_HUB_SIGNATURE_256": firma if firma is not None else firmar(cuerpo)}
    return client.post(URL, data=cuerpo, content_type="application/json", **cabeceras)


def test_firma():
    cuerpo = b'{"a": 1}'
    assert firma_valida(cuerpo, firmar(cuerpo), SECRETO)
    assert not firma_valida(cuerpo, firmar(b"otro"), SECRETO)
    assert not firma_valida(cuerpo, "", SECRETO)
    assert not firma_valida(cuerpo, firmar(cuerpo), "")


def test_verificacion_de_suscripcion(client):
    ok = client.get(
        URL, {"hub.mode": "subscribe", "hub.verify_token": "token-de-verificacion", "hub.challenge": "42"}
    )
    assert ok.status_code == 200
    assert ok.content == b"42"

    mal = client.get(URL, {"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "42"})
    assert mal.status_code == 403


@pytest.mark.django_db
def test_firma_invalida_se_rechaza(client, encolados):
    respuesta = publicar(client, payload_texto(), firma="sha256=falsa")
    assert respuesta.status_code == 403
    assert encolados == []


@pytest.mark.django_db
def test_mensaje_valido_se_encola_una_sola_vez(client, encolados):
    assert publicar(client, payload_texto()).status_code == 200
    assert publicar(client, payload_texto()).status_code == 200  # Meta reintenta el mismo mensaje

    assert len(encolados) == 1
    funcion, datos = encolados[0]
    assert funcion == "apps.asistente.procesamiento.procesar_mensaje"
    assert datos["id"] == "wamid.1"
    assert datos["texto"] == "hola"


@pytest.mark.django_db
def test_json_invalido(client, encolados):
    cuerpo = b"no es json"
    respuesta = client.post(
        URL, data=cuerpo, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=firmar(cuerpo)
    )
    assert respuesta.status_code == 400


@pytest.mark.django_db
def test_sin_secreto_en_produccion_se_rechaza(client, encolados, settings):
    settings.WHATSAPP_APP_SECRET = ""
    settings.DEBUG = False
    assert publicar(client, payload_texto()).status_code == 403
    assert encolados == []
