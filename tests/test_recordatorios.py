from datetime import UTC, datetime, timedelta

import pytest

from apps.recordatorios import servicios
from apps.recordatorios.models import Recordatorio
from apps.recordatorios.servicios import ErrorRecordatorio

from .conftest import SANTIAGO

pytestmark = pytest.mark.django_db


def test_crear_elige_espacio_y_calcula_aviso(juan, negocio, ahora):
    recordatorio = servicios.crear(
        juan,
        titulo="  Llamar a Pedro  ",
        fecha_hora=ahora + timedelta(hours=2),
        ambito="negocio",
        etiqueta="Acme",
        ahora=ahora,
    )
    assert recordatorio.titulo == "Llamar a Pedro"
    assert recordatorio.espacio == negocio
    assert recordatorio.dueno == juan == recordatorio.creado_por
    assert recordatorio.avisar_en == recordatorio.fecha_hora
    assert recordatorio.estado == Recordatorio.Estado.PENDIENTE


def test_crear_rechaza_fechas_pasadas_y_titulo_vacio(juan, ahora):
    with pytest.raises(ErrorRecordatorio, match="ya pasó"):
        servicios.crear(juan, titulo="Algo", fecha_hora=ahora - timedelta(hours=1), ahora=ahora)
    with pytest.raises(ErrorRecordatorio, match="título"):
        servicios.crear(juan, titulo="  ", fecha_hora=ahora + timedelta(hours=1), ahora=ahora)
    with pytest.raises(ErrorRecordatorio, match="zona horaria"):
        servicios.crear(juan, titulo="Algo", fecha_hora=datetime(2026, 10, 22, 9), ahora=ahora)


def test_crear_acepta_ahora_mismo(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Ya", fecha_hora=ahora - timedelta(minutes=1), ahora=ahora)
    assert recordatorio.pk


def test_usuario_sin_espacio_no_puede_crear(ahora, db):
    from apps.cuentas.models import Usuario

    solo = Usuario.objects.create_user("solo", whatsapp="56955555555")
    with pytest.raises(ErrorRecordatorio, match="espacio"):
        servicios.crear(solo, titulo="Algo", fecha_hora=ahora + timedelta(hours=1), ahora=ahora)


def test_asignar_a_otro_lo_avisa(juan, papa, familia, ahora, enviados):
    recordatorio = servicios.crear(
        papa, titulo="Traer cemento", fecha_hora=ahora + timedelta(days=1), para=juan, ahora=ahora
    )
    assert recordatorio.dueno == juan
    assert recordatorio.creado_por == papa
    assert recordatorio.espacio == familia

    # Juan no le ha escrito al bot en 24 h: se usa la plantilla de aviso.
    [aviso] = enviados
    assert aviso["tipo"] == "plantilla"
    assert aviso["nombre"] == "aviso"
    assert aviso["destino"] == "56911111111"
    assert "Luis te dejó un recordatorio para mañana jueves 22 a las 10:00" in aviso["parametros"][0]


def test_asignar_con_ventana_abierta_manda_texto(juan, papa, ahora, enviados):
    juan.ultimo_mensaje_entrante = ahora - timedelta(hours=1)
    juan.save()
    servicios.crear(
        papa, titulo="Traer clavos", fecha_hora=ahora + timedelta(hours=3), para=juan, ahora=ahora
    )
    assert enviados[0]["tipo"] == "texto"


def test_no_se_puede_asignar_sin_espacio_compartido(papa, pedro, ahora):
    with pytest.raises(ErrorRecordatorio, match="No compartes"):
        servicios.crear(papa, titulo="Algo", fecha_hora=ahora + timedelta(hours=1), para=pedro, ahora=ahora)


def test_aviso_previo_que_ya_paso_se_ajusta(juan, ahora):
    recordatorio = servicios.crear(
        juan,
        titulo="Reunión",
        fecha_hora=ahora + timedelta(minutes=10),
        tipo="evento",
        avisar_antes_min=30,
        ahora=ahora,
    )
    assert recordatorio.avisar_antes_min == 10
    assert recordatorio.avisar_en == ahora


def test_listar_muestra_propios_y_asignados_por_uno(juan, papa, ahora):
    propio = servicios.crear(juan, titulo="Mío", fecha_hora=ahora + timedelta(hours=1), ahora=ahora)
    para_papa = servicios.crear(
        juan, titulo="Para papá", fecha_hora=ahora + timedelta(hours=2), para=papa, ahora=ahora
    )
    completado = servicios.crear(juan, titulo="Hecho", fecha_hora=ahora + timedelta(hours=3), ahora=ahora)
    servicios.completar(completado, juan, ahora)

    assert servicios.listar(juan) == [propio, para_papa]
    assert servicios.listar(juan, incluir_completados=True) == [propio, para_papa, completado]
    assert servicios.listar(papa) == [para_papa]
    assert servicios.listar(juan, etiqueta="papá") == [para_papa]
    assert servicios.listar(juan, desde=ahora + timedelta(minutes=90)) == [para_papa]


def test_obtener_no_muestra_recordatorios_ajenos(juan, papa, ahora):
    privado = servicios.crear(juan, titulo="Privado", fecha_hora=ahora + timedelta(hours=1), ahora=ahora)
    with pytest.raises(ErrorRecordatorio, match="No encontré"):
        servicios.obtener(papa, privado.id)


def test_posponer_pendiente_cuenta_desde_su_hora(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Algo", fecha_hora=ahora + timedelta(hours=5), ahora=ahora)
    servicios.posponer(recordatorio, minutos=120, ahora=ahora)
    assert recordatorio.fecha_hora == ahora + timedelta(hours=7)
    assert recordatorio.veces_pospuesto == 1


def test_posponer_ya_avisado_cuenta_desde_ahora(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Algo", fecha_hora=ahora, ahora=ahora)
    recordatorio.estado = Recordatorio.Estado.ENVIADO
    recordatorio.save()
    despues = ahora + timedelta(minutes=20)

    servicios.posponer(recordatorio, minutos=60, ahora=despues)
    recordatorio.refresh_from_db()
    assert recordatorio.fecha_hora == despues + timedelta(minutes=60)
    assert recordatorio.avisar_en == recordatorio.fecha_hora
    assert recordatorio.estado == Recordatorio.Estado.PENDIENTE


def test_posponer_sin_datos_falla(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Algo", fecha_hora=ahora + timedelta(hours=1), ahora=ahora)
    with pytest.raises(ErrorRecordatorio):
        servicios.posponer(recordatorio, ahora=ahora)


def test_actualizar_fecha_y_titulo(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Algo", fecha_hora=ahora + timedelta(hours=1), ahora=ahora)
    nueva = ahora + timedelta(days=2)
    servicios.actualizar(recordatorio, titulo="Otra cosa", fecha_hora=nueva, ahora=ahora)
    recordatorio.refresh_from_db()
    assert recordatorio.titulo == "Otra cosa"
    assert recordatorio.fecha_hora == nueva
    assert recordatorio.avisar_en == nueva


def test_completar_asignado_avisa_a_quien_lo_creo(juan, papa, ahora, enviados):
    recordatorio = servicios.crear(
        papa, titulo="Traer cemento", fecha_hora=ahora + timedelta(hours=1), para=juan, ahora=ahora
    )
    enviados.clear()

    servicios.completar(recordatorio, juan, ahora)
    assert recordatorio.estado == Recordatorio.Estado.COMPLETADO
    [aviso] = enviados
    assert aviso["destino"] == "56922222222"
    assert "Juan completó: *Traer cemento*" in aviso["parametros"][0]

    # Completar dos veces no repite el aviso.
    servicios.completar(recordatorio, juan, ahora)
    assert len(enviados) == 1


def test_cancelar_avisa_a_la_otra_persona(juan, papa, ahora, enviados):
    recordatorio = servicios.crear(
        juan, titulo="Comprar clavos", fecha_hora=ahora + timedelta(hours=1), para=papa, ahora=ahora
    )
    enviados.clear()
    servicios.cancelar(recordatorio, juan, ahora)
    assert recordatorio.estado == Recordatorio.Estado.CANCELADO
    assert enviados[0]["destino"] == "56922222222"

    with pytest.raises(ErrorRecordatorio, match="cancelado"):
        servicios.posponer(recordatorio, minutos=10, ahora=ahora)


def test_mismo_horario_dia_siguiente(juan, ahora):
    recordatorio = servicios.crear(juan, titulo="Algo", fecha_hora=ahora, ahora=ahora)
    assert servicios.mismo_horario_dia_siguiente(recordatorio, ahora) == ahora + timedelta(days=1)
    # Si se responde días después, se usa el próximo día que no haya pasado.
    tarde = ahora + timedelta(days=3, hours=1)
    assert servicios.mismo_horario_dia_siguiente(recordatorio, tarde) == ahora + timedelta(days=4)


def test_mismo_horario_respeta_cambio_de_hora(juan):
    # En Chile el horario de verano termina el domingo 4 de abril de 2027: la hora local se mantiene.
    antes = datetime(2027, 4, 3, 9, 0, tzinfo=SANTIAGO)
    recordatorio = servicios.crear(juan, titulo="Algo", fecha_hora=antes, ahora=antes)
    siguiente = servicios.mismo_horario_dia_siguiente(recordatorio, antes)
    assert siguiente.astimezone(SANTIAGO).hour == 9
    # Restar con la misma zona ignora el desfase; en UTC se ve la hora extra del cambio.
    assert siguiente.astimezone(UTC) - antes.astimezone(UTC) == timedelta(hours=25)
