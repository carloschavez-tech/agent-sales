"""Esquema JSON de la salida estructurada (propuesta + correo + seguimientos)."""


def _obj(props: dict) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


_S = {"type": "string"}
_LIST_S = {"type": "array", "items": _S}

PROPOSAL_SCHEMA = _obj({
    "empresa": _obj({
        "nombre": _S,
        "sector": _S,
        "ubicacion": _S,
        "resumen": _S,
        "tiene_sitio_web": {"type": "boolean"},
    }),
    "diagnostico": _obj({
        "madurez_digital": {
            "type": "string",
            "enum": ["muy baja", "baja", "media", "alta"],
        },
        "hallazgos": {
            "type": "array",
            "items": _obj({"hallazgo": _S, "evidencia": _S, "impacto_negocio": _S}),
        },
        "competidor_referencia": _S,
    }),
    "oportunidades": {
        "type": "array",
        "items": _obj({
            "titulo": _S,
            "dolor": _S,
            "solucion": _S,
            "beneficio_estimado": _S,
            "prioridad": {"type": "string", "enum": ["alta", "media", "baja"]},
        }),
    },
    "propuesta": _obj({
        "nombre_proyecto": _S,
        "objetivo": _S,
        "alcance_mvp": _LIST_S,
        "fases": {
            "type": "array",
            "items": _obj({"fase": _S, "duracion": _S, "entregables": _LIST_S}),
        },
        "tecnologia": _S,
        "inversion_estimada": _S,
        "retorno_esperado": _S,
        "siguientes_pasos": _LIST_S,
    }),
    "contacto": _obj({
        "rol_decisor": _S,
        "email_publico": _S,
        "telefono_publico": _S,
        "mejor_canal": _S,
    }),
    "correo": _obj({
        "asuntos": _LIST_S,
        "preheader": _S,
        "saludo": _S,
        "cuerpo": _S,
        "cta_texto_boton": _S,
        "posdata": _S,
    }),
    "seguimientos": {
        "type": "array",
        "items": _obj({"dia": {"type": "integer"}, "canal": _S, "mensaje": _S}),
    },
    "mensaje_whatsapp": _S,
    "mensaje_linkedin": _S,
})
