from apps.whatsapp.parser import MensajeEntrante, parsear_webhook


def envoltorio(*mensajes, contactos=None, estados=None):
    valor = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "123"}}
    if contactos is not None:
        valor["contacts"] = contactos
    if mensajes:
        valor["messages"] = list(mensajes)
    if estados:
        valor["statuses"] = estados
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"value": valor}]}]}


def test_texto_con_nombre_de_perfil():
    payload = envoltorio(
        {"from": "56911111111", "id": "wamid.1", "type": "text", "text": {"body": "hola"}},
        contactos=[{"wa_id": "56911111111", "profile": {"name": "Juan"}}],
    )
    [mensaje] = parsear_webhook(payload)
    assert mensaje.tipo == MensajeEntrante.TEXTO
    assert mensaje.texto == "hola"
    assert mensaje.wa_id == "56911111111"
    assert mensaje.nombre_perfil == "Juan"
    assert mensaje.reenviado is False


def test_mensaje_reenviado():
    payload = envoltorio(
        {
            "from": "56911111111",
            "id": "wamid.2",
            "type": "text",
            "text": {"body": "cambiar el logo"},
            "context": {"forwarded": True},
        }
    )
    assert parsear_webhook(payload)[0].reenviado is True


def test_boton_de_mensaje_interactivo():
    payload = envoltorio(
        {
            "from": "56911111111",
            "id": "wamid.3",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "rec:listo:7", "title": "✅ Listo"},
            },
        }
    )
    [mensaje] = parsear_webhook(payload)
    assert mensaje.tipo == MensajeEntrante.BOTON
    assert mensaje.payload == "rec:listo:7"


def test_boton_de_plantilla():
    payload = envoltorio(
        {
            "from": "56911111111",
            "id": "wamid.4",
            "type": "button",
            "button": {"payload": "rec:1h:7", "text": "+1 hora"},
        }
    )
    [mensaje] = parsear_webhook(payload)
    assert mensaje.tipo == MensajeEntrante.BOTON
    assert mensaje.payload == "rec:1h:7"


def test_audio():
    payload = envoltorio(
        {
            "from": "56911111111",
            "id": "wamid.5",
            "type": "audio",
            "audio": {"id": "media-9", "mime_type": "audio/ogg"},
        }
    )
    [mensaje] = parsear_webhook(payload)
    assert mensaje.tipo == MensajeEntrante.AUDIO
    assert mensaje.media_id == "media-9"


def test_otros_tipos_se_marcan_como_otro():
    payload = envoltorio({"from": "56911111111", "id": "wamid.6", "type": "image", "image": {"id": "x"}})
    [mensaje] = parsear_webhook(payload)
    assert mensaje.tipo == MensajeEntrante.OTRO
    assert mensaje.tipo_original == "image"


def test_estados_de_entrega_y_mensajes_incompletos_se_ignoran():
    payload = envoltorio(
        {"id": "wamid.7", "type": "text", "text": {"body": "sin remitente"}},
        estados=[{"id": "wamid.0", "status": "delivered"}],
    )
    assert parsear_webhook(payload) == []
    assert parsear_webhook({}) == []


def test_ida_y_vuelta_por_diccionario():
    mensaje = MensajeEntrante(id="a", wa_id="1", tipo=MensajeEntrante.TEXTO, texto="hola")
    assert MensajeEntrante.desde_dict(mensaje.a_dict()) == mensaje
