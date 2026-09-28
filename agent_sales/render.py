"""Convierte el JSON del agente en entregables: correo HTML/TXT, propuesta HTML/MD, seguimiento."""

from __future__ import annotations

from html import escape

ACCENT = "#4F46E5"


def _paras_html(texto: str, style: str) -> str:
    return "".join(
        f'<p style="{style}">{escape(p.strip())}</p>'
        for p in texto.split("\n")
        if p.strip()
    )


def _firma_txt(empresa: dict) -> str:
    r = empresa.get("remitente", {})
    lineas = [r.get("nombre", ""), f'{r.get("cargo", "")} · {empresa.get("nombre", "")}',
              r.get("telefono", ""), empresa.get("sitio_web", "")]
    return "\n".join(l for l in lineas if l and "TODO" not in l)


def _cta_url(empresa: dict) -> str:
    r = empresa.get("remitente", {})
    for key in ("agenda", "whatsapp"):
        url = r.get(key, "")
        if url and "TODO" not in url:
            return url
    return f'mailto:{r.get("email", "")}'


# ───────────────────────────── CORREO ─────────────────────────────

def correo_txt(data: dict, empresa: dict) -> str:
    c = data["correo"]
    asuntos = "\n".join(f"  {i}. {a}" for i, a in enumerate(c["asuntos"], 1))
    return (
        f"ASUNTOS (elige uno o haz A/B test):\n{asuntos}\n\n"
        f"────────────────────────────────────────\n\n"
        f'{c["saludo"]}\n\n{c["cuerpo"].strip()}\n\n'
        f'👉 {c["cta_texto_boton"]}: {_cta_url(empresa)}\n\n'
        f"{_firma_txt(empresa)}\n\n"
        f'P.D. {c["posdata"]}\n'
    )


def correo_html(data: dict, empresa: dict) -> str:
    """Correo con mini-diagnóstico visual. Tablas + estilos inline para que se vea bien en Gmail/Outlook."""
    c = data["correo"]
    r = empresa.get("remitente", {})
    p_style = "margin:0 0 14px;font-size:15px;line-height:1.6;color:#1f2937;"

    hallazgos = data["diagnostico"]["hallazgos"][:3]
    filas = "".join(
        f'<tr><td style="padding:8px 0;border-top:1px solid #e5e7eb;font-size:14px;color:#374151;">'
        f'<strong style="color:#111827;">{escape(h["hallazgo"])}</strong><br>'
        f'<span style="color:#6b7280;">{escape(h["impacto_negocio"])}</span></td></tr>'
        for h in hallazgos
    )
    diag = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;margin:6px 0 20px;">'
        f'<tr><td style="padding:16px 18px;">'
        f'<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:{ACCENT};'
        f'font-weight:700;margin-bottom:6px;">Lo que vimos en {escape(data["empresa"]["nombre"])}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{filas}</table>'
        f"</td></tr></table>"
    ) if hallazgos else ""

    firma = "<br>".join(escape(l) for l in _firma_txt(empresa).split("\n"))
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(c["asuntos"][0] if c["asuntos"] else "")}</title></head>
<body style="margin:0;padding:0;background:#ffffff;">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(c["preheader"])}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:580px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
<tr><td>
<p style="{p_style}">{escape(c["saludo"])}</p>
{_paras_html(c["cuerpo"], p_style)}
{diag}
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 22px;"><tr>
<td style="background:{ACCENT};border-radius:8px;">
<a href="{escape(_cta_url(empresa))}" style="display:inline-block;padding:12px 22px;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;">{escape(c["cta_texto_boton"])} →</a>
</td></tr></table>
<p style="margin:0 0 18px;font-size:14px;line-height:1.5;color:#374151;">{firma}</p>
<p style="margin:0;font-size:14px;line-height:1.6;color:#4b5563;"><strong>P.D.</strong> {escape(c["posdata"])}</p>
<p style="margin:26px 0 0;font-size:11px;color:#9ca3af;">Si no es de tu interés, responde "no" y no te vuelvo a escribir. · {escape(r.get("email", ""))}</p>
</td></tr></table>
</td></tr></table>
</body></html>
"""


# ──────────────────────────── PROPUESTA ────────────────────────────

def propuesta_md(data: dict, empresa: dict) -> str:
    e, d, p = data["empresa"], data["diagnostico"], data["propuesta"]
    out = [
        f'# {p["nombre_proyecto"]}',
        f'**Propuesta para {e["nombre"]}** · {e["sector"]} · {e["ubicacion"]}  ',
        f'Preparada por {empresa.get("nombre", "")}\n',
        f'## Objetivo\n{p["objetivo"]}\n',
        f'## Diagnóstico (madurez digital: {d["madurez_digital"]})',
    ]
    out += [f'- **{h["hallazgo"]}** — {h["impacto_negocio"]}  \n  _Evidencia: {h["evidencia"]}_'
            for h in d["hallazgos"]]
    if d["competidor_referencia"]:
        out.append(f'\n> Referencia de mercado: {d["competidor_referencia"]}')
    out.append("\n## Oportunidades")
    for i, o in enumerate(data["oportunidades"], 1):
        out.append(f'### {i}. {o["titulo"]} (prioridad {o["prioridad"]})\n'
                   f'- **Dolor:** {o["dolor"]}\n- **Solución:** {o["solucion"]}\n'
                   f'- **Beneficio estimado:** {o["beneficio_estimado"]}\n')
    out.append("## Alcance del MVP")
    out += [f"- {a}" for a in p["alcance_mvp"]]
    out.append("\n## Plan de trabajo")
    for f in p["fases"]:
        out.append(f'**{f["fase"]}** ({f["duracion"]})')
        out += [f"- {x}" for x in f["entregables"]]
    out += [
        f'\n## Tecnología\n{p["tecnologia"]}\n',
        f'## Inversión estimada\n{p["inversion_estimada"]}\n',
        f'## Retorno esperado\n{p["retorno_esperado"]}\n',
        "## Siguientes pasos",
    ]
    out += [f"{i}. {s}" for i, s in enumerate(p["siguientes_pasos"], 1)]
    return "\n".join(out) + "\n"


def propuesta_html(data: dict, empresa: dict) -> str:
    """One-pager imprimible (Ctrl+P → Guardar como PDF)."""
    e, d, p = data["empresa"], data["diagnostico"], data["propuesta"]
    li = lambda xs: "".join(f"<li>{escape(x)}</li>" for x in xs)  # noqa: E731
    hallazgos = "".join(
        f'<div class="card"><h4>{escape(h["hallazgo"])}</h4><p>{escape(h["impacto_negocio"])}</p>'
        f'<small>Evidencia: {escape(h["evidencia"])}</small></div>'
        for h in d["hallazgos"]
    )
    opps = "".join(
        f'<div class="opp"><span class="tag {escape(o["prioridad"])}">{escape(o["prioridad"])}</span>'
        f'<h4>{i}. {escape(o["titulo"])}</h4>'
        f'<p><b>Dolor:</b> {escape(o["dolor"])}</p><p><b>Solución:</b> {escape(o["solucion"])}</p>'
        f'<p class="ben">↗ {escape(o["beneficio_estimado"])}</p></div>'
        for i, o in enumerate(data["oportunidades"], 1)
    )
    fases = "".join(
        f'<div class="fase"><div class="dur">{escape(f["duracion"])}</div><h4>{escape(f["fase"])}</h4>'
        f'<ul>{li(f["entregables"])}</ul></div>'
        for f in p["fases"]
    )
    r = empresa.get("remitente", {})
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(p["nombre_proyecto"])} · {escape(e["nombre"])}</title>
<style>
:root{{--ac:{ACCENT};--ink:#111827;--mut:#6b7280;--line:#e5e7eb;--bg:#fff;--soft:#f9fafb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:860px;margin:0 auto;padding:48px 24px}}
header{{border-bottom:3px solid var(--ac);padding-bottom:20px;margin-bottom:28px}}
.kicker{{color:var(--ac);font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:12px}}
h1{{font-size:32px;line-height:1.2;margin:6px 0 8px}}h2{{font-size:20px;margin:36px 0 12px}}h4{{margin:0 0 6px}}
.meta{{color:var(--mut)}}.obj{{font-size:17px;background:var(--soft);border-left:4px solid var(--ac);padding:14px 18px;border-radius:6px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}
.card,.opp,.fase{{border:1px solid var(--line);border-radius:10px;padding:16px}}
.card p,.opp p{{margin:0 0 6px}}.card small{{color:var(--mut)}}
.ben{{color:#047857;font-weight:600}}.tag{{float:right;font-size:11px;text-transform:uppercase;padding:2px 8px;border-radius:99px;background:var(--soft);border:1px solid var(--line)}}
.tag.alta{{background:#fef2f2;color:#b91c1c;border-color:#fecaca}}
.opp{{margin-bottom:12px}}.dur{{color:var(--ac);font-weight:700;font-size:13px}}
.inv{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.inv div{{background:var(--soft);border-radius:10px;padding:16px}}
footer{{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);color:var(--mut);font-size:14px}}
@media (max-width:600px){{.inv{{grid-template-columns:1fr}}h1{{font-size:26px}}}}
@media print{{.wrap{{padding:0}}h2{{break-after:avoid}}.card,.opp,.fase{{break-inside:avoid}}}}
</style></head><body><div class="wrap">
<header><div class="kicker">Propuesta de software a medida · {escape(empresa.get("nombre", ""))}</div>
<h1>{escape(p["nombre_proyecto"])}</h1>
<div class="meta">Para <b>{escape(e["nombre"])}</b> · {escape(e["sector"])} · {escape(e["ubicacion"])}</div></header>
<p class="obj">{escape(p["objetivo"])}</p>
<h2>Lo que encontramos <span class="meta" style="font-size:14px;font-weight:400">· madurez digital {escape(d["madurez_digital"])}</span></h2>
<div class="grid">{hallazgos}</div>
{f'<p class="meta">Referencia de mercado: {escape(d["competidor_referencia"])}</p>' if d["competidor_referencia"] else ""}
<h2>Oportunidades</h2>{opps}
<h2>Alcance del MVP</h2><ul>{li(p["alcance_mvp"])}</ul>
<h2>Plan de trabajo</h2><div class="grid">{fases}</div>
<h2>Inversión y retorno</h2>
<div class="inv"><div><b>Inversión estimada</b><br>{escape(p["inversion_estimada"])}</div>
<div><b>Retorno esperado</b><br>{escape(p["retorno_esperado"])}</div></div>
<p class="meta"><b>Tecnología:</b> {escape(p["tecnologia"])}</p>
<h2>Siguientes pasos</h2><ol>{li(p["siguientes_pasos"])}</ol>
<footer>{escape(r.get("nombre", ""))} · {escape(r.get("email", ""))} · {escape(empresa.get("nombre", ""))}</footer>
</div></body></html>
"""


def seguimiento_md(data: dict) -> str:
    out = ["# Secuencia de seguimiento\n"]
    for s in data["seguimientos"]:
        out.append(f'## Día {s["dia"]} · {s["canal"]}\n{s["mensaje"]}\n')
    out.append(f'## WhatsApp (primer contacto)\n{data["mensaje_whatsapp"]}\n')
    out.append(f'## LinkedIn (nota de conexión)\n{data["mensaje_linkedin"]}\n')
    c = data["contacto"]
    out.append(f'## A quién escribirle\n- Decisor probable: {c["rol_decisor"]}\n'
               f'- Email público: {c["email_publico"] or "—"}\n'
               f'- Teléfono público: {c["telefono_publico"] or "—"}\n'
               f'- Mejor canal: {c["mejor_canal"]}\n')
    return "\n".join(out)
