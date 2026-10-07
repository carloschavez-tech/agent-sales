"""CLI del agente de trading. El agente da las señales; tú ejecutas y registras.

  python -m agent_trading senal                 # ¿hay entrada ahora? (LONG/SHORT, stop, TP1, TP2, cantidad)
  python -m agent_trading abrir --precio 61234  # registraste la entrada de la última señal
  python -m agent_trading cerrar --precio 61800 [--cantidad 0.001]   # salida total o parcial (TP1)
  python -m agent_trading estado                # PnL de hoy, reparto 60/40, fondo del agente, apagado
  python -m agent_trading backtest --dias 90    # ¿la estrategia gana en el pasado con estas reglas?
  python -m agent_trading exportar --dias 365   # guarda velas en datos/ para analizarlas offline
  python -m agent_trading plan                  # cuánto capital hace realista la meta diaria
  python -m agent_trading solicitar --monto 5 --motivo "..."   # el agente pide de su fondo
  python -m agent_trading aprobar 1 | rechazar 1
  python -m agent_trading retirar --monto 20    # sacas parte de tu 60 %
  python -m agent_trading reactivar --confirmo REACTIVAR [--perdonar-deuda]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import datos
from .backtest import simular
from .estrategia import Analisis, tamano
from .libro import Libro

ROOT = Path(__file__).resolve().parent.parent


def _cfg(ruta: str) -> dict:
    return yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))


def _libro(cfg: dict, out: str) -> Libro:
    return Libro(Path(out) / cfg["modo"] / "libro.json", cfg)


def _fmt(x: float) -> str:
    return f"{x:,.2f}" if abs(x) >= 100 else f"{x:.4f}"


def cmd_senal(cfg: dict, lib: Libro, args) -> None:
    if cfg["modo"] == "real":
        ok, detalle = lib.apto_para_real()
        if not ok and not args.forzar:
            sys.exit(f"⛔ Modo real bloqueado: {detalle}. Practica en papel primero (o --forzar).")
    if (motivo := lib.bloqueo()):
        sys.exit(motivo)
    simbolos = [args.simbolo] if args.simbolo else list(cfg["simbolos"])
    riesgo = lib.riesgo_disponible()
    con_datos = 0
    for sim in simbolos:
        try:
            v15 = datos.velas(cfg["exchange"], sim, cfg["temporalidad"], 1000)
        except Exception as e:  # red caída, símbolo inválido…
            print(f"⚠️  {sim}: no pude traer datos ({e})")
            continue
        con_datos += 1
        an = Analisis(sim, v15)
        s = an.evaluar(len(v15) - 1)
        print(an.contexto())
        if s is None:
            continue
        paso = cfg["simbolos"][sim]["paso_cantidad"]
        qty, riesgo_real = tamano(s, lib.capital(), riesgo, cfg["comision_pct"],
                                  cfg["max_apalancamiento"], paso)
        if qty <= 0:
            print(f"   Señal {s.lado}, pero con {riesgo:.2f} USD de riesgo no alcanza la cantidad mínima.")
            continue
        vence = datetime.fromtimestamp((s.vela_t + 2 * datos.MS["15m"]) / 1000, timezone.utc).astimezone(lib.tz)
        lev = qty * s.entrada / lib.capital()
        print(f"""
══════════ SEÑAL {s.lado} {sim} ══════════
  Entrada : {_fmt(s.entrada)}   (límite; válida hasta {vence:%H:%M}, si no entra se cancela)
  Stop    : {_fmt(s.stop)}   ← ponlo en el exchange APENAS entres
  TP1     : {_fmt(s.tp1)}   cierra la mitad y sube el stop a la entrada
  TP2     : {_fmt(s.tp2)}   cierra el resto
  Cantidad: {qty} {sim.replace('USDT', '')}   (≈ {qty * s.entrada:,.0f} USD, apalancamiento {lev:.1f}x)
  Riesgo  : {riesgo_real:.2f} USD si toca el stop · ganancia a TP2 ≈ {qty * s.r * 1.5:.2f} USD
  Si en 4 h no tocó stop ni TP2: cierra a mercado.
  Motivo  : {s.motivo}

  Cuando entres:  python -m agent_trading abrir --precio <precio real>""")
        lib.d["ultima_senal"] = {**s.dict(), "cantidad": qty}
        lib.guardar()
        return
    if not con_datos:
        sys.exit("\n⛔ Sin datos del mercado: revisa tu conexión o cambia `exchange` en config/trading.yaml.")
    print("\nSin señal ahora. No forzar entradas: vuelve a consultar en la próxima vela de 15 min.")


def cmd_abrir(cfg: dict, lib: Libro, args) -> None:
    if (motivo := lib.bloqueo()):
        sys.exit(motivo)
    s = lib.d.get("ultima_senal")
    if not s and not (args.simbolo and args.lado and args.stop):
        sys.exit("No hay señal guardada: usa --simbolo --lado --stop (y --cantidad).")
    s = s or {}
    op = lib.abrir(args.simbolo or s["simbolo"], (args.lado or s["lado"]).upper(), args.precio,
                   args.cantidad or s["cantidad"], args.stop or s["stop"],
                   s.get("tp1") if not args.simbolo else None, s.get("tp2") if not args.simbolo else None)
    lib.d["ultima_senal"] = None
    lib.guardar()
    print(f"✅ Operación #{op['id']} abierta: {op['lado']} {op['cantidad']} {op['simbolo']} @ {op['entrada']}"
          f" · stop {op['stop']}")


def cmd_cerrar(cfg: dict, lib: Libro, args) -> None:
    op = lib.cerrar(args.id, args.precio, args.cantidad)
    lib.guardar()
    if op["estado"] == "abierta":
        print(f"Parcial registrado. Stop de #{op['id']} movido a la entrada ({op['stop']}). Muévelo en el exchange.")
        return
    print(f"{'🟢' if op['pnl'] > 0 else '🔴'} #{op['id']} cerrada: {op['pnl']:+.2f} USD "
          f"(comisiones {op['comisiones']:.2f})")
    cmd_estado(cfg, lib, args)


def cmd_estado(cfg: dict, lib: Libro, args) -> None:
    hoy = lib.hoy()
    pnl = lib.pnl_dia(hoy)
    rep = cfg["reparto"]
    print(f"""
── {cfg['modo'].upper()} · {hoy} ─────────────────────────
  Capital           : {lib.capital():,.2f} USD (máximo {lib.d['pico_capital']:,.2f})
  Hoy               : {pnl:+.2f} / meta {cfg['meta_diaria']} USD · {lib.operaciones_dia(hoy)} operaciones
  Si cierras así    : tú {max(pnl, 0) * rep['usuario']:.2f} · agente {max(pnl, 0) * rep['agente'] if pnl > 0 else pnl:.2f}
  Tu ganancia acum. : {lib.d['ganancia_usuario']:,.2f} USD (retirado {lib.d['retiros_usuario']:,.2f})
  Fondo del agente  : {lib.d['fondo_agente']:,.2f} USD (gastado {lib.d['gastos_agente']:,.2f}; se apaga en −{cfg['limite_deuda_agente']})
  Estado            : {lib.bloqueo() or '🟢 puede operar'}""")
    for o in lib.abiertas():
        print(f"  Abierta #{o['id']}: {o['lado']} {o['cantidad']} {o['simbolo']} @ {o['entrada']} "
              f"· stop {o['stop']} · TP1 {o['tp1']} · TP2 {o['tp2']}")
    pend = [s for s in lib.d["solicitudes"] if s["estado"] == "pendiente"]
    for s in pend:
        print(f"  Solicitud pendiente #{s['id']}: {s['monto']} USD — {s['motivo']}")
    ultimos = sorted(lib.d["dias"].items())[-7:]
    if ultimos:
        print("  Últimos días:", " · ".join(f"{d[5:]} {v['pnl']:+.2f}" for d, v in ultimos))
    if cfg["modo"] == "papel":
        print(f"  Para pasar a real: {lib.apto_para_real()[1]}")


def _velas_backtest(cfg: dict, sim: str, dias: int, carpeta: str | None) -> list:
    n = dias * 96 + 220 * 4
    if carpeta:
        return datos.cargar_csv(Path(carpeta) / f"{sim}_{cfg['temporalidad']}.csv")[-n:]
    return datos.velas(cfg["exchange"], sim, cfg["temporalidad"], n)


def cmd_backtest(cfg: dict, lib: Libro, args) -> None:
    simbolos = [args.simbolo] if args.simbolo else list(cfg["simbolos"])
    print(f"Backtest {args.dias} días · capital {cfg['capital_inicial']} · riesgo "
          f"{cfg['riesgo_por_operacion_pct']} % · comisión {cfg['comision_pct']} %/lado\n")
    for sim in simbolos:
        try:
            v15 = _velas_backtest(cfg, sim, args.dias, args.datos)
        except Exception as e:
            print(f"⚠️  {sim}: no pude traer datos ({e})")
            continue
        r = simular(sim, v15, cfg, cfg["simbolos"][sim]["paso_cantidad"])
        ap = r["apagados"]
        print(f"""{sim}: {r['operaciones']} operaciones en {r['dias']} días · acierto {r['acierto_pct']:.0f} % · factor {r['factor_beneficio']:.2f}
   PnL {r['pnl_total']:+.2f} USD ({r['pnl_por_dia']:+.2f}/día) · días con meta {r['dias_meta']} · días en pérdida {r['dias_perdida']}
   Para ti {r['para_usuario']:.2f} · fondo agente {r['fondo_agente']:+.2f} · {f'⛔ se habría apagado {len(ap)} veces ({", ".join(ap[:3])}{"…" if len(ap) > 3 else ""})' if ap else 'no se apagó'}
""")
    print("Factor < 1.2 o apagado = la estrategia NO tiene ventaja con estas reglas; no la uses con dinero real.")


def cmd_exportar(cfg: dict, lib: Libro, args) -> None:
    carpeta = ROOT / "datos"
    carpeta.mkdir(exist_ok=True)
    for sim in cfg["simbolos"]:
        vs = datos.velas(cfg["exchange"], sim, cfg["temporalidad"], args.dias * 96)
        ruta = carpeta / f"{sim}_{cfg['temporalidad']}.csv"
        datos.guardar_csv(ruta, vs)
        print(f"✅ {ruta.relative_to(ROOT)}: {len(vs)} velas")
    print("\nPara que el agente las analice: git add datos && git commit -m 'Velas' && git push")


def cmd_plan(cfg: dict, lib: Libro, args) -> None:
    meta = cfg["meta_diaria"]
    print(f"Capital necesario para ganar {meta} USD/día en promedio (≈ 21 días hábiles/mes):\n")
    for pct, nota in [(0.1, "ya es excelente y sostenible para pocos"),
                      (0.25, "muy agresivo; pocos profesionales lo sostienen"),
                      (0.5, "excepcional; casi nadie lo mantiene un año"),
                      (1.0, "irreal de forma sostenida; quien lo promete miente o apuesta")]:
        print(f"  {pct:>4} %/día → {meta / (pct / 100):>8,.0f} USD de capital · {nota}")
    print(f"\nTu capital: {lib.capital():,.0f} USD → la meta exige {100 * meta / lib.capital():.2f} %/día."
          "\nCon poco capital la meta empuja a sobre-apalancarse; las reglas de riesgo no lo permiten a propósito.")


def main() -> None:
    ap = argparse.ArgumentParser(prog="agent_trading", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "trading.yaml"))
    ap.add_argument("--out", default=str(ROOT / "salidas" / "trading"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("senal")
    p.add_argument("--simbolo")
    p.add_argument("--forzar", action="store_true")
    p = sub.add_parser("abrir")
    p.add_argument("--precio", type=float, required=True)
    p.add_argument("--cantidad", type=float)
    p.add_argument("--simbolo")
    p.add_argument("--lado", choices=["long", "short", "LONG", "SHORT"])
    p.add_argument("--stop", type=float)
    p = sub.add_parser("cerrar")
    p.add_argument("--precio", type=float, required=True)
    p.add_argument("--cantidad", type=float)
    p.add_argument("--id", type=int)
    sub.add_parser("estado")
    sub.add_parser("plan")
    p = sub.add_parser("backtest")
    p.add_argument("--dias", type=int, default=90)
    p.add_argument("--simbolo")
    p.add_argument("--datos", help="carpeta con CSV de `exportar` (en vez de bajar del exchange)")
    p = sub.add_parser("exportar")
    p.add_argument("--dias", type=int, default=365)
    p = sub.add_parser("solicitar")
    p.add_argument("--monto", type=float, required=True)
    p.add_argument("--motivo", required=True)
    for nombre in ("aprobar", "rechazar"):
        p = sub.add_parser(nombre)
        p.add_argument("id", type=int)
        p.add_argument("--nota", default="")
    p = sub.add_parser("retirar")
    p.add_argument("--monto", type=float, required=True)
    p = sub.add_parser("reactivar")
    p.add_argument("--confirmo", required=True)
    p.add_argument("--perdonar-deuda", action="store_true")
    args = ap.parse_args()

    cfg = _cfg(args.config)
    lib = _libro(cfg, args.out)
    try:
        if args.cmd in ("aprobar", "rechazar"):
            s = lib.resolver(args.id, args.cmd == "aprobar", args.nota)
            lib.guardar()
            print(f"Solicitud #{s['id']} {s['estado']}. Fondo del agente: {lib.d['fondo_agente']:.2f} USD")
        elif args.cmd == "solicitar":
            s = lib.solicitar(args.monto, args.motivo)
            lib.guardar()
            print(f"Solicitud #{s['id']} registrada ({args.monto} USD). Hablémoslo; luego aprobar/rechazar.")
        elif args.cmd == "retirar":
            lib.retirar(args.monto)
            lib.guardar()
            print(f"Retiro registrado. Tu ganancia disponible: {lib.d['ganancia_usuario']:.2f} USD")
        elif args.cmd == "reactivar":
            if not lib.d["apagado"]:
                sys.exit("El agente no está apagado.")
            if args.confirmo != "REACTIVAR":
                sys.exit('Escribe exactamente --confirmo REACTIVAR')
            lib.reactivar(args.perdonar_deuda)
            lib.guardar()
            print("Agente reactivado.")
        else:
            {"senal": cmd_senal, "abrir": cmd_abrir, "cerrar": cmd_cerrar, "estado": cmd_estado,
             "backtest": cmd_backtest, "plan": cmd_plan, "exportar": cmd_exportar}[args.cmd](cfg, lib, args)
    except ValueError as e:
        sys.exit(f"⚠️  {e}")


if __name__ == "__main__":
    main()
