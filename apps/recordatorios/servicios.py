"""Lógica de recordatorios. La usan las herramientas de la IA, los botones de WhatsApp y las tareas."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.cuentas.servicios import elegir_espacio

from . import notificaciones
from .formato import fecha_legible
from .models import Recordatorio

# Margen para fechas "ya" o "en 1 minuto" calculadas con la hora redondeada.
TOLERANCIA_PASADO = timedelta(minutes=2)
MAX_LISTADO = 30


class ErrorRecordatorio(Exception):
    """Error con un mensaje apto para mostrarle al usuario (o devolverle a la IA)."""


def _validar_fecha(fecha_hora, tz, ahora):
    if timezone.is_naive(fecha_hora):
        raise ErrorRecordatorio("La fecha debe incluir zona horaria.")
    if fecha_hora < ahora - TOLERANCIA_PASADO:
        raise ErrorRecordatorio(f"Esa fecha ya pasó ({fecha_legible(fecha_hora, tz, ahora)}).")


def _validar_activo(recordatorio):
    if not recordatorio.activo:
        raise ErrorRecordatorio(
            f"El recordatorio #{recordatorio.id} ya está {recordatorio.get_estado_display().lower()}."
        )


def _minutos_antes_posibles(fecha_hora, avisar_antes_min, ahora):
    """Si el aviso previo ya quedó en el pasado, se reduce para avisar de inmediato."""
    if avisar_antes_min < 0:
        raise ErrorRecordatorio("Los minutos de anticipación no pueden ser negativos.")
    disponibles = max(int((fecha_hora - ahora).total_seconds() // 60), 0)
    return min(avisar_antes_min, disponibles)


def crear(
    creador,
    *,
    titulo,
    fecha_hora,
    para=None,
    detalle="",
    tipo=Recordatorio.Tipo.RECORDATORIO,
    avisar_antes_min=0,
    etiqueta="",
    ambito=None,
    ahora=None,
):
    ahora = ahora or timezone.now()
    titulo = (titulo or "").strip()
    if not titulo:
        raise ErrorRecordatorio("El recordatorio necesita un título.")
    dueno = para or creador
    _validar_fecha(fecha_hora, dueno.tz, ahora)

    espacio = elegir_espacio(creador, dueno, ambito)
    if espacio is None:
        if dueno == creador:
            raise ErrorRecordatorio(
                "Todavía no perteneces a ningún espacio. Pide que te agreguen desde el admin."
            )
        raise ErrorRecordatorio(f"No compartes ningún espacio con {dueno.nombre_visible}.")

    recordatorio = Recordatorio.objects.create(
        espacio=espacio,
        dueno=dueno,
        creado_por=creador,
        titulo=titulo[:200],
        detalle=(detalle or "").strip(),
        tipo=tipo,
        fecha_hora=fecha_hora,
        avisar_antes_min=_minutos_antes_posibles(fecha_hora, avisar_antes_min, ahora),
        etiqueta=(etiqueta or "").strip()[:100],
    )
    if recordatorio.es_asignado:
        notificaciones.asignacion(recordatorio, ahora)
    return recordatorio


def visibles_para(usuario):
    return Recordatorio.objects.filter(Q(dueno=usuario) | Q(creado_por=usuario)).select_related(
        "dueno", "creado_por"
    )


def listar(usuario, *, desde=None, hasta=None, incluir_completados=False, etiqueta=""):
    consulta = visibles_para(usuario)
    if not incluir_completados:
        consulta = consulta.filter(estado__in=[Recordatorio.Estado.PENDIENTE, Recordatorio.Estado.ENVIADO])
    if desde:
        consulta = consulta.filter(fecha_hora__gte=desde)
    if hasta:
        consulta = consulta.filter(fecha_hora__lte=hasta)
    if etiqueta:
        consulta = consulta.filter(Q(etiqueta__icontains=etiqueta) | Q(titulo__icontains=etiqueta))
    return list(consulta.order_by("fecha_hora")[:MAX_LISTADO])


def obtener(usuario, recordatorio_id):
    recordatorio = visibles_para(usuario).filter(pk=recordatorio_id).first()
    if recordatorio is None:
        raise ErrorRecordatorio(f"No encontré el recordatorio #{recordatorio_id}.")
    return recordatorio


def _reprogramar(recordatorio, fecha_hora, ahora):
    recordatorio.fecha_hora = fecha_hora
    recordatorio.avisar_antes_min = _minutos_antes_posibles(fecha_hora, recordatorio.avisar_antes_min, ahora)
    recordatorio.estado = Recordatorio.Estado.PENDIENTE
    recordatorio.aviso_enviado_en = None
    recordatorio.intentos_envio = 0


def posponer(recordatorio, *, minutos=None, nueva_fecha=None, ahora=None):
    ahora = ahora or timezone.now()
    _validar_activo(recordatorio)
    if nueva_fecha is None:
        if not minutos or minutos <= 0:
            raise ErrorRecordatorio("Indica cuántos minutos posponer o una nueva fecha.")
        # Si ya avisó (o ya pasó), se cuenta desde ahora; si aún no, desde la hora que tenía.
        base = recordatorio.fecha_hora
        if recordatorio.estado == Recordatorio.Estado.ENVIADO or base <= ahora:
            base = ahora
        nueva_fecha = base + timedelta(minutes=minutos)
    _validar_fecha(nueva_fecha, recordatorio.dueno.tz, ahora)
    _reprogramar(recordatorio, nueva_fecha, ahora)
    recordatorio.veces_pospuesto += 1
    recordatorio.save()
    return recordatorio


def mismo_horario_dia_siguiente(recordatorio, ahora=None):
    """La misma hora local del día siguiente; si eso ya pasó, el próximo día en que no haya pasado."""
    ahora = ahora or timezone.now()
    nueva = recordatorio.fecha_hora.astimezone(recordatorio.dueno.tz) + timedelta(days=1)
    while nueva <= ahora:
        nueva += timedelta(days=1)
    return nueva


def actualizar(
    recordatorio,
    *,
    titulo=None,
    fecha_hora=None,
    detalle=None,
    avisar_antes_min=None,
    etiqueta=None,
    ahora=None,
):
    ahora = ahora or timezone.now()
    _validar_activo(recordatorio)
    if titulo is not None:
        if not titulo.strip():
            raise ErrorRecordatorio("El título no puede quedar vacío.")
        recordatorio.titulo = titulo.strip()[:200]
    if detalle is not None:
        recordatorio.detalle = detalle.strip()
    if etiqueta is not None:
        recordatorio.etiqueta = etiqueta.strip()[:100]
    if avisar_antes_min is not None:
        recordatorio.avisar_antes_min = avisar_antes_min
    if fecha_hora is not None:
        _validar_fecha(fecha_hora, recordatorio.dueno.tz, ahora)
        _reprogramar(recordatorio, fecha_hora, ahora)
    elif avisar_antes_min is not None:
        recordatorio.avisar_antes_min = _minutos_antes_posibles(
            recordatorio.fecha_hora, avisar_antes_min, ahora
        )
    recordatorio.save()
    return recordatorio


def completar(recordatorio, por, ahora=None):
    ahora = ahora or timezone.now()
    if recordatorio.estado == Recordatorio.Estado.COMPLETADO:
        return recordatorio
    _validar_activo(recordatorio)
    recordatorio.estado = Recordatorio.Estado.COMPLETADO
    recordatorio.completado_en = ahora
    recordatorio.save()
    if recordatorio.es_asignado and por != recordatorio.creado_por:
        notificaciones.completado(recordatorio, por, ahora)
    return recordatorio


def cancelar(recordatorio, por, ahora=None):
    _validar_activo(recordatorio)
    recordatorio.estado = Recordatorio.Estado.CANCELADO
    recordatorio.save()
    if recordatorio.es_asignado:
        otro = recordatorio.dueno if por == recordatorio.creado_por else recordatorio.creado_por
        notificaciones.cancelado(recordatorio, por, otro, ahora)
    return recordatorio


def pendientes_de_aviso(ahora=None):
    ahora = ahora or timezone.now()
    return Recordatorio.objects.filter(estado=Recordatorio.Estado.PENDIENTE, avisar_en__lte=ahora).order_by(
        "avisar_en"
    )
