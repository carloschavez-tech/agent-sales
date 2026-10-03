"""El cerebro: tendencia en 1h + retroceso a la EMA20 en 15m. Stop por ATR, objetivos a 1R y 2R.

Reglas LONG (SHORT es el espejo):
  1. Tendencia 1h alcista: cierre > EMA50 > EMA200.
  2. Retroceso: en las últimas 4 velas de 15m el precio tocó la EMA20.
  3. Reanudación: la vela cierra sobre la EMA20, es verde y el RSI(14) sube, entre 45 y 68.
  4. Volatilidad sana: ATR entre 0.1 % y 2 % del precio.
  Stop: el mínimo de las últimas 5 velas o 1.2 ATR (lo más lejano), sin pasar de 3 ATR.
  TP1 = 1R (se cierra la mitad y el stop pasa a la entrada). TP2 = 2R.
  Si en 4 horas no tocó ni stop ni TP2, se cierra a mercado.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .datos import Vela, a_hora

VELAS_MAX = 16  # 4 horas en 15m


def ema(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) < n:
        return out
    k = 2 / (n + 1)
    e = sum(xs[:n]) / n
    out[n - 1] = e
    for i in range(n, len(xs)):
        e = xs[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi(xs: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) <= n:
        return out
    cambios = [xs[i] - xs[i - 1] for i in range(1, len(xs))]
    sube = sum(max(c, 0) for c in cambios[:n]) / n
    baja = sum(max(-c, 0) for c in cambios[:n]) / n
    for i in range(n, len(xs)):
        if i > n:
            c = cambios[i - 1]
            sube = (sube * (n - 1) + max(c, 0)) / n
            baja = (baja * (n - 1) + max(-c, 0)) / n
        out[i] = 100.0 if baja == 0 else 100 - 100 / (1 + sube / baja)
    return out


def atr(vs: list[Vela], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(vs)
    if len(vs) <= n:
        return out
    tr = [vs[0].h - vs[0].l] + [max(v.h - v.l, abs(v.h - p.c), abs(v.l - p.c)) for p, v in zip(vs, vs[1:])]
    a = sum(tr[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(vs)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


@dataclass
class Senal:
    simbolo: str
    lado: str          # LONG | SHORT
    entrada: float
    stop: float
    tp1: float
    tp2: float
    atr: float
    vela_t: int        # apertura de la vela de 15m que generó la señal
    motivo: str

    @property
    def r(self) -> float:
        return abs(self.entrada - self.stop)

    def dict(self) -> dict:
        return asdict(self)


class Analisis:
    """Indicadores precalculados sobre una serie de velas de 15m (se reusa en vivo y en backtest)."""

    def __init__(self, simbolo: str, v15: list[Vela]):
        self.simbolo = simbolo
        self.v = v15
        c = [v.c for v in v15]
        self.ema20, self.rsi, self.atr = ema(c, 20), rsi(c), atr(v15)
        horas, self.cierre_hora = a_hora(v15)
        hc = [h.c for h in horas]
        self.hc, self.h50, self.h200 = hc, ema(hc, 50), ema(hc, 200)
        # índice de la última hora cerrada para cada vela de 15m
        self.hora_de: list[int | None] = []
        j = -1
        for i in range(len(v15)):
            while j + 1 < len(self.cierre_hora) and self.cierre_hora[j + 1] <= i:
                j += 1
            self.hora_de.append(j if j >= 0 else None)

    def tendencia(self, i: int) -> str | None:
        j = self.hora_de[i]
        if j is None or self.h200[j] is None:
            return None
        if self.hc[j] > self.h50[j] > self.h200[j]:
            return "LONG"
        if self.hc[j] < self.h50[j] < self.h200[j]:
            return "SHORT"
        return None

    def evaluar(self, i: int) -> Senal | None:
        if i < 20 or self.ema20[i] is None or self.rsi[i - 1] is None or self.atr[i] is None:
            return None
        lado = self.tendencia(i)
        if lado is None:
            return None
        v, e20, r, a = self.v[i], self.ema20[i], self.rsi[i], self.atr[i]
        if not 0.001 <= a / v.c <= 0.02:
            return None
        ult = self.v[i - 3:i + 1]
        if lado == "LONG":
            ok = (min(x.l for x in ult) <= e20 * 1.001 and v.c > e20 and v.c > v.o
                  and 45 <= r <= 68 and r > self.rsi[i - 1])
            if not ok:
                return None
            stop = min(min(x.l for x in self.v[i - 4:i + 1]), v.c - 1.2 * a)
            stop = max(stop, v.c - 3 * a)
            R = v.c - stop
            return Senal(self.simbolo, "LONG", v.c, stop, v.c + R, v.c + 2 * R, a, v.t,
                         f"Tendencia 1h alcista, retroceso a EMA20 ({e20:.2f}) y reanudación; RSI {r:.0f}")
        ok = (max(x.h for x in ult) >= e20 * 0.999 and v.c < e20 and v.c < v.o
              and 32 <= r <= 55 and r < self.rsi[i - 1])
        if not ok:
            return None
        stop = max(max(x.h for x in self.v[i - 4:i + 1]), v.c + 1.2 * a)
        stop = min(stop, v.c + 3 * a)
        R = stop - v.c
        return Senal(self.simbolo, "SHORT", v.c, stop, v.c - R, v.c - 2 * R, a, v.t,
                     f"Tendencia 1h bajista, rebote a EMA20 ({e20:.2f}) y rechazo; RSI {r:.0f}")

    def contexto(self) -> str:
        i = len(self.v) - 1
        t = self.tendencia(i) or "LATERAL (no se opera)"
        return (f"{self.simbolo}: precio {self.v[i].c:.4f} · tendencia 1h {t} · "
                f"EMA20 {self.ema20[i]:.4f} · RSI {self.rsi[i]:.0f} · ATR {self.atr[i]:.4f}")


def tamano(s: Senal, capital: float, riesgo_usd: float, comision_pct: float,
           max_apalancamiento: float, paso: float) -> tuple[float, float]:
    """Cantidad (redondeada al paso del exchange) y riesgo real en USD, comisiones incluidas."""
    costo_por_unidad = s.r + s.entrada * 2 * comision_pct / 100
    qty = riesgo_usd / costo_por_unidad
    qty = min(qty, capital * max_apalancamiento / s.entrada)
    qty = math.floor(qty / paso + 1e-9) * paso
    qty = round(qty, 8)
    return qty, qty * costo_por_unidad
