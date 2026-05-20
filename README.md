# CFD Trading System

Sistema automático de trading para CFDs con señales técnicas + ML (XGBoost cross-sectional), paper trading en Alpaca, y notificaciones Telegram.

**Estado**: Producción. 16 comandos CLI. 47 tests. Cron activo 24/7.

---

## ¿Qué hace?

```
Cron cada hora
   ↓
Yahoo Finance → datos frescos de 10 tickers
   ↓
Indicadores técnicos (21) + features engineered (4)
   ↓
3 estrategias generan señales BUY/SELL + SL + TP
   ↓
XGBoost cross-sectional vota (80-84% test accuracy)
   ↓
Confluence scoring (1-5 estrellas)
   ↓
Telegram: señales con 3+ estrellas → tu teléfono
   ↓
Alpaca Paper: bracket orders automáticos (entry + SL + TP)
   ↓
Paper dashboard: P&L, win rate, equity curve
```

---

## Inicio Rápido

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Ver estado
python3 main.py status

# Pipeline completo (señales + Telegram)
python3 main.py pipeline --telegram

# Paper trading (señales + ejecución automática en sandbox)
python3 main.py paper-trade --dry-run          # Simular sin ejecutar
python3 main.py paper-trade                    # Ejecutar en vivo
python3 main.py paper-status                   # Ver cuenta y posiciones
python3 main.py paper-history                  # Historial de trades y P&L
```

---

## Comandos

| Comando | Descripción |
|---------|-------------|
| `pipeline` | Pipeline unificado: datos → indicadores → estrategias → ML → Telegram |
| `paper-trade` | Pipeline + ejecución automática en Alpaca paper (bracket orders) |
| `paper-status` | Estado de cuenta paper: equity, posiciones, órdenes pendientes |
| `paper-history` | Historial de trades cerrados: win rate, P&L, profit factor |
| `paper-close` | Cerrar posición(es) paper |
| `signal` | Generar una señal individual |
| `scan` | Escanear múltiples tickers y estrategias |
| `watch` | Monitoreo continuo con horarios de mercado |
| `backtest` | Backtesting con VectorBT |
| `train-lstm` | Entrenar modelo LSTM+Transformer (legacy) |
| `train-xgb-cross` | Entrenar XGBoost cross-sectional (todos los tickers juntos) |
| `fetch-data` | Descargar datos OHLCV |
| `fetch-all-history` | Descargar historial extendido (5 años diario, 2 años horario) |
| `list-strategies` | Listar estrategias disponibles |
| `list-tickers` | Listar tickers configurados |
| `status` | Estado del sistema |

---

## Estrategias

| Estrategia | Tipo | Entrada | SL | TP |
|-----------|------|---------|-----|-----|
| `macd_vwap` | Trend-following | MACD cross + VWAP filter | 0.5% | 1% |
| `rsi_bb` | Mean-reversion | RSI extreme + BB touch | 0.7% | BB middle |
| `ma_crossover` | Swing | SMA 50/200 golden cross | 2% | 3% |

Todas soportan filtro de tendencia (ADX ≥ 20) y SL/TP dinámico basado en ATR.

---

## ML: XGBoost Cross-Sectional

| | 1d | 1h |
|---|-----|-----|
| Modelo | XGBoost (200 trees, depth=5) | XGBoost (200 trees, depth=5) |
| Entrenamiento | Cross-sectional (7 tickers) | Cross-sectional (7 tickers) |
| Samples train | 4,890 | 3,962 |
| Features | 13 (OHLCV + indicadores + engineered) | 13 |
| Labels | Binary threshold (≥0.5% move) | Binary threshold (≥0.5% move) |
| Test accuracy | 74.4% | 84.4% |

**LSTM+Transformer** (legacy): disponible como fallback vía `PRIMARY_ML_MODEL='lstm'` en config.

---

## Confluence Scoring (1-5 estrellas)

| Estrellas | Significado |
|-----------|-------------|
| 1★ | Señal BUY/SELL en al menos 1 timeframe |
| 2★ | Multi-timeframe agreement **o** ML confirma |
| 3★ | ML confirma **y** (multi-TF **o** ML >65% confianza) |
| 4★ | Ensemble STRONG consensus |
| 5★ | Confianza promedio ≥70% |

**Cron actual**: solo tradea y notifica señales con 3+ estrellas.

---

## Setup Alpaca Paper Trading

1. Crear cuenta gratis en https://alpaca.markets
2. Obtener API keys del dashboard
3. Agregar a `.env`:
```bash
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
ALPACA_PAPER_URL=https://paper-api.alpaca.markets
```

---

## Cron (automático)

```
0 * * * *   run_paper_trade.sh    # Cada hora: pipeline + trade + Telegram
0 0 * * 0   reset_paper.sh        # Domingo: cerrar todas las posiciones
```

---

## Documentación

| Documento | Contenido |
|-----------|-----------|
| `docs/guides/INTEGRATION_SUMMARY.md` | Arquitectura completa del sistema |
| `docs/reference/ML_RESEARCH.md` | Bibliografía ML: 8 papers + 2 libros |
| `docs/analysis/SESSION_2026-05-19.md` | Changelog de la sesión de auditoría |
| `docs/quickstart/GUIA_COMPLETA.md` | Guía completa en español |

---

## Tests

```bash
pytest tests/ -v    # 47 tests, todos pasan
```

---

## ⚠️ Disclaimer

CFDs conllevan riesgo extremo. Paper trading en Alpaca usa dinero virtual. No tradees dinero real sin validar estadísticas.

---

*Última actualización: 2026-05-20*
