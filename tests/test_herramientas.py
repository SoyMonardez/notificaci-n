import json
from datetime import timedelta

import pytest

from apps.asistente.herramientas import DEFINICIONES, Herramientas
from apps.recordatorios import servicios
from apps.recordatorios.models import Recordatorio


def test_definiciones_cumplen_modo_estricto():
    for definicion in DEFINICIONES:
        esquema = definicion["input_schema"]
        assert definicion["strict"] is True
        assert esquema["additionalProperties"] is False
        assert set(esquema["required"]) <= set(esquema["properties"])


def test_no_se_pasa_el_limite_de_parametros_opcionales():
    # La API admite como máximo 24 parámetros opcionales sumando todas las herramientas strict.
    opcionales = sum(
        len(set(d["input_schema"]["properties"]) - set(d["input_schema"]["required"])) for d in DEFINICIONES
    )
    assert opcionales <= 24
    assert len(DEFINICIONES) <= 20


@pytest.mark.django_db
def test_crear_con_fecha_sin_zona_usa_la_del_usuario(juan, ahora):
    herramientas = Herramientas(juan, ahora)
    texto, es_error = herramientas.ejecutar(
        "crear_recordatorio", {"titulo": "Llamar a Pedro", "fecha_hora": "2026-10-22T09:00:00"}
    )
    assert not es_error
    resultado = json.loads(texto)
    assert resultado["ok"] is True
    assert resultado["cuando"] == "mañana jueves 22 a las 09:00"
    assert herramientas.hubo_cambios
    assert Recordatorio.objects.get(pk=resultado["id"]).fecha_hora.utcoffset() is not None


@pytest.mark.django_db
def test_crear_para_otra_persona_por_alias(juan, papa, ahora):
    texto, es_error = Herramientas(juan, ahora).ejecutar(
        "crear_recordatorio",
        {"titulo": "Comprar clavos", "fecha_hora": "2026-10-21T18:00:00-03:00", "para": "viejo"},
    )
    assert not es_error
    assert json.loads(texto)["para"] == "Luis"


@pytest.mark.django_db
def test_para_uno_mismo_no_asigna(juan, ahora):
    texto, es_error = Herramientas(juan, ahora).ejecutar(
        "crear_recordatorio", {"titulo": "Algo", "fecha_hora": "2026-10-21T18:00:00-03:00", "para": "yo"}
    )
    assert not es_error
    assert "para" not in json.loads(texto)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("nombre", "entrada", "mensaje"),
    [
        ("crear_recordatorio", {"titulo": "Algo", "fecha_hora": "mañana"}, "No entendí la fecha"),
        ("crear_recordatorio", {"titulo": "Algo", "fecha_hora": "2026-10-20T09:00:00-03:00"}, "ya pasó"),
        (
            "crear_recordatorio",
            {"titulo": "Algo", "fecha_hora": "2026-10-22T09:00:00-03:00", "para": "Marta"},
            "No encontré a «Marta»",
        ),
        ("completar_recordatorio", {"recordatorio_id": 999}, "No encontré el recordatorio #999"),
        ("completar_recordatorio", {"id": 1}, "Parámetros inválidos"),
        ("borrar_todo", {}, "Herramienta desconocida"),
    ],
)
def test_errores_se_devuelven_a_la_ia(juan, ahora, nombre, entrada, mensaje):
    texto, es_error = Herramientas(juan, ahora).ejecutar(nombre, entrada)
    assert es_error
    assert mensaje in texto


@pytest.mark.django_db
def test_listar_posponer_y_completar(juan, papa, ahora):
    recordatorio = servicios.crear(
        papa, titulo="Traer cemento", fecha_hora=ahora + timedelta(hours=1), para=juan, ahora=ahora
    )
    herramientas = Herramientas(juan, ahora)

    listado = json.loads(herramientas.ejecutar("listar_recordatorios", {})[0])
    assert listado["total"] == 1
    assert listado["recordatorios"][0]["te_lo_dejo"] == "Luis"

    pospuesto = json.loads(
        herramientas.ejecutar("posponer_recordatorio", {"recordatorio_id": recordatorio.id, "minutos": 30})[0]
    )
    assert pospuesto["cuando"] == "hoy a las 11:30"

    completado = json.loads(
        herramientas.ejecutar("completar_recordatorio", {"recordatorio_id": recordatorio.id})[0]
    )
    assert completado["estado"] == "Completado"
