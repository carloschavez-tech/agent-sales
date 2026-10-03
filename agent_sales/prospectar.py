"""Prospección: encuentra negocios con buena reputación en Google pero sin página web.

Uso:
  python -m agent_sales.prospectar "spa de uñas, peluquerías" --ciudad "Chía, Cundinamarca"
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from .agent import estructurar, investigar_web
from .schema import _obj

ROOT = Path(__file__).resolve().parent.parent

SYSTEM = """\
Eres un investigador de prospectos B2B para una empresa que desarrolla software a medida, páginas \
web, sistemas de reservas y agentes de WhatsApp para negocios locales en Colombia.

Tu misión: encontrar negocios REALES del sector y ciudad indicados que tengan buena reputación o \
mucha demanda en Google (calificación alta y/o muchas reseñas) pero que NO tengan página web propia. \
Esos son los mejores prospectos: ya tienen clientes, pero dependen de Instagram/WhatsApp y pierden \
reservas y visibilidad.

Cómo buscar (usa muchas búsquedas distintas, en español):
- "<sector> en <ciudad>", "<sector> <ciudad> opiniones", "mejores <sector> <ciudad>", por barrios o \
  centros comerciales de la ciudad, y variantes del sector (ej. uñas: manicure, nail spa, nail bar; \
  peluquería: salón de belleza, barbería, estilista).
- Directorios y fichas: Google Maps, Páginas Amarillas, Cylex, Tupalo, Fresha, Booksy, Treatwell, \
  Facebook, Instagram, Tripadvisor, Waze.
- Para cada candidato, verifica si tiene web propia: busca "<nombre> <ciudad>" y mira si aparece un \
  dominio propio. Un perfil de Instagram, Facebook, Linktree, Fresha/Booksy o una ficha de directorio \
  NO cuenta como página web propia (anótalo aparte: es una señal útil).

Reglas de rigor:
- Solo negocios que realmente encontraste en una fuente. Cero inventos. Cada dato con su URL fuente.
- Calificación y número de reseñas: solo si los viste en una fuente; si no, escribe "no encontrado". \
  Indica de qué plataforma es la calificación (Google, Facebook, Fresha…).
- Verifica que el negocio esté en la ciudad pedida (no en la ciudad vecina) y que siga operando \
  (indicios de cierre → descártalo).
- Si no puedes comprobar si tiene web, márcalo "no verificado", no "no".
- Solo datos de contacto del NEGOCIO publicados por el negocio (teléfono, WhatsApp, Instagram). \
  Nada personal.

Entrega un informe con TODOS los candidatos encontrados (apunta a 15-25), con fuentes, y al final una \
nota de qué tan completa fue la búsqueda y qué no pudiste verificar."""

ESTRUCTURA_SYSTEM = """\
Convierte el informe de prospección en una lista estructurada. No agregues negocios ni datos que no \
estén en el informe. Asigna un puntaje de 1 a 10 como prospecto: más alto si NO tiene web, tiene \
buena calificación y muchas reseñas, y hay un canal de contacto claro. Ordena de mayor a menor puntaje. \
El ángulo de venta es una frase concreta para abrir la conversación con ESE negocio (ej. "142 reseñas \
de 4,9 en Google y reservas solo por WhatsApp: agenda en línea que confirma sola")."""

_S = {"type": "string"}
SCHEMA = _obj({
    "prospectos": {
        "type": "array",
        "items": _obj({
            "nombre": _S,
            "categoria": _S,
            "direccion_o_zona": _S,
            "calificacion": _S,
            "num_resenas": _S,
            "plataforma_resenas": _S,
            "tiene_web": {"type": "string", "enum": ["no", "sí", "no verificado"]},
            "web_url": _S,
            "instagram": _S,
            "telefono_whatsapp": _S,
            "otras_presencias": _S,
            "puntaje": {"type": "integer"},
            "por_que": _S,
            "angulo_de_venta": _S,
            "fuentes": {"type": "array", "items": _S},
        }),
    },
    "notas": _S,
})

COLUMNAS = ["puntaje", "nombre", "categoria", "direccion_o_zona", "calificacion", "num_resenas",
            "plataforma_resenas", "tiene_web", "web_url", "instagram", "telefono_whatsapp",
            "otras_presencias", "por_que", "angulo_de_venta", "fuentes"]


def main() -> None:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(prog="agent_sales.prospectar",
                                 description="Busca negocios bien calificados sin página web.")
    ap.add_argument("sector", help='Ej. "spa de uñas, peluquerías"')
    ap.add_argument("--ciudad", required=True, help='Ej. "Chía, Cundinamarca"')
    ap.add_argument("--incluir-con-web", action="store_true",
                    help="No descartar los que ya tienen web (por defecto se descartan)")
    ap.add_argument("--out", default=str(ROOT / "salidas"))
    args = ap.parse_args()

    client = anthropic.Anthropic()
    print(f"🗺️  Prospectando {args.sector} en {args.ciudad}…", file=sys.stderr)
    informe = investigar_web(
        client, SYSTEM, f"Sector: {args.sector}\nCiudad: {args.ciudad}", max_uses=30)

    print("📋 Armando la lista…", file=sys.stderr)
    data = estructurar(client, ESTRUCTURA_SYSTEM,
                       f"<informe>\n{informe}\n</informe>", SCHEMA)
    prospectos = data["prospectos"]
    if not args.incluir_con_web:
        prospectos = [p for p in prospectos if p["tiene_web"] != "sí"]
    prospectos.sort(key=lambda p: p["puntaje"], reverse=True)

    from .__main__ import _slug  # noqa: PLC0415 (evita duplicar la función)
    out = Path(args.out) / f"{date.today():%Y-%m-%d}_prospectos_{_slug(args.sector)}_{_slug(args.ciudad)}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "informe.md").write_text(informe, encoding="utf-8")
    (out / "prospectos.json").write_text(
        json.dumps({**data, "prospectos": prospectos}, ensure_ascii=False, indent=2), encoding="utf-8")
    # utf-8-sig para que Excel abra bien las tildes
    with open(out / "prospectos.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        for p in prospectos:
            w.writerow({**p, "fuentes": " | ".join(p["fuentes"])})

    print(f"\n✅ {len(prospectos)} prospectos → {out}\n", file=sys.stderr)
    for p in prospectos:
        print(f'{p["puntaje"]:>2}/10  {p["nombre"]} · {p["categoria"]} · ⭐ {p["calificacion"]} '
              f'({p["num_resenas"]} reseñas) · web: {p["tiene_web"]} · {p["telefono_whatsapp"] or p["instagram"]}')
    print(f'\nNotas: {data["notas"]}')


if __name__ == "__main__":
    main()
