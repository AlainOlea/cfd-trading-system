# CFD Trading System

Sistema de trading para CFDs con señales técnicas + ML (XGBoost cross-sectional + TimesFM),
ejecutado en **paper trading** (dinero simulado) en Alpaca, con notificaciones por Telegram.

**Estado**: Paper trading activo. 16 comandos CLI. 147 tests. Automatizado vía Windows Task
Scheduler (Lun-Vie, horario de mercado — no es cron, no corre 24/7). Ver `CLAUDE.md` para el
detalle completo de arquitectura y configuración; este README es solo un punto de entrada rápido.

---

## ¿Qué hace?

```
Windows Task Scheduler (hourly + daily jobs, Lun-Vie horario de mercado)
   ↓
Alpaca Data API (incremental, solo velas nuevas) → 19 tickers
   fallback: Yahoo Finance si Alpaca no responde
   ↓
Indicadores técnicos (21 vía pandas-ta) + 4 features engineered
   ↓
3 estrategias generan señales BUY/SELL + SL/TP (cada una con su propio filtro de régimen ADX)
   ↓
XGBoost cross-sectional filtra/valida la señal técnica
   ↓
TimesFM (zero-shot, forecast a 1min) valida de nuevo en 1m/1h — suma una estrella si coincide
   ↓
Confluence scoring (0-5 estrellas)
   ↓
Telegram: señales con 3+ estrellas → notificación al teléfono
   ↓
Alpaca Paper: bracket orders automáticos (entry + SL + TP)
   ↓
paper-status / paper-history: P&L, win rate, posiciones (en terminal, no hay dashboard web)
```

---

## Inicio Rápido

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# TimesFM depende de PyTorch y no está en requirements.txt (paquete pesado, opcional
# de instalar si solo querés correr el resto del sistema) — sin esto, el pipeline
# sigue funcionando pero salta el paso de validación TimesFM silenciosamente:
pip install 'timesfm[torch]'

# Configurar Alpaca (paper trading) y Telegram en .env — ver .env.example
cp .env.example .env

# Ver estado
python3 main.py status

# Pipeline completo (señales + Telegram)
python3 main.py pipeline --telegram

# Paper trading (señales + ejecución automática en sandbox)
python3 main.py paper-trade --dry-run          # Simular sin ejecutar
python3 main.py paper-trade                    # Ejecutar en vivo (paper, no dinero real)
python3 main.py paper-status                   # Ver cuenta y posiciones
python3 main.py paper-history                  # Historial de trades y P&L
```

---

## Comandos

| Comando | Descripción |
|---------|-------------|
| `pipeline` | Pipeline unificado: datos → indicadores → estrategias → ML → TimesFM → Telegram |
| `paper-trade` | Pipeline + ejecución automática en Alpaca paper (bracket orders) |
| `paper-status` | Estado de cuenta paper: equity, posiciones, órdenes pendientes |
| `paper-history` | Historial de trades cerrados: win rate, P&L, profit factor |
| `paper-close` | Cerrar posición(es) paper |
| `signal` | Generar una señal individual (solo técnico, sin ML — debug de un ticker) |
| `scan` | Escanear múltiples tickers y estrategias |
| `watch` | Monitoreo continuo con horarios de mercado |
| `backtest` | Backtesting con VectorBT |
| `train-xgb-cross` | Entrenar XGBoost cross-sectional (todos los tickers juntos — único modelo ML soportado) |
| `fetch-data` | Descargar datos OHLCV |
| `fetch-1min-history` | Descargar histórico 1min (hasta 3 años, Alpaca API) |
| `fetch-all-history` | Descargar historial extendido (5 años diario, 2 años horario) |
| `list-strategies` | Listar estrategias disponibles |
| `list-tickers` | Listar tickers configurados |
| `status` | Estado del sistema |

---

## Estrategias

| Estrategia | Tipo | Entrada | SL | TP | Filtro de régimen |
|-----------|------|---------|-----|-----|-----|
| `macd_vwap` | Scalping (momentum) | MACD cross + VWAP filter | 0.5% | 1% | ADX ≥ 20 (necesita tendencia) |
| `rsi_bb` | Scalping (mean-reversion) | RSI extreme + BB touch | 0.7% | BB middle | ADX < 20 (necesita rango, no tendencia) |
| `ma_crossover` | Swing | SMA 50/200 golden cross | 2% | 3% | Ninguno |

SL/TP dinámico basado en ATR existe como capacidad en `BaseStrategy` (`use_atr_sl`) pero
ninguna estrategia lo tiene activado hoy — todas usan porcentajes fijos.

---

## ML: XGBoost Cross-Sectional + TimesFM

Un modelo XGBoost entrenado sobre los 19 tickers configurados pooled juntos (cross-sectional,
no un modelo por ticker), con labels de threshold binario (≥0.5% de movimiento). TimesFM 2.5
(zero-shot, sin fine-tuning) corre después como validador adicional en 1m/1h.

> LSTM+Transformer fue retirado por completo (ver `docs/archive/ML_RETRAINING*.md`) — XGBoost
> es el único modelo ML soportado hoy.

Las cifras de accuracy cambian con cada reentrenamiento y hay más de un snapshot en los docs
(`docs/reference/ML_RESEARCH.md`, `docs/analysis/SYSTEM_AUDIT_GUIDE.md`) — consultar esos
archivos para el número vigente en vez de confiar en una cifra fija acá.

---

## Confluence Scoring (0-5 estrellas)

| Estrella | Se suma si... |
|-----------|-------------|
| 1★ | Hay al menos una señal BUY/SELL accionable |
| 2★ | Multi-timeframe agreement **o** XGBoost confirma la dirección |
| 3★ | XGBoost confirma **y** (multi-TF agreement **o** confianza ML > 65%) |
| 4★ | Confianza promedio de las señales accionables ≥ 70% |
| 5★ | TimesFM coincide en dirección (solo aplica en 1m/1h, post-procesamiento) |

`paper-trade` solo tradea y notifica señales con 3+ estrellas y confianza ≥60% (ambos
configurables vía `--min-confluence`/`--min-confidence`).

---

## Setup Alpaca Paper Trading

1. Crear cuenta gratis en https://alpaca.markets
2. Obtener API keys **de paper trading** del dashboard
3. Agregar a `.env` (ver `.env.example`):
```bash
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
```

---

## Automatización (Windows Task Scheduler)

No es cron — corre en Windows vía Task Scheduler, invocando `main.py paper-trade` dentro de
WSL. Los scripts (`run_paper_hourly.ps1`, `run_paper_daily.ps1`, `setup_tasks.ps1`, raíz del
repo) están cableados a tareas reales del sistema — no renombrarlos ni moverlos.

| Task | Horario | Órdenes |
|------|---------|---------|
| `CFD Paper Hourly` | Lun-Vie, 07:00-15:59 ET, cada hora | DAY (SL 0.5%, TP 1%) |
| `CFD Paper Daily` | Lun-Vie, 07:00 ET, una vez al día | GTC (SL 1.5%, TP 3%) |

Esta automatización corre en una sola máquina sin redundancia — si se apaga o se suspende
Windows, no hay failover. Ver `CLAUDE.md` → "Paper Trading Automation" para el detalle.

---

## Documentación

| Documento | Contenido |
|-----------|-----------|
| `CLAUDE.md` (raíz) | Arquitectura completa, setup, comandos, decisiones de diseño — punto de entrada canónico |
| `docs/README.md` | Navegación completa de toda la documentación |
| `docs/reference/MODULES_API.md` | API detallada de cada módulo |
| `docs/reference/ML_RESEARCH.md` | Bibliografía ML: 8 papers + 2 libros, decisiones de modelado |
| `docs/analysis/SYSTEM_AUDIT_GUIDE.md` | Evaluación del approach de riesgo, estilo asesor financiero |

---

## Tests

```bash
pytest tests/ -v    # 147 tests, todos pasan
```

---

## ⚠️ Disclaimer

CFDs conllevan riesgo extremo. Este sistema corre en **paper trading en Alpaca (dinero
virtual)** — no hay capital real en juego. No tradees dinero real sin validar estadísticas
extensamente y entender que resultados en paper no garantizan resultados en vivo (slippage,
delay de datos de 15min en el free tier, y liquidez real son distintos).

---

*Última actualización: 2026-07-13*
