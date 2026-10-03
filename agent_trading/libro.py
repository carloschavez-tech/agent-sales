"""Libro del trato: operaciones, reparto 60/40, fondo del agente, solicitudes y apagado.

Reglas de dinero:
  - Día con ganancia neta  → 60 % para ti, 40 % al fondo del agente.
  - Día con pérdida neta   → se cobra completa al fondo del agente (puede quedar en deuda).
    Las ganancias siguientes del agente pagan primero esa deuda.
  - Deuda del agente > limite_deuda_agente, o capital −drawdown_max_pct desde su máximo → APAGADO.
    Solo tú lo reactivas.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class Libro:
    def __init__(self, ruta: Path, cfg: dict):
        self.ruta = ruta
        self.cfg = cfg
        self.tz = ZoneInfo(cfg.get("zona_horaria", "UTC"))
        if ruta.exists():
            self.d = json.loads(ruta.read_text(encoding="utf-8"))
        else:
            cap = float(cfg["capital_inicial"])
            self.d = {"capital_inicial": cap, "pico_capital": cap, "operaciones": [], "dias": {},
                      "fondo_agente": 0.0, "ganancia_usuario": 0.0, "retiros_usuario": 0.0,
                      "gastos_agente": 0.0, "solicitudes": [], "eventos": [],
                      "apagado": None, "ultima_senal": None}
        self._liquidar_dias()

    # ── utilidades ──────────────────────────────────────────
    def ahora(self) -> datetime:
        return datetime.now(self.tz)

    def hoy(self) -> str:
        return self.ahora().strftime("%Y-%m-%d")

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.ruta)

    def evento(self, texto: str) -> None:
        self.d["eventos"].append({"fecha": self.ahora().isoformat(timespec="seconds"), "texto": texto})

    # ── cifras ──────────────────────────────────────────────
    def cerradas(self) -> list[dict]:
        return [o for o in self.d["operaciones"] if o["estado"] == "cerrada"]

    def abiertas(self) -> list[dict]:
        return [o for o in self.d["operaciones"] if o["estado"] == "abierta"]

    def pnl_dia(self, dia: str) -> float:
        return sum(o["pnl"] for o in self.cerradas() if o["dia"] == dia)

    def operaciones_dia(self, dia: str) -> int:
        return sum(1 for o in self.d["operaciones"] if o["dia_apertura"] == dia)

    def pnl_total(self) -> float:
        return sum(o["pnl"] for o in self.cerradas())

    def capital(self) -> float:
        return (self.d["capital_inicial"] + self.pnl_total()
                - self.d["retiros_usuario"] - self.d["gastos_agente"])

    def fondo_con_hoy(self) -> float:
        """Fondo del agente contando la pérdida de hoy (las ganancias de hoy aún no se reparten)."""
        return self.d["fondo_agente"] + min(self.pnl_dia(self.hoy()), 0.0)

    # ── reparto diario ──────────────────────────────────────
    def _liquidar_dias(self) -> None:
        hoy = self.hoy()
        dias = sorted({o["dia"] for o in self.cerradas()} - set(self.d["dias"]))
        for dia in dias:
            if dia >= hoy:
                continue
            pnl = self.pnl_dia(dia)
            rep = self.cfg["reparto"]
            usuario = pnl * rep["usuario"] if pnl > 0 else 0.0
            agente = pnl * rep["agente"] if pnl > 0 else pnl
            self.d["ganancia_usuario"] += usuario
            self.d["fondo_agente"] += agente
            self.d["dias"][dia] = {"pnl": round(pnl, 2), "usuario": round(usuario, 2),
                                   "agente": round(agente, 2)}
        if dias:
            self.revisar_apagado()
            self.guardar()

    # ── apagado ─────────────────────────────────────────────
    def revisar_apagado(self) -> None:
        if self.d["apagado"]:
            return
        cap = self.capital()
        self.d["pico_capital"] = max(self.d["pico_capital"], cap)
        motivo = None
        if self.fondo_con_hoy() <= -self.cfg["limite_deuda_agente"]:
            motivo = (f"El agente perdió su dinero: deuda del fondo {self.fondo_con_hoy():.2f} USD "
                      f"(límite −{self.cfg['limite_deuda_agente']})")
        elif cap <= self.d["pico_capital"] * (1 - self.cfg["drawdown_max_pct"] / 100):
            motivo = (f"Capital {cap:.2f} USD cayó más de {self.cfg['drawdown_max_pct']} % "
                      f"desde el máximo {self.d['pico_capital']:.2f}")
        if motivo:
            self.d["apagado"] = {"fecha": self.ahora().isoformat(timespec="seconds"), "motivo": motivo}
            self.evento(f"APAGADO: {motivo}")

    def reactivar(self, perdonar_deuda: bool) -> None:
        self.evento(f"Reactivado por el usuario (antes: {self.d['apagado']['motivo']}). "
                    f"Deuda {'perdonada' if perdonar_deuda else 'se mantiene'}.")
        self.d["apagado"] = None
        if perdonar_deuda and self.d["fondo_agente"] < 0:
            self.d["fondo_agente"] = 0.0
        self.d["pico_capital"] = self.capital()

    def bloqueo(self) -> str | None:
        """Por qué el agente no puede dar señales ahora mismo (None = puede operar)."""
        if self.d["apagado"]:
            return f"⛔ AGENTE APAGADO — {self.d['apagado']['motivo']}. Solo tú puedes reactivarlo."
        hoy = self.hoy()
        pnl = self.pnl_dia(hoy)
        if self.abiertas():
            o = self.abiertas()[0]
            return f"Hay una operación abierta (#{o['id']} {o['lado']} {o['simbolo']}). Ciérrala primero."
        if pnl <= -self.cfg["perdida_max_diaria"]:
            return f"🛑 Pérdida máxima del día alcanzada ({pnl:.2f} USD). Mañana se vuelve a operar."
        if self.cfg.get("parar_al_llegar_meta", True) and pnl >= self.cfg["meta_diaria"]:
            return f"🎯 Meta del día cumplida (+{pnl:.2f} USD). No se opera más hoy."
        if self.operaciones_dia(hoy) >= self.cfg["max_operaciones_dia"]:
            return f"Máximo de {self.cfg['max_operaciones_dia']} operaciones por día alcanzado."
        return None

    def riesgo_disponible(self) -> float:
        """USD que se pueden arriesgar en la próxima operación sin pasar la pérdida máxima diaria."""
        por_op = self.capital() * self.cfg["riesgo_por_operacion_pct"] / 100
        margen_dia = self.cfg["perdida_max_diaria"] + self.pnl_dia(self.hoy())
        return max(0.0, min(por_op, margen_dia))

    # ── operaciones ─────────────────────────────────────────
    def abrir(self, simbolo: str, lado: str, entrada: float, cantidad: float,
              stop: float, tp1: float | None, tp2: float | None, nota: str = "") -> dict:
        ahora = self.ahora()
        op = {"id": len(self.d["operaciones"]) + 1, "simbolo": simbolo, "lado": lado,
              "entrada": entrada, "cantidad": cantidad, "stop": stop, "tp1": tp1, "tp2": tp2,
              "abierta_en": ahora.isoformat(timespec="seconds"), "dia_apertura": ahora.strftime("%Y-%m-%d"),
              "salidas": [], "estado": "abierta", "nota": nota}
        self.d["operaciones"].append(op)
        return op

    def cerrar(self, op_id: int | None, precio: float, cantidad: float | None) -> dict:
        abiertas = self.abiertas()
        op = next((o for o in abiertas if op_id is None or o["id"] == op_id), None)
        if op is None:
            raise ValueError("No hay una operación abierta con ese id.")
        vendido = sum(s["cantidad"] for s in op["salidas"])
        resto = round(op["cantidad"] - vendido, 10)
        cant = min(cantidad or resto, resto)
        op["salidas"].append({"precio": precio, "cantidad": cant,
                              "fecha": self.ahora().isoformat(timespec="seconds")})
        if cant >= resto - 1e-12:
            self._finalizar(op)
        elif op["tp1"] is not None:
            # cierre parcial (TP1): el stop pasa a la entrada
            op["stop"] = op["entrada"]
        return op

    def _finalizar(self, op: dict) -> None:
        signo = 1 if op["lado"] == "LONG" else -1
        com = self.cfg["comision_pct"] / 100
        bruto = sum(signo * (s["precio"] - op["entrada"]) * s["cantidad"] for s in op["salidas"])
        comisiones = op["entrada"] * op["cantidad"] * com + sum(s["precio"] * s["cantidad"] * com
                                                                for s in op["salidas"])
        op["pnl"] = round(bruto - comisiones, 4)
        op["comisiones"] = round(comisiones, 4)
        op["estado"] = "cerrada"
        op["cerrada_en"] = self.ahora().isoformat(timespec="seconds")
        op["dia"] = self.ahora().strftime("%Y-%m-%d")
        self.revisar_apagado()

    # ── dinero ──────────────────────────────────────────────
    def solicitar(self, monto: float, motivo: str) -> dict:
        s = {"id": len(self.d["solicitudes"]) + 1, "fecha": self.ahora().isoformat(timespec="seconds"),
             "monto": monto, "motivo": motivo, "estado": "pendiente"}
        self.d["solicitudes"].append(s)
        return s

    def resolver(self, sid: int, aprobar: bool, nota: str = "") -> dict:
        s = next((x for x in self.d["solicitudes"] if x["id"] == sid), None)
        if s is None or s["estado"] != "pendiente":
            raise ValueError("No hay una solicitud pendiente con ese id.")
        if aprobar and s["monto"] > self.d["fondo_agente"]:
            raise ValueError(f"El fondo del agente tiene {self.d['fondo_agente']:.2f} USD; "
                             f"no alcanza para {s['monto']:.2f}.")
        s["estado"] = "aprobada" if aprobar else "rechazada"
        s["nota"] = nota
        if aprobar:
            self.d["fondo_agente"] -= s["monto"]
            self.d["gastos_agente"] += s["monto"]
            self.d["pico_capital"] -= s["monto"]
        self.evento(f"Solicitud #{sid} {s['estado']} ({s['monto']} USD: {s['motivo']})")
        return s

    def retirar(self, monto: float) -> None:
        if monto > self.d["ganancia_usuario"] + 1e-9:
            raise ValueError(f"Tu ganancia acumulada es {self.d['ganancia_usuario']:.2f} USD.")
        self.d["ganancia_usuario"] -= monto
        self.d["retiros_usuario"] += monto
        self.d["pico_capital"] -= monto  # sacar dinero no es perder dinero
        self.evento(f"Retiro del usuario: {monto} USD")

    def apto_para_real(self) -> tuple[bool, str]:
        n, pnl = len(self.cerradas()), self.pnl_total()
        minimo = self.cfg["min_operaciones_papel"]
        if n >= minimo and pnl > 0:
            return True, f"{n} operaciones en papel, neto +{pnl:.2f} USD"
        return False, f"{n}/{minimo} operaciones en papel, neto {pnl:+.2f} USD"
