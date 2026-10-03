# agent-sales 🎯

Le das una **página web** (o el nombre de un negocio que **no tiene web**) y el agente:

1. **Investiga** al prospecto en internet: sitio, Google Maps, reseñas, Instagram/Facebook/LinkedIn, vacantes, competencia.
2. **Diagnostica** dónde pierden plata o tiempo (pedidos por WhatsApp, catálogos en PDF, sitio viejo, reservas por teléfono…), siempre con evidencia.
3. **Diseña una propuesta de software a medida**: oportunidades priorizadas, MVP de 4-8 semanas, fases, inversión y retorno.
4. **Escribe el correo en frío** que abre con algo específico de *su* negocio, con un mini-diagnóstico visual y un solo llamado a la acción.
5. Arma la **secuencia de seguimiento** (días 3, 7 y 14) más mensajes para WhatsApp y LinkedIn.

## Arranque rápido

```bash
pip install -r requirements.txt
cp .env.example .env          # pon tu ANTHROPIC_API_KEY
# Llena config/empresa.yaml (tus servicios, precios, casos de éxito, link de agenda)

python -m agent_sales https://www.ejemplo.com.co
python -m agent_sales "Panadería La Espiga, Laureles, Medellín. IG @laespiga. No tiene web"
python -m agent_sales https://www.ejemplo.com.co --contexto "Nos refirió Juan; tienen líos con inventario"
```

## Qué te entrega (`salidas/AAAA-MM-DD_nombre/`)

| Archivo | Para qué |
|---|---|
| `correo.html` | Correo listo para pegar/enviar (se ve bien en Gmail y Outlook) |
| `correo.txt` | 3 asuntos para A/B test + versión en texto plano |
| `propuesta.html` | Propuesta de una página; Ctrl+P → PDF para adjuntar después de la reunión |
| `propuesta.md` | La misma propuesta, editable |
| `seguimiento.md` | Secuencia de seguimiento, WhatsApp, LinkedIn y a quién escribirle |
| `investigacion.md` | Informe de investigación con las fuentes (URLs) |
| `datos.json` | Todo lo anterior en estructura, para CRM o automatizaciones |

## Personalizar

- **Verificación de identidad:** si el agente no puede confirmar que el prospecto es el negocio correcto (pasa mucho con Instagram), se detiene y no escribe el correo. Dale más datos con `--contexto "sector, ciudad, web"` o usa `--forzar` si ya lo confirmaste tú.
- `config/empresa.yaml`: **lo más importante**. Casos de éxito reales con números y precios de referencia hacen que la propuesta sea creíble. El agente nunca inventa casos.
- `agent_sales/prompts.py`: el "cerebro" vendedor (reglas de copy, estructura del correo, tono).
- `agent_sales/render.py`: diseño del correo y de la propuesta (color de marca en `ACCENT`).

## Cómo funciona

Usa Claude (`claude-opus-5`) en dos fases: investigación con las herramientas de búsqueda y lectura web del lado del servidor, y después una salida estructurada (JSON Schema) con propuesta, correo y seguimientos. Tiene activado el respaldo automático del servidor por si el modelo rechaza la solicitud.

---

# agent-trading 📈

Agente de señales de trading (cripto, futuros perpetuos). **El agente es el cerebro; tú eres las manos**: te da la entrada, el stop, los objetivos y la cantidad de un LONG o SHORT, tú ejecutas en el exchange y registras lo que pasó. Nunca toca tu dinero ni tus llaves.

## El trato (`config/trading.yaml`)

| Regla | Valor por defecto |
|---|---|
| Meta diaria | 10 USD; al cumplirla no se opera más ese día |
| Reparto de un día ganador | 60 % para ti · 40 % al fondo del agente |
| Día perdedor | la pérdida se cobra completa del fondo del agente (puede quedar en deuda) |
| **Apagado** | deuda del agente > 30 USD, o capital −10 % desde su máximo → se apaga y solo tú lo reactivas |
| Riesgo | 1 % del capital por operación, máx. 10 USD de pérdida al día, 3 operaciones/día, máx. 3x |
| Papel → real | no te deja pasar a real sin 30 operaciones en papel con resultado neto positivo |
| Fondo del agente | lo usa pidiéndote (`solicitar`); tú decides (`aprobar` / `rechazar`) |

## Uso

```bash
pip install -r requirements.txt
python -m agent_trading plan                      # ¿cuánto capital hace realista la meta?
python -m agent_trading backtest --dias 180       # ¿la estrategia tiene ventaja con estas reglas?
python -m agent_trading senal                     # ¿hay entrada ahora?
python -m agent_trading abrir --precio 61234.5    # ya entraste (usa la última señal)
python -m agent_trading cerrar --precio 61800 --cantidad 0.007   # TP1 parcial (stop pasa a la entrada)
python -m agent_trading cerrar --precio 62400     # cierre total
python -m agent_trading estado
python -m agent_trading solicitar --monto 5 --motivo "..." && python -m agent_trading aprobar 1
```

Pruebas: `python -m unittest tests.test_trading -v`. El libro se guarda en `salidas/trading/<modo>/libro.json`.

## TradingView

TradingView no tiene API para que un agente opere tu cuenta, y **no hay que compartir usuario ni contraseña**. En su lugar:

1. Abre un gráfico de **15 minutos** de `BINANCE:BTCUSDT.P` (o ETH/SOL).
2. Abajo, **Pine Editor** → borra todo → pega `agent_trading/tradingview.pine` → **Add to chart**.
3. En la configuración del indicador pon tu capital y riesgo.
4. **Alertas** (reloj ⏰) → Condición: *Agente de trading — señales* → `LONG` (y otra para `SHORT`) → *Once per bar close* → notificación a la app.
5. Cuando suene: `python -m agent_trading senal` para confirmar cantidad y reglas del día (meta, pérdida máxima, apagado) antes de entrar.

## Estrategia

Tendencia en 1h (cierre > EMA50 > EMA200 para LONG, al revés para SHORT) + retroceso a la EMA20 en 15m con reanudación (vela a favor, RSI 45–68 subiendo). Stop en el extremo de las últimas 5 velas o 1.2 ATR; TP1 = 1R (se cierra la mitad y el stop va a la entrada), TP2 = 2R; si en 4 h no pasa nada, se cierra. Está en `agent_trading/estrategia.py`.

> ⚠️ Ninguna estrategia garantiza ganancias. La meta de 10 USD/día con 1 000 USD exige ~1 %/día, algo que casi nadie sostiene. Corre el backtest, opera en papel, y solo usa dinero que puedas perder.
