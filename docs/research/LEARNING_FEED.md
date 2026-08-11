# Learning Feed: Fuentes para Mantenerse Actualizado (2026-08-10)

Fuentes de información curada para el hábito de informarse y estar al día en
trading sistemático / intraday. Separa fuentes de **datos verificables** de las de
**señales** (Telegram/Facebook, mayormente no verificables).

## Regla general

- Un edge operativo real **no se regala**: quien vive de él no lo publica vivo
  (hedge funds, prop firms). Publican papers, frameworks y estadística descriptiva.
- Lo público que vale la pena: efectos documentados, papers académicos, y sitios de
  estadística dura. Las señales listas para copiar son estructuralmente sospechosas.
- Regla de oro para cualquier canal: si no puedes ver **todo** el historial de
  señales con timestamps y pérdidas incluidas (sin ediciones/borrados) y cada señal
  no lleva SL → tratarlo como hostil.

## Nivel 1 — Datos verificables (la mejor señal/ruido)

| Fuente | Qué es | URL |
|--------|--------|-----|
| QuantPedia | Catálogo académico de efectos documentados (seasonality, momentum, etc.) | https://quantpedia.com |
| thetrading.tools | Estadística dura: overnight drift de SPY (8,434 días), weekday, señales | https://www.thetrading.tools |
| tradingstats.net | Estadística de estrategias intradía: ORB en ES/NQ (6,142 días) | https://tradingstats.net |
| intradayseasonals.com | Intraday seasonality (legado de Larry Williams) | https://intradayseasonals.com |
| stockmarketonline.com | Seasonality intradiario con hit rates por hora | https://www.stockmarketonline.com |
| sapphirecapitals.com | App de intraday seasonality por hora | https://sapphirecapitals.com |
| tradeseasons.com | Patrones estacionales stocks/indices/forex | https://tradeseasons.com |

## Nivel 2 — Academia / papers

| Fuente | Qué es | URL |
|--------|--------|-----|
| SSRN | Papers de finanzas (Concretum Group, etc.) | https://papers.ssrn.com |
| arXiv (q-fin / fin-ML) | Preprints de finanzas cuantitativa y ML | https://arxiv.org |
| ScienceDirect / journals | Papers revisados por pares (ORB, FX intraday) | https://www.sciencedirect.com |
| paperswithbacktest | Papers resumidos + enlaces a backtests | https://paperswithbacktest.com |

Ejemplos de papers relevantes a nuestro sistema:
- *Assessing the profitability of intraday opening range breakout strategies* (ScienceDirect, 2013).
- *In Search of Seasonality in Intraday and Overnight Option Returns* (paperswithbacktest).
- *Catching Crypto Trends: A Tactical Approach for Bitcoin and Altcoins* (SSRN, Concretum).
- *Overnight Seasonality in Bitcoin* (QuantPedia): "hold BTC solo 2 horas al día".

## Nivel 3 — Foros y comunidades

| Comunidad | Foco | URL |
|-----------|------|-----|
| Wilmott | Foro de quants, teoría-práctica, papers | https://forum.wilmott.com |
| r/quant | Quant general, careers, papers | https://www.reddit.com/r/quant |
| r/quantfinance | Quant finance | https://www.reddit.com/r/quantfinance |
| r/algotrading | Implementación de estrategias | https://www.reddit.com/r/algotrading |
| QuantConnect | Foro + Discord, motor Lean, backtests | https://www.quantconnect.com |
| NexusFi (ex Elite Trader) | Futuros/intradía ES/NQ, microestructura | https://nexusfi.com |

## Nivel 4 — Discord

| Servidor | Foco | Notas |
|----------|------|-------|
| Quant Trading App (QTA) | Trading cuantitativo, GEX, opciones | ~11.8k miembros |
| Quant Talk | Quant trading / algo / data science | ~2.8k miembros |
| Quantitative Research Network | Systematic + macro research | ~1.2k miembros |
| QuantQuestionsIO | Prep de entrevistas quant | ~5.4k miembros (más careers que trading) |
| HangukQuant Discord | Comunidad de readers de HangukQuant (Substack) | acceso tras suscribirse |

## Nivel 5 — Newsletter / Substack

- HangukQuant (Substack): research quant con código (Russian Doll, etc.).
- Research letters de thetrading.tools / tradingstats.net (análisis verificables).
- Preferir newsletters que publican **datos y metodología**, no opiniones.

## Señales — qué NO usar como fuente de información

- **Telegram/Facebook signal groups**: ~90% son estafas; estructuralmente
  imposibles de verificar (historial editable, anonimato, broadcast masivo, pump-and-dump).
  Reporte Chainalysis 2025: fake signal groups top-5 categoría de estafa cripto.
  FTC 2024: $14B+ perdidos en estafas de inversión, redes sociales como vector principal.
- Red flags: retornos garantizados, historial borrado/editado, presión a "VIP",
  sin SL en las señales, referidos agresivos.
- Mejor alternativa: brokers con copy-trading transparente y estadísticas auditables
  (p.ej. OANDA, Interactive Brokers, eToro) — nunca grupos anónimos.

## Sitios de referencia de código / repos

| Recurso | Qué es | URL |
|---------|--------|-----|
| freqtrade/freqtrade-strategies | 5.3k★, estrategias para Freqtrade | https://github.com/freqtrade/freqtrade-strategies |
| polakowo/vectorbt | Motor de backtesting (el que usamos) | https://github.com/polakowo/vectorbt |
| sam-bateman/trading-orb | ORB intraday sistemático | https://github.com/sam-bateman/trading-orb |
| vinnypt/ES-NQ-Pairs-Trading | Pairs trading ES-NQ (referencia) | https://github.com/vinnypt/ES-NQ-Pairs-Trading |
| shashwat-shahi/Statistical-Arbitrage-Trading-Strategy | Stat arb con Kalman (referencia) | https://github.com/shashwat-shahi/Statistical-Arbitrage-Trading-Strategy |
| TheoBrigitte/freqtrade | Estrategias + dry-runs de freqtrade | https://github.com/TheoBrigitte/freqtrade |
| monomadic Scalping Handbook (gist) | Guía de scalping | https://gist.github.com/monomadic/cd134ec73738fc5dae9afdfdcedb7744 |

## Flujo sugerido (30 min/semana)

1. **Lunes**: 1 entrada de QuantPedia (efecto documentado) + 1 lectura de
   tradingstats.net o thetrading.tools (estadística dura).
2. Evaluar si el hallazgo aplica a nuestros 25 tickers con backtest vbt
   (skill `strategy-research`).
3. Guardar hallazgos en `docs/research/` (patrón que ya usamos para Kronos y ORB).

## Datos de respaldo de la industria (citas)

- FTC: consumidores perdieron $14B+ en estafas de inversión en 2024.
- Chainalysis 2025: fake signal groups top-5 categoría de estafa cripto por víctimas.
- Análisis de la industria 2025: ~90% de canales de señales de Telegram son estafas.
- Overnight drift SPY (thetrading.tools, 2026-08-05): $100→$1,507 overnight vs $116
  intraday desde 1993; mejor transición Viernes→Lunes (+0.05%, win 56.1%).
