import re
import unicodedata

from .models import Espacio, Usuario


def normalizar_numero(numero):
    return re.sub(r"\D", "", numero or "")


def usuario_por_whatsapp(numero):
    """Devuelve el usuario activo con ese número, o None si no está autorizado."""
    numero = normalizar_numero(numero)
    if not numero:
        return None
    return Usuario.objects.filter(whatsapp=numero, is_active=True).first()


def _sin_tildes(texto):
    texto = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def companeros(usuario):
    """Usuarios activos que comparten al menos un espacio con `usuario` (sin incluirlo)."""
    return (
        Usuario.objects.filter(espacios__in=usuario.espacios.all(), is_active=True)
        .exclude(pk=usuario.pk)
        .distinct()
        .order_by("first_name", "username")
    )


def buscar_companero(usuario, nombre):
    """Encuentra, entre los compañeros de espacio, a quien se nombra por nombre, usuario o alias."""
    buscado = _sin_tildes(nombre)
    if not buscado:
        return None
    for candidato in companeros(usuario):
        nombres = [candidato.first_name, candidato.username, *candidato.lista_alias()]
        if buscado in {_sin_tildes(n) for n in nombres if n}:
            return candidato
    return None


def espacios_compartidos(a, b):
    return Espacio.objects.filter(membresias__usuario=a).filter(membresias__usuario=b).distinct()


def elegir_espacio(creador, dueno, tipo=None):
    """Espacio al que pertenece un recordatorio: uno que compartan creador y dueño, preferentemente del tipo pedido."""
    candidatos = espacios_compartidos(creador, dueno).order_by("id")
    if tipo:
        del_tipo = candidatos.filter(tipo=tipo).first()
        if del_tipo:
            return del_tipo
    return candidatos.first()
