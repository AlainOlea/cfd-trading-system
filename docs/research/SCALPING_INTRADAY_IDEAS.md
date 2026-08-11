# Scalping e Intraday: Lluvia de Ideas y Fuentes (2026-08-10)

Contexto y fuentes de la sesión de investigación sobre cómo hacer scalping/intraday
con el sistema. Todo edge listado aquí debe validarse contra los 25 tickers con
salidas SL/TP (vbt `sl_stop`/`tp_stop`) siguiendo la skill `strategy-research`,
nunca por señal opuesta.

## Constraint crítico que filtra todo

- **Alpaca feed gratis = IEX, 15-min delay** (`data/alpaca_data.py:117-120`). El
  pipeline nunca ve las últimas 15 velas.
- Implicación: todo lo que dependa de latencia, Level 2, order flow en vivo o tick
  está descartado de entrada (microestructura, HFT, spread/arb de pares ES-NQ).
- Los edges factibles son los que operan sobre **rangos ya formados** (ORB, apertura,
  compresión) o **estadística de sesión** (overnight drift, hora del día).

## Edges con evidencia estadística que SÍ encajan

### 1. Overnight drift (el más sólido: 8,434 días de SPY desde 1993)
- Casi todo el retorno de SPY se acumula *overnight* (close→open): compuesto desde
  1993, $100 → $1,507 solo overnight vs $116 solo intraday. La sesión regular es
  ~plana (intraday por día de semana: +0.00% a +0.02%).
- Mejor transición de gap: Viernes→Lunes (+0.05%, win rate 56.1%).
- Fuente: thetrading.tools (Weekday Analysis), updated 2026-08-05.
- **Implicación para el sistema**: evaluar si los slots `1h`/`1m` (07:00-15:59 ET)
  capturan el único lugar donde hay retorno; considerar operar el gap en vez de la
  sesión plana. La descomposición overnight/intraday asume ejecución exacta en
  open/close — en la práctica spreads/slippage se comen parte del edge.

### 2. ORB — Opening Range Breakout (6,142 días de ES/NQ)
- Continuación tras el primer quiebre (ORB de 30m, cierre 5m): **64.6% ES / 67.0% NQ**.
- ORB "wide" (solo 4.3-6.9% de los días): **77.5% ES / 74.2% NQ** de continuación.
- Extensión de 1x del rango de apertura (5m) se alcanza el ~64% de los días (upside y
  downside); 2x ≈ 43%; 3x ≈ 28-30%.
- El quiebre del rango de apertura no se resuelve hasta 1-2h después del open →
  **compatible con el feed 15-min delay**.
- Filtros anti-fakeout: no operar días con gaps enormes, FOMC, earnings previos,
  VIX bajo (<12), volumen pobre (festivos). En ES el 74.3% de los días se rompen
  ambos lados del ORB 5m → usar ORB de 30m + confirmación de cierre.
- Fuente: tradingstats.net (2026-07-25); paper académico ScienceDirect (ORB sobre
  futuros de crudo, 2013); libro de referencia Toby Crabel (1990).
- Repos: `sam-bateman/trading-orb`.

### 3. Compresión → Expansión (Toby Crabel, NR7)
- Barra con rango más angosto que las 6 previas (NR7) → zona de compresión → breakout.
- Contraste con nuestro hallazgo: la volatilidad es *persistente* (Kronos rho 0.60-0.80),
  pero la *compresión* anticipa expansión. El modelo correcto es contar rangos angostos,
  no predecir dirección.
- Fuente: MQL5 blog "NR7 Opening Range Breakout EA" (2026-06-30); Crabel 1990.

### 4. Mean reversion con z-score desde VWAP (filtro de régimen estricto)
- La mean reversion (fade de extensión >2σ de VWAP/BB) funciona en días de rango y
  falla sistemáticamente en tendencia.
- Bots de ES/NQ documentan 60-75% de win rate operando SOLO días de rango, con
  filtro de sesión (horas de mayor liquidez) y sin operar días de tendencia.
- Fuente: youngmoneyinvestments (Marty Bot), mrtrader.io, nexusfi.com.
- **Implicación para el sistema**: RSI+BB ya tiene `require_ranging` (ADX<20); la
  evidencia sugiere que el filtro de régimen es lo que separa rentable de no
  rentable — considerar añadir filtro de hora del día y días de rango agresivo.

### 5. Hora del día / sesiones
- Equities: volumen alto en la primera hora, "lunch doldrums" al mediodía, "power
  hour" al cierre. La apertura (9:30-10:30 ET) concentra la mayor parte del volumen
  y forma el "Initial Balance".
- Horario (ET): 9:30-10:30 apertura volátil; 10:30-11:30 cierre europeo / reversión;
  11:30-13:30 rango (lunch); 14:00+ power hour.
- Fuente: luxalgo.com (Intraday Time-of-day Effects), sophie-ai-finance.com.

## Lo que se descarta por el delay de 15 min
- Microestructura / Level 2 / order flow / queue position (requiere datos en vivo).
- Latency edges y HFT.
- Spread/arb de pares ES-NQ (requiere tick + ejecución simultánea de ambas patas).
- Fuente de referencia sobre por qué: tech-champion.com (microstructure edges),
  sophie-ai-finance.com (retail vs institutional).

## Lección de validación directa (backtest real, BTC 15m, 6 meses)
- RSI scalping: win rate 66.3% pero **-16.88%** neto (max DD 30.6%): muchas
  victorias pequeñas vs pocas derrotas grandes. Lo rompió: sin filtro de tendencia
  + pérdidas asimétricas al atravesar tendencia bajista extendida.
- Fuente: coinquant.ai (2026-06-17). Confirma el diagnóstico de nuestros brackets.

## Recursos de código (repos)
| Recurso | Qué es |
|---------|--------|
| `freqtrade/freqtrade-strategies` | 5.3k★, estrategias gratis para Freqtrade (incl. scalping, hyperopt) |
| `polakowo/vectorbt` | Motor de backtesting vectorizado que ya usamos |
| `workprior/vectorbt-backtest` | Estrategias vbt de ejemplo (VWAP reversion, RSI+BB, SMA cross) |
| `sam-bateman/trading-orb` | ORB intraday sistemático |
| `vinnypt/ES-NQ-Pairs-Trading` | Pairs trading ES-NQ (descartado por delay, pero útil de referencia) |
| `shashwat-shahi/Statistical-Arbitrage-Trading-Strategy` | Stat arb con Kalman + cointegración (referencia) |
| `TheoBrigitte/freqtrade` | Colección de estrategias + dry-runs de freqtrade |
| `AnthonyFJGarner/...gist` | Mean reversion simple en pandas |

Otros sitios: `strat.ninja` (backtests de estrategias freqtrade), `freqst.com`
(resultados de estrategias), `deepwiki.com/freqtrade/freqtrade-strategies`
(scalping strategies), `mstock.com` (guía conceptual de scalping),
`quantstrategy.io` (order flow/DOM), `1minscalper.com` (guías 1m crypto),
`thetrading.tools` (weekday/overnight), `tradingstats.net` (ORB stats),
`mql5.com` (NR7/ORB).

## Shortlist propuesta
1. **ORB adaptado al slot 1h de US** (quiebre del rango de apertura, TP=1x rango,
   SL debajo) — edge documentable más fuerte, test corto con vbt.
2. **Filtro de régimen agresivo para RSI+BB** (horas de mayor liquidez + solo días
   de rango).
3. **Recalibrar brackets al rango de apertura** en vez de % fijo.
4. Revisar si el slot diario debería capturar el *gap overnight* en vez de la sesión.

## Fuentes (URLs completas)

**Papers / investigación académica**
- Assessing the profitability of intraday opening range breakout strategies (ScienceDirect, 2013):
  https://www.sciencedirect.com/science/article/pii/S1544612312000438
- In Search of Seasonality in Intraday and Overnight Option Returns (paperswithbacktest):
  https://paperswithbacktest.com/strategies/in-search-of-seasonality-in-intraday-and-overnight-option-returns

**Datos estadísticos**
- Weekday Analysis: SPY by day of week & overnight vs intraday (thetrading.tools):
  https://www.thetrading.tools/weekday-analysis
- ORB Strategy: 6,142 Days of ES & NQ (tradingstats.net, 2026-07-25):
  https://tradingstats.net/orb-breakout-strategy-guide

**Guías / blogs**
- Intraday Time-of-day Effects (luxalgo):
  https://www.luxalgo.com/library/concept/intraday-time-of-day-effects/
- Mastering Order Flow / DOM (quantstrategy.io, 2026-01-12):
  https://quantstrategy.io/blog/mastering-order-flow-advanced-scalping-and-momentum/
- Scalping Strategy Guide (mstock, 2026-07-10):
  https://www.mstock.com/mlearn/stock-market-courses/trading-styles/scalping-strategies
- 1-Minute Scalping Strategy (1minscalper, 2026-04-23):
  https://1minscalper.com/the-ultimate-1-minute-scalping-strategy-explained
- Advanced Scalping (marketclutch):
  https://marketclutch.com/the-precision-edge-advanced-scalping-intraday-trading-strategies/
- Microstructure edges (tech-champion):
  https://tech-champion.com/finance/find-microstructure-edges-via-queue-priority-and-imbalance
- Retail vs institutional / opciones intraday (sophie-ai-finance, 2026-02-13):
  https://www.sophie-ai-finance.com/articles/microstructure-intraday-option-speculation-mechanics-strategies-risks
- Mean reversion ES/NQ (youngmoneyinvestments, 2025-12-06):
  https://youngmoneyinvestments.com/blog/mean-reversion-trading-strategy-es-nq-futures
- Mean reversion ES/NQ Marty Bot (youngmoneyinvestments, 2026-05-05):
  https://youngmoneyinvestments.com/blog/mean-reversion-trading-strategy-futures
- Mean reversion futures (mrtrader.io):
  https://mrtrader.io/blog/mean-reversion-strategy
- Statistical arbitrage futures (nexusfi, 2026-06-01):
  https://nexusfi.com/a/automation/statistical-arbitrage-futures
- NR7 Opening Range Breakout EA (MQL5, 2026-06-30):
  https://www.mql5.com/en/blogs/post/772126
- Crypto scalping backtest 6 meses BTC 15m (coinquant, 2026-06-17):
  https://www.coinquant.ai/blog/crypto-scalping-strategy-backtested-6-months-of-15-minute-data-on-btc

**Repos GitHub**
- https://github.com/freqtrade/freqtrade-strategies
- https://github.com/freqtrade/freqtrade
- https://github.com/polakowo/vectorbt
- https://github.com/workprior/vectorbt-backtest
- https://github.com/sam-bateman/trading-orb
- https://github.com/vinnypt/ES-NQ-Pairs-Trading
- https://github.com/shashwat-shahi/Statistical-Arbitrage-Trading-Strategy
- https://github.com/TheoBrigitte/freqtrade
- https://gist.github.com/monomadic/cd134ec73738fc5dae9afdfdcedb7744 (Scalping Handbook)
- https://gist.github.com/AnthonyFJGarner/ccd23f0e9d46214612f59c7b92a82149 (Mean reversion)

**Comunidad / otros**
- https://strat.ninja/strats.php
- https://www.freqst.com/
- https://deepwiki.com/freqtrade/freqtrade-strategies/3.5-scalping-strategies
- https://www.freqtrade.io/en/stable/
