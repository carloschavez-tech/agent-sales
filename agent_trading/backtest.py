"""Backtest con las mismas reglas del trato: meta diaria, pérdida máxima, reparto y apagado.

Supuestos conservadores: entrada al cierre de la vela de señal con comisión taker; si en una
misma vela se tocan stop y objetivo, cuenta como stop.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .datos import Vela
from .estrategia import VELAS_MAX, Analisis, tamano


def simular(simbolo: str, v15: list[Vela], cfg: dict, paso: float) -> dict:
    tz = ZoneInfo(cfg.get("zona_horaria", "UTC"))
    dia_de = [datetime.fromtimestamp(v.t / 1000, timezone.utc).astimezone(tz).strftime("%Y-%m-%d")
              for v in v15]
    an = Analisis(simbolo, v15)
    com = cfg["comision_pct"] / 100
    capital = pico = float(cfg["capital_inicial"])
    fondo = usuario = 0.0
    pnl_dia: dict[str, float] = defaultdict(float)
    ops_dia: dict[str, int] = defaultdict(int)
    trades: list[dict] = []
    apagado = None
    dia_liquidado = None

    def liquidar(dia: str) -> None:
        nonlocal fondo, usuario
        p = pnl_dia.get(dia, 0.0)
        if p > 0:
            usuario += p * cfg["reparto"]["usuario"]
            fondo += p * cfg["reparto"]["agente"]
        else:
            fondo += p

    i = 220 * 4  # calentamiento: EMA200 de 1h
    while i < len(v15) - 1 and not apagado:
        dia = dia_de[i]
        if dia_liquidado is not None and dia != dia_liquidado:
            liquidar(dia_liquidado)
        dia_liquidado = dia
        p = pnl_dia[dia]
        if (p <= -cfg["perdida_max_diaria"] or ops_dia[dia] >= cfg["max_operaciones_dia"]
                or (cfg.get("parar_al_llegar_meta", True) and p >= cfg["meta_diaria"])):
            i += 1
            continue
        s = an.evaluar(i)
        if s is None:
            i += 1
            continue
        riesgo = max(0.0, min(capital * cfg["riesgo_por_operacion_pct"] / 100,
                              cfg["perdida_max_diaria"] + p))
        qty, _ = tamano(s, capital, riesgo, cfg["comision_pct"], cfg["max_apalancamiento"], paso)
        if qty <= 0:
            i += 1
            continue
        signo = 1 if s.lado == "LONG" else -1
        stop, resto, bruto, salidas_val = s.stop, qty, 0.0, 0.0
        medio = round(qty / 2 / paso) * paso if qty >= 2 * paso else 0.0
        tp1_hecho = False
        j = i + 1
        while j < len(v15) and resto > 0:
            v = v15[j]
            toca_stop = v.l <= stop if signo == 1 else v.h >= stop
            toca_tp1 = v.h >= s.tp1 if signo == 1 else v.l <= s.tp1
            toca_tp2 = v.h >= s.tp2 if signo == 1 else v.l <= s.tp2
            if toca_stop:
                salida, cant = stop, resto
            elif toca_tp2:
                salida, cant = s.tp2, resto
            elif toca_tp1 and not tp1_hecho and medio > 0:
                salida, cant = s.tp1, medio
                tp1_hecho, stop = True, s.entrada
            elif j - i >= VELAS_MAX:
                salida, cant = v.c, resto
            else:
                j += 1
                continue
            bruto += signo * (salida - s.entrada) * cant
            salidas_val += salida * cant
            resto = round(resto - cant, 10)
            if resto > 0:
                j += 1
        pnl = bruto - (s.entrada * qty + salidas_val) * com
        dia_cierre = dia_de[min(j, len(v15) - 1)]
        pnl_dia[dia_cierre] += pnl
        ops_dia[dia] += 1
        capital += pnl
        pico = max(pico, capital)
        trades.append({"dia": dia, "lado": s.lado, "pnl": pnl})
        fondo_hoy = fondo + min(pnl_dia[dia_cierre], 0.0)
        if fondo_hoy <= -cfg["limite_deuda_agente"]:
            apagado = f"{dia_cierre}: deuda del agente {fondo_hoy:.2f} USD"
        elif capital <= pico * (1 - cfg["drawdown_max_pct"] / 100):
            apagado = f"{dia_cierre}: drawdown {100 * (1 - capital / pico):.1f} %"
        i = j + 1
    if dia_liquidado and not apagado:
        liquidar(dia_liquidado)

    dias = sorted(set(dia_de[220 * 4:]))
    ganadas = [t for t in trades if t["pnl"] > 0]
    perdidas = [t for t in trades if t["pnl"] <= 0]
    gan_total = sum(t["pnl"] for t in ganadas)
    per_total = -sum(t["pnl"] for t in perdidas)
    return {
        "simbolo": simbolo,
        "dias": len(dias),
        "operaciones": len(trades),
        "acierto_pct": 100 * len(ganadas) / len(trades) if trades else 0.0,
        "factor_beneficio": gan_total / per_total if per_total else float("inf") if gan_total else 0.0,
        "pnl_total": capital - cfg["capital_inicial"],
        "pnl_por_dia": (capital - cfg["capital_inicial"]) / max(len(dias), 1),
        "dias_meta": sum(1 for d in dias if pnl_dia.get(d, 0) >= cfg["meta_diaria"]),
        "dias_perdida": sum(1 for d in dias if pnl_dia.get(d, 0) < 0),
        "para_usuario": usuario,
        "fondo_agente": fondo,
        "apagado": apagado,
    }
