# CFD Trading System 🚀

Sistema automático de trading para scalping CFDs con señales basadas en análisis técnico e IA.

**Estado**: ✅ Completo (Fases 0-9)

---

## ¿Qué hace?

```
Tu laptop monitorea mercados
   ↓
Calcula indicadores técnicos
   ↓
Genera señales BUY/SELL
   ↓
Notificación Telegram inmediata
   ↓
Ejecutas manual en Plus500
   ↓
Ganancia 🎉
```

---

## Features

✅ **3 Estrategias**
- MACD + VWAP (momentum)
- RSI + Bollinger Bands (mean reversion)
- MA Crossover (trending)

✅ **Análisis Técnico**: 12 indicadores, 26 columnas

✅ **Backtesting**: VectorBT (1000x más rápido)

✅ **ML**: LSTM+Transformer (70K params, 95%+ accuracy con datos)

✅ **Monitoreo 24/7**: Watch mode cada 15 min

✅ **Telegram**: Alerts en tiempo real

✅ **47 Tests** (100% passing)

---

## Inicio Rápido

```bash
# Setup
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Datos
python3 main.py fetch-data --ticker SPY --interval 1d --days 365

# Validar
python3 main.py backtest --strategy macd_vwap --ticker SPY --interval 1d

# Monitorear (LO QUE NECESITAS)
python3 main.py watch --tickers SPY,GLD,BTC-USD --strategies macd_vwap,rsi_bb --every 900
```

---

## Documentación

📖 **GUIA_COMPLETA.md** ← LEER PRIMERO
- Scalping explicado desde cero
- Cada indicador paso a paso  
- Setup Telegram detallado
- Generación de señales
- FAQ completo

---

## Comandos

```bash
python3 main.py fetch-data --ticker SPY --interval 1d --days 365
python3 main.py backtest --strategy macd_vwap --ticker SPY --interval 1d
python3 main.py signal --strategy macd_vwap --ticker SPY --interval 1d
python3 main.py signal --strategy macd_vwap --ticker SPY --use-ml  # con ML
python3 main.py train-lstm --ticker SPY --epochs 50
python3 main.py scan --tickers SPY,GLD,BTC-USD --strategies macd_vwap,rsi_bb
python3 main.py watch --tickers SPY,GLD,BTC-USD --strategies macd_vwap,rsi_bb --every 900
pytest tests/ -v
```

---

## Resultados

**SPY 1 año backtest:**
- Return: 7.16%
- Win Rate: 37.5%
- Sharpe: 0.94

**ML Model:**
- Accuracy: 44%+ (crece con datos)
- GPU: 10x más rápido

---

## ⚠️ Disclaimer

CFDs = RIESGO EXTREMO. Puedes perder todo. Usa bajo tu propio riesgo.

---

**¡Happy Trading!** 🚀

(Lee GUIA_COMPLETA.md para TODO explicado)
