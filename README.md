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
