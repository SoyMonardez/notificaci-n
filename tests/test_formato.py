from datetime import datetime

import pytest

from apps.recordatorios import servicios
from apps.recordatorios.formato import fecha_larga, fecha_legible, texto_aviso

from .conftest import SANTIAGO


def en(dia, hora=9, mes=10, anio=2026):
    return datetime(anio, mes, dia, hora, 0, tzinfo=SANTIAGO)


@pytest.mark.parametrize(
    ("fecha", "esperado"),
    [
        (en(21, 15), "hoy a las 15:00"),
        (en(22), "mañana jueves 22 a las 09:00"),
        (en(20), "ayer a las 09:00"),
        (en(24), "el sábado 24 a las 09:00"),
        (en(2, mes=11), "el lunes 2 de noviembre a las 09:00"),
        (en(5, mes=1, anio=2027), "el martes 5 de enero de 2027 a las 09:00"),
    ],
)
def test_fecha_legible(fecha, esperado, ahora):
    assert fecha_legible(fecha, SANTIAGO, ahora) == esperado


def test_fecha_larga(ahora):
    assert fecha_larga(ahora, SANTIAGO) == "miércoles 21 de octubre de 2026, 10:00"


@pytest.mark.django_db
def test_texto_aviso_de_recordatorio_asignado(juan, papa, ahora):
    recordatorio = servicios.crear(
        papa, titulo="Traer cemento", detalle="3 sacos", fecha_hora=en(22, 8), para=juan, ahora=ahora
    )
    assert texto_aviso(recordatorio, ahora) == "⏰ *Traer cemento*\n3 sacos\n_Te lo dejó Luis._"


@pytest.mark.django_db
def test_texto_aviso_de_evento_con_anticipacion(juan, ahora):
    recordatorio = servicios.crear(
        juan,
        titulo="Reunión con Acme",
        fecha_hora=en(21, 16),
        tipo="evento",
        avisar_antes_min=30,
        ahora=ahora,
    )
    assert texto_aviso(recordatorio, ahora) == "📅 *Reunión con Acme* (hoy a las 16:00)"
