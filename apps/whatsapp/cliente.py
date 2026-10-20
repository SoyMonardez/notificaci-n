"""Clientes para enviar mensajes por WhatsApp.

- ClienteGraph: la API real de Meta (WhatsApp Cloud API).
- ClienteConsola: imprime los mensajes en la terminal, para desarrollar sin Meta.
- ClienteMemoria: guarda los mensajes en una lista, para los tests.

Se elige con el setting WHATSAPP_CLIENTE.
"""

import logging
from dataclasses import dataclass

import httpx
from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

# Límites de la API de WhatsApp.
MAX_TEXTO = 4096
MAX_CUERPO_INTERACTIVO = 1024
MAX_TITULO_BOTON = 20
MAX_PARAMETRO_PLANTILLA = 1024


@dataclass(frozen=True)
class Boton:
    id: str
    titulo: str


def parametro_plantilla(texto):
    """Las plantillas no aceptan saltos de línea, tabulaciones ni más de 4 espacios seguidos."""
    limpio = " · ".join(linea.strip() for linea in texto.replace("\t", " ").splitlines() if linea.strip())
    while "     " in limpio:
        limpio = limpio.replace("     ", "    ")
    return limpio[:MAX_PARAMETRO_PLANTILLA]


class ErrorWhatsApp(Exception):
    pass


class ClienteGraph:
    def __init__(self):
        if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
            raise ErrorWhatsApp("Faltan WHATSAPP_TOKEN o WHATSAPP_PHONE_NUMBER_ID")
        self._http = httpx.Client(
            base_url=f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/",
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            timeout=20,
        )

    def _enviar(self, destino, contenido):
        cuerpo = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": destino, **contenido}
        respuesta = self._http.post(f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages", json=cuerpo)
        if respuesta.is_error:
            raise ErrorWhatsApp(f"WhatsApp respondió {respuesta.status_code}: {respuesta.text[:500]}")
        return respuesta.json()

    def enviar_texto(self, destino, texto):
        return self._enviar(
            destino, {"type": "text", "text": {"body": texto[:MAX_TEXTO], "preview_url": False}}
        )

    def enviar_botones(self, destino, texto, botones):
        return self._enviar(
            destino,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": texto[:MAX_CUERPO_INTERACTIVO]},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": b.id, "title": b.titulo[:MAX_TITULO_BOTON]}}
                            for b in botones[:3]
                        ]
                    },
                },
            },
        )

    def enviar_plantilla(self, destino, nombre, parametros, payloads_botones=()):
        componentes = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": parametro_plantilla(p)} for p in parametros],
            }
        ]
        for indice, payload in enumerate(payloads_botones):
            componentes.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(indice),
                    "parameters": [{"type": "payload", "payload": payload}],
                }
            )
        return self._enviar(
            destino,
            {
                "type": "template",
                "template": {
                    "name": nombre,
                    "language": {"code": settings.WHATSAPP_PLANTILLA_IDIOMA},
                    "components": componentes,
                },
            },
        )

    def descargar_media(self, media_id):
        info = self._http.get(media_id)
        if info.is_error:
            raise ErrorWhatsApp(f"No se pudo obtener el media {media_id}: {info.status_code}")
        datos = info.json()
        archivo = self._http.get(datos["url"])
        if archivo.is_error:
            raise ErrorWhatsApp(f"No se pudo descargar el media {media_id}: {archivo.status_code}")
        return archivo.content, datos.get("mime_type", "")


class ClienteMemoria:
    """Guarda lo enviado en `ClienteMemoria.enviados` (compartido entre instancias)."""

    enviados = []

    @classmethod
    def limpiar(cls):
        cls.enviados.clear()

    def enviar_texto(self, destino, texto):
        self.enviados.append({"tipo": "texto", "destino": destino, "texto": texto})

    def enviar_botones(self, destino, texto, botones):
        self.enviados.append(
            {"tipo": "botones", "destino": destino, "texto": texto, "botones": list(botones)}
        )

    def enviar_plantilla(self, destino, nombre, parametros, payloads_botones=()):
        self.enviados.append(
            {
                "tipo": "plantilla",
                "destino": destino,
                "nombre": nombre,
                "parametros": [parametro_plantilla(p) for p in parametros],
                "payloads": list(payloads_botones),
            }
        )

    def descargar_media(self, media_id):
        return b"", ""


class ClienteConsola:
    """Muestra cada mensaje en la terminal en vez de enviarlo."""

    def enviar_texto(self, destino, texto):
        print(f"\n💬 → {destino}\n{texto}\n", flush=True)

    def enviar_botones(self, destino, texto, botones):
        opciones = "  ".join(f"[{b.titulo}] ({b.id})" for b in botones)
        print(f"\n💬 → {destino}\n{texto}\n{opciones}\n", flush=True)

    def enviar_plantilla(self, destino, nombre, parametros, payloads_botones=()):
        valores = [parametro_plantilla(p) for p in parametros]
        print(
            f"\n📨 plantilla «{nombre}» → {destino}: {valores} botones={list(payloads_botones)}\n", flush=True
        )

    def descargar_media(self, media_id):
        return b"", ""


_clientes = {}


def obtener_cliente():
    """Una instancia por clase configurada y por proceso, para reutilizar la conexión HTTP."""
    ruta = settings.WHATSAPP_CLIENTE
    if ruta not in _clientes:
        _clientes[ruta] = import_string(ruta)()
    return _clientes[ruta]
