import hashlib
import hmac


def firma_valida(cuerpo: bytes, cabecera: str, secreto: str) -> bool:
    """Comprueba la cabecera X-Hub-Signature-256 que Meta firma con el secreto de la app."""
    if not cabecera or not secreto or not cabecera.startswith("sha256="):
        return False
    esperada = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(cabecera.removeprefix("sha256="), esperada)
