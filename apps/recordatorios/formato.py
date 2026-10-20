"""Textos en español para fechas y mensajes. No depende del locale del servidor."""

from django.utils import timezone

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def fecha_larga(dt, tz):
    local = dt.astimezone(tz)
    return f"{DIAS[local.weekday()]} {local.day} de {MESES[local.month - 1]} de {local.year}, {local:%H:%M}"


def fecha_legible(dt, tz, ahora=None):
    """Ej: «hoy a las 15:00», «mañana jueves 22 a las 09:00», «el lunes 2 de noviembre a las 09:00»."""
    ahora = (ahora or timezone.now()).astimezone(tz)
    local = dt.astimezone(tz)
    hora = f"a las {local:%H:%M}"
    dias = (local.date() - ahora.date()).days
    dia = DIAS[local.weekday()]

    if dias == 0:
        return f"hoy {hora}"
    if dias == 1:
        return f"mañana {dia} {local.day} {hora}"
    if dias == -1:
        return f"ayer {hora}"
    if 2 <= dias <= 6:
        return f"el {dia} {local.day} {hora}"
    anio = f" de {local.year}" if local.year != ahora.year else ""
    return f"el {dia} {local.day} de {MESES[local.month - 1]}{anio} {hora}"


def texto_aviso(recordatorio, ahora=None):
    tz = recordatorio.dueno.tz
    if recordatorio.tipo == recordatorio.Tipo.EVENTO:
        encabezado = f"📅 *{recordatorio.titulo}*"
        if recordatorio.avisar_antes_min:
            encabezado += f" ({fecha_legible(recordatorio.fecha_hora, tz, ahora)})"
    else:
        encabezado = f"⏰ *{recordatorio.titulo}*"
    partes = [encabezado]
    if recordatorio.detalle:
        partes.append(recordatorio.detalle)
    if recordatorio.es_asignado:
        partes.append(f"_Te lo dejó {recordatorio.creado_por.nombre_visible}._")
    return "\n".join(partes)
