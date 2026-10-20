"""Herramientas que la IA puede usar. Cada una valida su entrada y llama a los servicios.

Las definiciones son fijas y en orden estable para que el caché del prompt funcione.
"""

import json
import unicodedata
from datetime import datetime

from django.utils import timezone

from apps.cuentas.servicios import buscar_companero
from apps.recordatorios import servicios
from apps.recordatorios.formato import fecha_legible
from apps.recordatorios.models import Recordatorio
from apps.recordatorios.servicios import ErrorRecordatorio


def _objeto(propiedades, requeridos=()):
    return {
        "type": "object",
        "properties": propiedades,
        "required": list(requeridos),
        "additionalProperties": False,
    }


_FECHA = "Fecha y hora en ISO 8601 con diferencia horaria, ej: 2026-10-21T09:00:00-03:00."
_ID = {"type": "integer", "description": "Id del recordatorio (el número que aparece como #12)."}

DEFINICIONES = [
    {
        "name": "crear_recordatorio",
        "description": (
            "Crea un recordatorio o evento. Por defecto es para el mismo usuario; usa 'para' cuando "
            "lo quiere dejar a otra persona del [Contexto] (ej: 'recuérdale a papá...')."
        ),
        "strict": True,
        "input_schema": _objeto(
            {
                "titulo": {"type": "string", "description": "Título corto y claro, ej: 'Llamar a Pedro'."},
                "fecha_hora": {"type": "string", "description": f"Cuándo ocurre o cuándo avisar. {_FECHA}"},
                "detalle": {
                    "type": "string",
                    "description": "Detalle opcional; para pedidos largos, una lista con guiones.",
                },
                "tipo": {
                    "type": "string",
                    "enum": ["recordatorio", "evento"],
                    "description": "'evento' para reuniones o citas con hora fija; si no, 'recordatorio'.",
                },
                "avisar_antes_min": {
                    "type": "integer",
                    "description": "Minutos de anticipación del aviso (útil en eventos). 0 = a la hora exacta.",
                },
                "para": {"type": "string", "description": "Nombre o alias de otra persona del [Contexto]."},
                "ambito": {"type": "string", "enum": ["familia", "negocio"]},
                "etiqueta": {"type": "string", "description": "Cliente o proyecto relacionado, si lo hay."},
            },
            ["titulo", "fecha_hora"],
        ),
    },
    {
        "name": "listar_recordatorios",
        "description": (
            "Lista los recordatorios del usuario (los suyos y los que dejó a otros). Úsala para '¿qué tengo hoy?', "
            "'¿qué tengo pendiente del cliente X?' o para encontrar el id de un recordatorio."
        ),
        "strict": True,
        "input_schema": _objeto(
            {
                "desde": {"type": "string", "description": f"Opcional. {_FECHA}"},
                "hasta": {"type": "string", "description": f"Opcional. {_FECHA}"},
                "incluir_completados": {"type": "boolean"},
                "texto": {"type": "string", "description": "Filtra por etiqueta o palabra del título."},
            }
        ),
    },
    {
        "name": "posponer_recordatorio",
        "description": "Pospone un recordatorio: indica 'minutos' (ej: 60) o 'nueva_fecha_hora'.",
        "strict": True,
        "input_schema": _objeto(
            {
                "recordatorio_id": _ID,
                "minutos": {"type": "integer"},
                "nueva_fecha_hora": {"type": "string", "description": _FECHA},
            },
            ["recordatorio_id"],
        ),
    },
    {
        "name": "actualizar_recordatorio",
        "description": "Cambia título, fecha, detalle, anticipación o etiqueta de un recordatorio. Envía solo lo que cambia.",
        "strict": True,
        "input_schema": _objeto(
            {
                "recordatorio_id": _ID,
                "titulo": {"type": "string"},
                "fecha_hora": {"type": "string", "description": _FECHA},
                "detalle": {"type": "string"},
                "avisar_antes_min": {"type": "integer"},
                "etiqueta": {"type": "string"},
            },
            ["recordatorio_id"],
        ),
    },
    {
        "name": "completar_recordatorio",
        "description": "Marca un recordatorio como hecho.",
        "strict": True,
        "input_schema": _objeto({"recordatorio_id": _ID}, ["recordatorio_id"]),
    },
    {
        "name": "cancelar_recordatorio",
        "description": "Cancela un recordatorio que ya no hace falta.",
        "strict": True,
        "input_schema": _objeto({"recordatorio_id": _ID}, ["recordatorio_id"]),
    },
]

NOMBRES = {d["name"] for d in DEFINICIONES}


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


class Herramientas:
    def __init__(self, usuario, ahora=None):
        self.usuario = usuario
        self.ahora = ahora or timezone.now()
        self.hubo_cambios = False

    def definiciones(self):
        return DEFINICIONES

    def ejecutar(self, nombre, entrada):
        """Devuelve (texto_resultado, es_error)."""
        if nombre not in NOMBRES:
            return f"Herramienta desconocida: {nombre}", True
        try:
            resultado = getattr(self, f"_{nombre}")(**(entrada or {}))
        except ErrorRecordatorio as error:
            return str(error), True
        except TypeError as error:
            return f"Parámetros inválidos: {error}", True
        return json.dumps(resultado, ensure_ascii=False), False

    # --- utilidades ---

    def _fecha(self, texto):
        try:
            fecha = datetime.fromisoformat(texto)
        except (TypeError, ValueError) as exc:
            raise ErrorRecordatorio(f"No entendí la fecha «{texto}». Usa ISO 8601.") from exc
        if timezone.is_naive(fecha):
            fecha = fecha.replace(tzinfo=self.usuario.tz)
        return fecha

    def _persona(self, nombre):
        if not nombre:
            return None
        propios = {_normalizar(self.usuario.first_name), _normalizar(self.usuario.username), "yo", "mi", "mí"}
        if _normalizar(nombre) in propios:
            return None
        persona = buscar_companero(self.usuario, nombre)
        if persona is None:
            raise ErrorRecordatorio(f"No encontré a «{nombre}» entre las personas del bot.")
        return persona

    def _resumen(self, recordatorio):
        datos = {
            "id": recordatorio.id,
            "titulo": recordatorio.titulo,
            "cuando": fecha_legible(recordatorio.fecha_hora, self.usuario.tz, self.ahora),
            "estado": recordatorio.get_estado_display(),
        }
        if recordatorio.dueno_id != self.usuario.id:
            datos["para"] = recordatorio.dueno.nombre_visible
        if recordatorio.creado_por_id != self.usuario.id:
            datos["te_lo_dejo"] = recordatorio.creado_por.nombre_visible
        if recordatorio.tipo == Recordatorio.Tipo.EVENTO:
            datos["tipo"] = "evento"
        if recordatorio.avisar_antes_min:
            datos["avisa_minutos_antes"] = recordatorio.avisar_antes_min
        if recordatorio.detalle:
            datos["detalle"] = recordatorio.detalle
        if recordatorio.etiqueta:
            datos["etiqueta"] = recordatorio.etiqueta
        return datos

    def _obtener(self, recordatorio_id):
        return servicios.obtener(self.usuario, recordatorio_id)

    # --- herramientas ---

    def _crear_recordatorio(
        self,
        titulo,
        fecha_hora,
        detalle="",
        tipo="recordatorio",
        avisar_antes_min=0,
        para="",
        ambito=None,
        etiqueta="",
    ):
        recordatorio = servicios.crear(
            self.usuario,
            titulo=titulo,
            fecha_hora=self._fecha(fecha_hora),
            para=self._persona(para),
            detalle=detalle,
            tipo=tipo,
            avisar_antes_min=avisar_antes_min,
            etiqueta=etiqueta,
            ambito=ambito,
            ahora=self.ahora,
        )
        self.hubo_cambios = True
        return {"ok": True, **self._resumen(recordatorio)}

    def _listar_recordatorios(self, desde=None, hasta=None, incluir_completados=False, texto=""):
        recordatorios = servicios.listar(
            self.usuario,
            desde=self._fecha(desde) if desde else None,
            hasta=self._fecha(hasta) if hasta else None,
            incluir_completados=incluir_completados,
            etiqueta=texto,
        )
        return {"total": len(recordatorios), "recordatorios": [self._resumen(r) for r in recordatorios]}

    def _posponer_recordatorio(self, recordatorio_id, minutos=None, nueva_fecha_hora=None):
        recordatorio = servicios.posponer(
            self._obtener(recordatorio_id),
            minutos=minutos,
            nueva_fecha=self._fecha(nueva_fecha_hora) if nueva_fecha_hora else None,
            ahora=self.ahora,
        )
        self.hubo_cambios = True
        return {"ok": True, **self._resumen(recordatorio)}

    def _actualizar_recordatorio(
        self,
        recordatorio_id,
        titulo=None,
        fecha_hora=None,
        detalle=None,
        avisar_antes_min=None,
        etiqueta=None,
    ):
        recordatorio = servicios.actualizar(
            self._obtener(recordatorio_id),
            titulo=titulo,
            fecha_hora=self._fecha(fecha_hora) if fecha_hora else None,
            detalle=detalle,
            avisar_antes_min=avisar_antes_min,
            etiqueta=etiqueta,
            ahora=self.ahora,
        )
        self.hubo_cambios = True
        return {"ok": True, **self._resumen(recordatorio)}

    def _completar_recordatorio(self, recordatorio_id):
        recordatorio = servicios.completar(self._obtener(recordatorio_id), self.usuario, self.ahora)
        self.hubo_cambios = True
        return {"ok": True, **self._resumen(recordatorio)}

    def _cancelar_recordatorio(self, recordatorio_id):
        recordatorio = servicios.cancelar(self._obtener(recordatorio_id), self.usuario, self.ahora)
        self.hubo_cambios = True
        return {"ok": True, **self._resumen(recordatorio)}
