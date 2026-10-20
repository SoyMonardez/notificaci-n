"""El agente con el SDK real de Anthropic y un transporte HTTP simulado: verifica la solicitud exacta."""

import json

import anthropic
import httpx2
import pytest

from apps.asistente import agente
from apps.recordatorios.models import Recordatorio

pytestmark = pytest.mark.django_db


def mensaje_api(stop_reason, contenido):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": contenido,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def test_solicitudes_reales_del_sdk(juan, ahora, settings):
    settings.CLAUDE_MODEL = "claude-opus-5-5"
    settings.CLAUDE_EFFORT = "low"
    respuestas = [
        mensaje_api(
            "tool_use",
            [
                {"type": "thinking", "thinking": "", "signature": "firma-1"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "crear_recordatorio",
                    "input": {"titulo": "Pagar la luz", "fecha_hora": "2026-10-22T09:00:00-03:00"},
                },
            ],
        ),
        mensaje_api("end_turn", [{"type": "text", "text": "Listo ✅"}]),
    ]
    solicitudes = []

    def manejar(solicitud):
        solicitudes.append(solicitud)
        return httpx2.Response(200, json=respuestas.pop(0))

    cliente = anthropic.Anthropic(
        api_key="clave-falsa",
        http_client=httpx2.Client(transport=httpx2.MockTransport(manejar)),
        max_retries=0,
    )

    assert (
        agente.responder(juan, "recuérdame pagar la luz mañana", ahora=ahora, cliente=cliente) == "Listo ✅"
    )
    assert Recordatorio.objects.get().titulo == "Pagar la luz"

    primera, segunda = (json.loads(s.content) for s in solicitudes)
    assert "server-side-fallback-2026-07-01" in solicitudes[0].headers["anthropic-beta"]
    assert primera["model"] == "claude-opus-5-5"
    assert primera["fallbacks"] == "default"
    assert primera["output_config"] == {"effort": "low"}
    assert primera["cache_control"] == {"type": "ephemeral"}
    assert [t["name"] for t in primera["tools"]][0] == "crear_recordatorio"
    assert "tool_choice" not in primera

    # El turno del asistente (con su bloque de thinking intacto) vuelve tal cual, seguido del resultado.
    turno_asistente, resultados = segunda["messages"][-2:]
    assert turno_asistente["role"] == "assistant"
    assert [b["type"] for b in turno_asistente["content"]] == ["thinking", "tool_use"]
    assert turno_asistente["content"][0]["signature"] == "firma-1"
    assert resultados["content"][0]["tool_use_id"] == "toolu_1"
