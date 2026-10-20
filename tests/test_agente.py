from datetime import timedelta
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from apps.asistente import agente
from apps.asistente.models import MensajeConversacion
from apps.asistente.prompts import SISTEMA
from apps.recordatorios.models import Recordatorio

from .conftest import ClaudeFalso, respuesta, texto, uso

pytestmark = pytest.mark.django_db

CREAR = {"titulo": "Llamar a Pedro", "fecha_hora": "2026-10-22T09:00:00-03:00", "ambito": "negocio"}


def test_crea_recordatorio_con_herramienta_y_responde(juan, papa, ahora):
    claude = ClaudeFalso(
        respuesta("tool_use", uso("crear_recordatorio", CREAR)),
        respuesta("end_turn", texto("Listo ✅ Te aviso *mañana jueves 22 a las 09:00*.")),
    )

    final = agente.responder(juan, "recuérdame mañana a las 9 llamar a Pedro", ahora=ahora, cliente=claude)

    assert final == "Listo ✅ Te aviso *mañana jueves 22 a las 09:00*."
    recordatorio = Recordatorio.objects.get()
    assert recordatorio.titulo == "Llamar a Pedro"
    assert recordatorio.espacio.tipo == "negocio"

    # La segunda llamada lleva el resultado de la herramienta.
    resultado = claude.llamadas[1]["messages"][-1]["content"][0]
    assert resultado["type"] == "tool_result"
    assert resultado["tool_use_id"] == "toolu_1"
    assert "is_error" not in resultado
    assert '"cuando": "mañana jueves 22 a las 09:00"' in resultado["content"]

    historial = list(MensajeConversacion.objects.values_list("rol", "texto"))
    assert historial == [
        ("user", "recuérdame mañana a las 9 llamar a Pedro"),
        ("assistant", "Listo ✅ Te aviso *mañana jueves 22 a las 09:00*."),
    ]


def test_parametros_de_la_llamada(juan, papa, ahora, settings):
    settings.CLAUDE_MODEL = "claude-opus-5-5"
    claude = ClaudeFalso(respuesta("end_turn", texto("Hola")))
    agente.responder(juan, "hola", ahora=ahora, cliente=claude)

    llamada = claude.llamadas[0]
    assert llamada["model"] == "claude-opus-5-5"
    assert llamada["system"] == SISTEMA
    assert llamada["betas"] == ["server-side-fallback-2026-07-01"]
    assert llamada["fallbacks"] == "default"
    assert llamada["output_config"] == {"effort": "low"}
    assert llamada["cache_control"] == {"type": "ephemeral"}
    assert "tool_choice" not in llamada
    assert all(t["strict"] for t in llamada["tools"])

    contexto, mensaje = llamada["messages"][-1]["content"]
    assert "Ahora: miércoles 21 de octubre de 2026, 10:00 (America/Santiago, UTC-03:00)" in contexto["text"]
    assert "Usuario: Juan" in contexto["text"]
    assert "Luis (alias: papá, viejo)" in contexto["text"]
    assert "Ámbitos: familia, negocio" in contexto["text"]
    assert mensaje["text"] == "hola"


def test_error_de_herramienta_vuelve_a_la_ia(juan, ahora):
    pasado = {**CREAR, "fecha_hora": "2026-10-20T09:00:00-03:00"}
    claude = ClaudeFalso(
        respuesta("tool_use", uso("crear_recordatorio", pasado)),
        respuesta("end_turn", texto("Esa fecha ya pasó, ¿para cuándo lo dejo?")),
    )
    agente.responder(juan, "recuérdame ayer", ahora=ahora, cliente=claude)

    resultado = claude.llamadas[1]["messages"][-1]["content"][0]
    assert resultado["is_error"] is True
    assert "ya pasó" in resultado["content"]
    assert not Recordatorio.objects.exists()


def test_rechazo(juan, ahora):
    claude = ClaudeFalso(respuesta("refusal"))
    assert agente.responder(juan, "algo", ahora=ahora, cliente=claude) == agente.RESPUESTA_RECHAZO


def test_error_de_conexion(juan, ahora):
    error = anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    claude = ClaudeFalso(error)
    assert agente.responder(juan, "algo", ahora=ahora, cliente=claude) == agente.RESPUESTA_ERROR
    # El mensaje del usuario queda guardado para el próximo intento.
    assert list(MensajeConversacion.objects.values_list("rol", flat=True)) == ["user"]


def test_error_despues_de_guardar_cambios(juan, ahora):
    error = anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    claude = ClaudeFalso(respuesta("tool_use", uso("crear_recordatorio", CREAR)), error)
    assert agente.responder(juan, "recuérdame", ahora=ahora, cliente=claude) == agente.RESPUESTA_ERROR_PARCIAL
    assert Recordatorio.objects.count() == 1


def test_historial_alterna_roles_y_junta_mensajes_sin_respuesta(juan, ahora):
    MensajeConversacion.objects.create(
        usuario=juan, rol="assistant", texto="huérfano", creado_en=ahora - timedelta(hours=3)
    )
    MensajeConversacion.objects.create(
        usuario=juan, rol="user", texto="primero", creado_en=ahora - timedelta(hours=2)
    )
    MensajeConversacion.objects.create(
        usuario=juan, rol="assistant", texto="ok", creado_en=ahora - timedelta(hours=2)
    )
    MensajeConversacion.objects.create(
        usuario=juan, rol="user", texto="sin respuesta", creado_en=ahora - timedelta(hours=1)
    )
    MensajeConversacion.objects.create(
        usuario=juan, rol="user", texto="viejo", creado_en=ahora - timedelta(days=2)
    )

    claude = ClaudeFalso(respuesta("end_turn", texto("Hola")))
    agente.responder(juan, "nuevo", ahora=ahora, cliente=claude)

    mensajes = claude.llamadas[0]["messages"]
    assert [m["role"] for m in mensajes] == ["user", "assistant", "user"]
    assert mensajes[0]["content"] == "primero"
    textos = [bloque["text"] for bloque in mensajes[-1]["content"]]
    assert textos[0] == "sin respuesta"
    assert textos[-1] == "nuevo"


def test_cambio_de_modelo_a_mitad_descarta_herramientas_previas(juan, ahora):
    claude = ClaudeFalso(
        respuesta(
            "end_turn",
            uso("crear_recordatorio", CREAR),
            SimpleNamespace(type="fallback"),
            texto("No pude con eso."),
        )
    )
    assert agente.responder(juan, "algo", ahora=ahora, cliente=claude) == "No pude con eso."
    assert not Recordatorio.objects.exists()


def test_demasiados_pasos(juan, ahora):
    claude = ClaudeFalso(
        *[respuesta("tool_use", uso("listar_recordatorios", {}, f"t{i}")) for i in range(agente.MAX_PASOS)]
    )
    assert agente.responder(juan, "algo", ahora=ahora, cliente=claude) == agente.RESPUESTA_ENREDO
