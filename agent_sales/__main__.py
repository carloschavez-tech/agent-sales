"""CLI: python -m agent_sales <url o descripción del negocio> [--contexto "..."]"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

from . import render
from .agent import investigar, proponer

ROOT = Path(__file__).resolve().parent.parent


def _slug(texto: str) -> str:
    texto = re.sub(r"^https?://(www\.)?", "", texto.strip().lower())
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:50] or "prospecto"


def main() -> None:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(
        prog="agent_sales",
        description="Analiza un prospecto y genera propuesta de software a medida + correo en frío.",
    )
    ap.add_argument("prospecto", help='URL del sitio, o descripción si no tiene web: '
                                      '"Panadería La Espiga, Medellín, IG @laespiga"')
    ap.add_argument("--contexto", help="Lo que ya sabes del cliente (reunión, referido, dolor mencionado…)")
    ap.add_argument("--config", default=str(ROOT / "config" / "empresa.yaml"))
    ap.add_argument("--out", default=str(ROOT / "salidas"))
    args = ap.parse_args()

    empresa_yaml = Path(args.config).read_text(encoding="utf-8")
    empresa = yaml.safe_load(empresa_yaml)
    if "TODO" in empresa_yaml:
        print("⚠️  config/empresa.yaml todavía tiene campos TODO; llénalos para propuestas más fuertes.\n",
              file=sys.stderr)

    client = anthropic.Anthropic()

    print(f"🕵️  Investigando: {args.prospecto}", file=sys.stderr)
    research = investigar(client, args.prospecto, args.contexto)

    print("🧠 Diseñando propuesta y correo…", file=sys.stderr)
    data = proponer(client, research, empresa_yaml, args.prospecto)

    out = Path(args.out) / f"{date.today():%Y-%m-%d}_{_slug(data['empresa']['nombre'] or args.prospecto)}"
    out.mkdir(parents=True, exist_ok=True)
    archivos = {
        "correo.html": render.correo_html(data, empresa),
        "correo.txt": render.correo_txt(data, empresa),
        "propuesta.html": render.propuesta_html(data, empresa),
        "propuesta.md": render.propuesta_md(data, empresa),
        "seguimiento.md": render.seguimiento_md(data),
        "investigacion.md": research,
        "datos.json": json.dumps(data, ensure_ascii=False, indent=2),
    }
    for nombre, contenido in archivos.items():
        (out / nombre).write_text(contenido, encoding="utf-8")

    c = data["correo"]
    print(f"\n✅ Listo → {out}\n", file=sys.stderr)
    print(f"Asunto: {c['asuntos'][0]}\n")
    print(render.correo_txt(data, empresa).split("────────────────────────────────────────\n\n", 1)[1])


if __name__ == "__main__":
    main()
