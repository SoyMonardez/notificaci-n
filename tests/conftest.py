from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.cuentas.models import Espacio, Membresia, Usuario
from apps.whatsapp.cliente import ClienteMemoria

SANTIAGO = ZoneInfo("America/Santiago")


@pytest.fixture(autouse=True)
def enviados():
    """Mensajes de WhatsApp "enviados" durante el test (settings_test usa ClienteMemoria)."""
    ClienteMemoria.limpiar()
    yield ClienteMemoria.enviados
    ClienteMemoria.limpiar()


@pytest.fixture
def ahora():
    # Miércoles 21 de octubre de 2026, 10:00 en Santiago (UTC-03:00).
    return datetime(2026, 10, 21, 10, 0, tzinfo=SANTIAGO)


@pytest.fixture
def familia(db):
    return Espacio.objects.create(nombre="Familia", tipo=Espacio.Tipo.FAMILIA)


@pytest.fixture
def negocio(db):
    return Espacio.objects.create(nombre="Monardez Soft", tipo=Espacio.Tipo.NEGOCIO)


def crear_usuario(username, nombre, whatsapp, espacios_roles, alias=""):
    usuario = Usuario.objects.create_user(
        username, first_name=nombre, whatsapp=whatsapp, alias=alias, zona_horaria="America/Santiago"
    )
    for espacio, rol in espacios_roles:
        Membresia.objects.create(usuario=usuario, espacio=espacio, rol=rol)
    return usuario


@pytest.fixture
def juan(familia, negocio):
    return crear_usuario(
        "juan", "Juan", "56911111111", [(familia, Membresia.Rol.DUENO), (negocio, Membresia.Rol.DUENO)]
    )


@pytest.fixture
def papa(familia):
    return crear_usuario(
        "luis", "Luis", "56922222222", [(familia, Membresia.Rol.FAMILIAR)], alias="papá, viejo"
    )


@pytest.fixture
def pedro(negocio):
    return crear_usuario("pedro", "Pedro", "56933333333", [(negocio, Membresia.Rol.EMPLEADO)])


# --- Claude falso para probar el agente sin llamar a la API ---


def texto(contenido):
    return SimpleNamespace(type="text", text=contenido)


def uso(nombre, entrada, id_uso="toolu_1"):
    return SimpleNamespace(type="tool_use", id=id_uso, name=nombre, input=entrada)


def respuesta(stop_reason, *bloques):
    return SimpleNamespace(stop_reason=stop_reason, content=list(bloques), usage=None, model="falso")


class ClaudeFalso:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        # Copia superficial de la lista: el agente la sigue modificando después.
        self.llamadas.append({**kwargs, "messages": list(kwargs["messages"])})
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente
