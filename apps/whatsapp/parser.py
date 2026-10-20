"""Convierte el JSON del webhook de WhatsApp Cloud API en mensajes simples."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MensajeEntrante:
    TEXTO = "texto"
    AUDIO = "audio"
    BOTON = "boton"
    OTRO = "otro"

    id: str
    wa_id: str
    tipo: str
    nombre_perfil: str = ""
    texto: str = ""
    media_id: str = ""
    payload: str = ""
    reenviado: bool = False
    tipo_original: str = ""

    def a_dict(self):
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos):
        return cls(**datos)


def parsear_webhook(payload):
    """Devuelve los mensajes entrantes del payload; ignora estados de entrega y otros eventos."""
    mensajes = []
    for entrada in payload.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            valor = cambio.get("value") or {}
            nombres = {
                c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in valor.get("contacts") or []
            }
            for mensaje in valor.get("messages") or []:
                convertido = _convertir(mensaje, nombres)
                if convertido:
                    mensajes.append(convertido)
    return mensajes


def _convertir(mensaje, nombres):
    remitente = mensaje.get("from")
    id_mensaje = mensaje.get("id")
    if not remitente or not id_mensaje:
        return None

    tipo = mensaje.get("type", "")
    base = {
        "id": id_mensaje,
        "wa_id": remitente,
        "nombre_perfil": nombres.get(remitente, ""),
        "reenviado": bool((mensaje.get("context") or {}).get("forwarded")),
        "tipo_original": tipo,
    }

    if tipo == "text":
        return MensajeEntrante(
            tipo=MensajeEntrante.TEXTO, texto=(mensaje.get("text") or {}).get("body", ""), **base
        )
    if tipo == "audio":
        return MensajeEntrante(
            tipo=MensajeEntrante.AUDIO, media_id=(mensaje.get("audio") or {}).get("id", ""), **base
        )
    if tipo == "interactive":
        interactivo = mensaje.get("interactive") or {}
        respuesta = interactivo.get("button_reply") or interactivo.get("list_reply") or {}
        return MensajeEntrante(
            tipo=MensajeEntrante.BOTON,
            payload=respuesta.get("id", ""),
            texto=respuesta.get("title", ""),
            **base,
        )
    if tipo == "button":
        # Respuesta rápida de una plantilla.
        boton = mensaje.get("button") or {}
        return MensajeEntrante(
            tipo=MensajeEntrante.BOTON, payload=boton.get("payload", ""), texto=boton.get("text", ""), **base
        )
    return MensajeEntrante(tipo=MensajeEntrante.OTRO, **base)
