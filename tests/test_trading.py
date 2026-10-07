"""Pruebas del agente de trading con datos sintéticos (sin red)."""

import math
import random
import tempfile
import unittest
from pathlib import Path

import yaml

from agent_trading.backtest import simular
from agent_trading.datos import Vela, a_hora
from agent_trading.estrategia import Analisis, Senal, ema, rsi, tamano
from agent_trading.libro import Libro

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "trading.yaml").read_text())


def serie(n: int, semilla: int = 7) -> list[Vela]:
    rnd = random.Random(semilla)
    p, out, t = 60_000.0, [], 1_700_000_000_000 // 3_600_000 * 3_600_000
    for i in range(n):
        deriva = 0.0004 * math.sin(i / 900)
        o = p
        c = o * (1 + deriva + rnd.gauss(0, 0.002))
        h, l = max(o, c) * (1 + abs(rnd.gauss(0, 0.001))), min(o, c) * (1 - abs(rnd.gauss(0, 0.001)))
        out.append(Vela(t + i * 900_000, o, h, l, c, 1.0))
        p = c
    return out


class Indicadores(unittest.TestCase):
    def test_ema_constante(self):
        self.assertAlmostEqual(ema([5.0] * 30, 10)[-1], 5.0)

    def test_rsi_extremos(self):
        self.assertEqual(rsi([float(i) for i in range(30)])[-1], 100.0)
        self.assertLess(rsi([float(30 - i) for i in range(30)])[-1], 1)

    def test_horas_sin_futuro(self):
        v = serie(40)
        horas, cierre = a_hora(v)
        self.assertEqual(len(horas), 10)
        self.assertTrue(all(c % 4 == 3 for c in cierre))
        an = Analisis("BTCUSDT", v)
        self.assertIsNone(an.hora_de[2])
        self.assertEqual(an.hora_de[3], 0)


class Tamano(unittest.TestCase):
    def test_riesgo_y_apalancamiento(self):
        s = Senal("BTCUSDT", "LONG", 60_000, 59_400, 60_600, 61_200, 300, 0, "")
        qty, riesgo = tamano(s, 1000, 10, 0.05, 3, 0.001)
        self.assertLessEqual(riesgo, 10)
        self.assertLessEqual(qty * 60_000, 3000 + 1e-6)
        self.assertAlmostEqual(qty, 0.015)  # 10 USD / 660 por BTC = 0.01515 → paso 0.001
        qty, _ = tamano(s, 1000, 100, 0.05, 3, 0.001)
        self.assertAlmostEqual(qty, 0.05)  # tope 3x: 3000 USD / 60 000


class LibroReglas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = Libro(Path(self.tmp.name) / "libro.json", CFG)

    def tearDown(self):
        self.tmp.cleanup()

    def _op(self, entrada, salida, qty=0.01, lado="LONG"):
        self.lib.abrir("BTCUSDT", lado, entrada, qty, entrada - 500, None, None)
        return self.lib.cerrar(None, salida, None)

    def test_meta_bloquea(self):
        self._op(60_000, 61_200)
        self.assertGreater(self.lib.pnl_dia(self.lib.hoy()), 10)
        self.assertIn("Meta", self.lib.bloqueo())

    def test_perdida_diaria_bloquea(self):
        self._op(60_000, 58_900)
        self.assertIn("Pérdida máxima", self.lib.bloqueo())
        self.assertEqual(self.lib.riesgo_disponible(), 0.0)

    def test_reparto_y_deuda(self):
        for dia, pnl in [("2020-01-01", 20.0), ("2020-01-02", -12.0)]:
            self.lib.d["operaciones"].append({"id": 0, "estado": "cerrada", "dia": dia, "pnl": pnl,
                                              "dia_apertura": dia})
        self.lib._liquidar_dias()
        self.assertAlmostEqual(self.lib.d["ganancia_usuario"], 12.0)
        self.assertAlmostEqual(self.lib.d["fondo_agente"], 8.0 - 12.0)
        self.assertIsNone(self.lib.d["apagado"])

    def test_apagado_por_deuda_y_reactivar(self):
        self.lib.d["operaciones"].append({"id": 0, "estado": "cerrada", "dia": "2020-01-01", "pnl": -31.0,
                                          "dia_apertura": "2020-01-01"})
        self.lib._liquidar_dias()
        self.assertIn("APAGADO", self.lib.bloqueo())
        self.lib.reactivar(perdonar_deuda=True)
        self.assertIsNone(self.lib.bloqueo())
        self.assertEqual(self.lib.d["fondo_agente"], 0.0)

    def test_tp1_parcial_mueve_stop(self):
        self.lib.abrir("BTCUSDT", "SHORT", 60_000, 0.02, 60_500, 59_500, 59_000)
        op = self.lib.cerrar(None, 59_500, 0.01)
        self.assertEqual(op["estado"], "abierta")
        self.assertEqual(op["stop"], 60_000)
        op = self.lib.cerrar(None, 59_000, None)
        self.assertAlmostEqual(op["pnl"], 5 + 10 - (1200 + 595 + 590) * 0.0005, places=4)

    def test_solicitud_requiere_fondo(self):
        s = self.lib.solicitar(5, "datos premium")
        with self.assertRaises(ValueError):
            self.lib.resolver(s["id"], True)
        self.lib.d["fondo_agente"] = 8
        self.lib.resolver(s["id"], True)
        self.assertEqual(self.lib.d["fondo_agente"], 3)
        self.assertIsNone(self.lib.d["apagado"])

    def test_retiro_no_cuenta_como_perdida(self):
        self.lib.d["ganancia_usuario"] = 200
        self.lib.retirar(150)
        self.lib.revisar_apagado()
        self.assertIsNone(self.lib.d["apagado"])


class Backtest(unittest.TestCase):
    def test_corre_y_respeta_reglas(self):
        r = simular("BTCUSDT", serie(96 * 60), CFG, 0.0001)
        self.assertGreater(r["operaciones"], 0)
        self.assertLessEqual(r["operaciones"], r["dias"] * CFG["max_operaciones_dia"])
        self.assertGreater(max(t["dia"] for t in r["trades"]), r["trades"][0]["dia"])
        print("\n", {k: round(v, 2) if isinstance(v, float) else v for k, v in r.items()})


if __name__ == "__main__":
    unittest.main()
