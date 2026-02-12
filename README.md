# CFD Trading System - Automated Technical Analysis & Backtesting

A Python-based **technical analysis system** for CFD trading with support for **scalping** and **swing trading** strategies. Features backtesting, LSTM price prediction, and multi-instrument support (stocks, commodities, crypto).

## 🎯 Features

✅ **Multiple Trading Strategies**
- MACD + VWAP (scalping - 1-5 min)
- RSI + Bollinger Bands (scalping)
- Moving Average Crossover (swing/weekly)

✅ **Technical Indicators**
- MACD, RSI, Bollinger Bands, EMA, SMA, VWAP, Stochastic, ADX, ATR, OBV

✅ **Machine Learning**
- LSTM neural network for price prediction
- Acts as signal filter to improve win rate
- TensorFlow Lite for mobile/Android compatibility

✅ **Backtesting**
- Historical data testing with realistic fills
- Metrics: Returns, Sharpe Ratio, Max Drawdown, Win Rate, Profit Factor
- HTML reports with equity curves

✅ **Multi-Instrument Support**
- Stocks: SPY, QQQ, AAPL, TSLA, etc.
- Commodities: Gold (GLD), Oil (USO)
- Crypto: Bitcoin, Ethereum (via Bitso/CCXT)
- Forex: EUR/USD, GBP/USD, etc.

✅ **Data Sources**
- Yahoo Finance (free, reliable)
- CCXT/Bitso for crypto
- Extensible for other brokers

## 📋 Project Structure

```
cfd-trading-system/
├── data/                    # Historical data storage
│   ├── raw/                # Downloaded OHLCV CSV files
│   └── processed/          # Cleaned and prepared data
├── strategies/             # Trading strategy implementations
│   ├── scalping/           # MACD+VWAP, RSI+BB strategies
│   └── swing/              # MA Crossover strategy
├── indicators/             # Technical indicator calculations
├── backtesting/            # Backtesting engine
├── signals/                # Signal generation logic
├── models/                 # ML models (LSTM)
│   └── saved/              # Trained model weights
├── notebooks/              # Jupyter notebooks for analysis
├── tests/                  # Unit tests
├── config/                 # Configuration files
├── logs/                   # Trading logs and signals
├── requirements.txt        # Python dependencies
├── README.md              # This file
└── main.py                # CLI entry point
```

## 🚀 Quick Start

### Installation

1. **Clone the repository**:
```bash
git clone https://github.com/<your-username>/cfd-trading-system.git
cd cfd-trading-system
```

2. **Create virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure settings**:
Edit `config/settings.py` with your tickers and parameters.

### Usage

**Download historical data**:
```bash
python main.py fetch-data --ticker SPY --interval 1m --days 30
```

**Run backtesting**:
```bash
python main.py backtest --strategy macd_vwap --ticker SPY --interval 1m
```

**Generate live signals**:
```bash
python main.py signal --strategy macd_vwap --ticker SPY
```

**Train LSTM model**:
```bash
python main.py train-lstm --ticker SPY --epochs 50
```

## 📊 Strategies

### 1. MACD + VWAP (Scalping)
- **Timeframe**: 1-5 minutes
- **Entry**: MACD crosses above signal line + price above VWAP
- **Exit**: MACD crosses below OR 1% profit target
- **Stop Loss**: 0.5% below entry

### 2. RSI + Bollinger Bands (Scalping)
- **Timeframe**: 1-5 minutes
- **Entry**: RSI < 30 (oversold) + touches lower BB
- **Exit**: RSI > 70 OR touches upper BB
- **Stop Loss**: 0.7% below entry

### 3. Moving Average Crossover (Swing)
- **Timeframe**: Daily
- **Entry**: Golden Cross (SMA50 > SMA200)
- **Exit**: Death Cross (SMA50 < SMA200)
- **Stop Loss**: 2% below entry

## 🤖 LSTM Model

The LSTM model predicts next price movement using 60-minute lookback window and multiple features:
- OHLCV data
- Technical indicators (RSI, MACD, BB, ATR)
- Volume indicators

The predictions act as a **filter** for technical signals:
- Only take signals when LSTM predicts favorable movement
- Significantly improves win rate

## 📈 Backtesting Results

Example output after backtest:
```
CFD Trading System Backtesting Results
=====================================
Strategy: MACD_VWAP
Ticker: SPY
Period: 2024-01-01 to 2026-02-12

Total Return: 24.5%
Sharpe Ratio: 1.85
Max Drawdown: 8.2%
Win Rate: 62.3%
Total Trades: 145
Profit Factor: 2.1
```

## 🔧 Configuration

Edit `config/settings.py`:

```python
# Instruments to analyze
TICKERS = {
    'indices': ['SPY', 'QQQ'],
    'commodities': ['GLD', 'USO'],
    'crypto': ['BTC-USD', 'ETH-USD']
}

# Trading parameters
INITIAL_CAPITAL = 10000
RISK_PER_TRADE = 0.02  # 2%

# Strategy parameters
MACD_PARAMS = {'fast': 12, 'slow': 26, 'signal': 9}
RSI_PARAMS = {'period': 14, 'overbought': 70, 'oversold': 30}
```

## 📚 Documentation

- [Strategy Details](./STRATEGIES.md)
- [LSTM Model Guide](./LSTM_GUIDE.md)
- [API Reference](./API.md)

## 🧪 Testing

Run unit tests:
```bash
pytest tests/
```

## ⚠️ Important Notes

1. **Backtesting ≠ Live Trading**: Past performance does not guarantee future results
2. **Risk Management**: Always use stop losses and position sizing
3. **Plus500 Integration**: Currently manual execution. API integration possible with other brokers
4. **Paper Trading**: Test signals in paper trading before using real capital

## 🔐 Security

- Never commit API keys (use `.env` file)
- Store Bitso/broker credentials in environment variables
- Add `.env` to `.gitignore`

Example `.env`:
```
BITSO_API_KEY=your_key_here
BITSO_API_SECRET=your_secret_here
```

## 🛠️ Future Enhancements

- [ ] Real-time data streaming
- [ ] Broker API integration (OANDA, Interactive Brokers)
- [ ] Advanced ML models (Transformer, Ensemble methods)
- [ ] Portfolio optimization
- [ ] Risk analysis dashboard
- [ ] Telegram/Discord alerts

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## 📄 License

MIT License - see LICENSE file

## 📧 Contact

For questions or suggestions, open an issue on GitHub.

---

**Status**: MVP (Minimum Viable Product) - Version 1.0
**Last Updated**: February 2026
**Maintained By**: Your Name
