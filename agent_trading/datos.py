"""Velas públicas del exchange (sin API key). Solo lectura: el agente nunca ejecuta órdenes."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}


@dataclass
class Vela:
    t: int        # apertura, ms UTC
    o: float
    h: float
    l: float
    c: float
    v: float


def _get(url: str, params: dict) -> object:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": "agent-trading/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _binance(base: str, limite: int, simbolo: str, intervalo: str, fin: int | None) -> list[Vela]:
    params = {"symbol": simbolo, "interval": intervalo, "limit": limite}
    if fin:
        params["endTime"] = fin
    return [Vela(int(k[0]), *map(float, k[1:6])) for k in _get(base, params)]


def _bybit(simbolo: str, intervalo: str, fin: int | None) -> list[Vela]:
    params = {"category": "linear", "symbol": simbolo, "interval": MS[intervalo] // 60_000, "limit": 1000}
    if fin:
        params["end"] = fin
    filas = _get("https://api.bybit.com/v5/market/kline", params)["result"]["list"]
    return [Vela(int(k[0]), *map(float, k[1:6])) for k in reversed(filas)]


def _pagina(exchange: str, simbolo: str, intervalo: str, fin: int | None) -> list[Vela]:
    if exchange == "binance_futuros":
        return _binance("https://fapi.binance.com/fapi/v1/klines", 1500, simbolo, intervalo, fin)
    if exchange == "binance_spot":
        return _binance("https://api.binance.com/api/v3/klines", 1000, simbolo, intervalo, fin)
    if exchange == "bybit":
        return _bybit(simbolo, intervalo, fin)
    raise ValueError(f"Exchange no soportado: {exchange}")


def velas(exchange: str, simbolo: str, intervalo: str, cantidad: int) -> list[Vela]:
    """Últimas `cantidad` velas CERRADAS (descarta la que todavía se está formando)."""
    ahora = int(time.time() * 1000)
    out: list[Vela] = []
    fin = None
    while len(out) < cantidad:
        pagina = _pagina(exchange, simbolo, intervalo, fin)
        pagina = [v for v in pagina if not out or v.t < out[0].t]
        if not pagina:
            break
        out = pagina + out
        fin = out[0].t - 1
    out = [v for v in out if v.t + MS[intervalo] <= ahora]
    return out[-cantidad:]


def a_hora(velas15: list[Vela]) -> tuple[list[Vela], list[int]]:
    """Agrupa velas de 15m en velas de 1h completas.

    Devuelve las velas de 1h y, para cada una, el índice de la vela de 15m con la que
    cierra (así el análisis de la vela i solo usa horas ya cerradas: sin mirar el futuro).
    """
    horas: list[Vela] = []
    cierre: list[int] = []
    grupo: list[Vela] = []
    for i, v in enumerate(velas15):
        if grupo and v.t // MS["1h"] != grupo[0].t // MS["1h"]:
            grupo = []
        grupo.append(v)
        if len(grupo) == 4:
            horas.append(Vela(grupo[0].t, grupo[0].o, max(x.h for x in grupo),
                              min(x.l for x in grupo), grupo[-1].c, sum(x.v for x in grupo)))
            cierre.append(i)
    return horas, cierre
