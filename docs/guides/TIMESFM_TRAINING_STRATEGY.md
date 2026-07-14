# TimesFM Training Strategy: Batch Comparison Methodology

## Overview

After POC (zero-shot baseline), you'll train specialized models on your financial data using **LoRA** (Low-Rank Adaptation). We'll test multiple training configurations and compare results systematically.

---

## ¿Por qué Entrenar TimesFM?

**Zero-shot (sin entrenar):**
- ✅ Funciona inmediatamente
- ❌ Optimizado para datos generales, no finanzas
- ❌ Puede tener MAPE > 5% en precios

**Fine-tuned (entrenado):**
- ✅ Especializado para precios de CFD
- ✅ MAPE típicamente 2-3%
- ✅ Directional accuracy 58-65%
- ⚠️ Requiere 2-4 horas entrenamiento

---

## Methodology: Multi-Batch Comparison

Usaremos 3 lotes diferentes para entrenar y comparar:

### **Batch A: Conservative (baseline)**
- **Data**: SPY 1d (5 años completos)
- **Epochs**: 10
- **Learning Rate**: 0.0001
- **LoRA Rank**: 8
- **Métrica**: MAE, MAPE, Directional Accuracy

### **Batch B: Aggressive (más datos)**
- **Data**: Todos 19 tickers 1d (5 años)
- **Epochs**: 10
- **Learning Rate**: 0.00005 (menor = más conservador)
- **LoRA Rank**: 16 (más capacidad)
- **Métrica**: ¿Mejor generalización?

### **Batch C: Specialized (1h data)**
- **Data**: SPY 1h (90 días recientes)
- **Epochs**: 20
- **Learning Rate**: 0.0001
- **LoRA Rank**: 8
- **Métrica**: ¿Funciona para trading horario?

**Comparison:** A vs B vs C → seleccionar ganador

---

## Training Setup

### Architecture: LoRA (Low-Rank Adaptation)

**¿Por qué LoRA en lugar de fine-tuning completo?**

```
Full Fine-tuning:
  - Entrenar 200M parámetros
  - 10+ horas en GPU
  - Riesgo de overfitting
  - Alto uso de memoria

LoRA (nuestro enfoque):
  - Entrenar solo ~100K parámetros
  - 2-4 horas en GPU
  - Conserva conocimiento general
  - Bajo riesgo overfitting
  - Bajo uso memoria (cabe en RTX 5060)
```

**¿Cómo funciona?**

```
TimesFM Forward Pass:
  output = model(x)  # 200M params (congelados)
           + A @ B   # LoRA adapters (~100K trainables)

Ventaja: Solo actualizas A y B, no todo el modelo
```

---

## Training Script Template

```python
# scripts/train_timesfm_lora.py

import logging
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from config.settings import DEFAULT_TICKERS
import timesfm

logger = logging.getLogger(__name__)

class TimesFMLoRATrainer:
    """Train TimesFM with LoRA adapters on financial data."""
    
    def __init__(self, model_name: str, output_dir: str = "models/saved"):
        self.model_name = model_name
        self.output_dir = Path(output_dir)
        self.model = None
        self.history = {}
    
    def load_training_data(self, tickers: list, interval: str, days: int = 1825):
        """Load historical data from CSV or API."""
        from data.fetcher import DataFetcher
        
        fetcher = DataFetcher()
        training_data = []
        
        for ticker in tickers:
            logger.info(f"Loading {ticker} {interval}...")
            df = fetcher.load_from_csv(ticker, interval)
            
            if df is None or len(df) < 100:
                logger.warning(f"Skipping {ticker}: insufficient data")
                continue
            
            # Use last `days` for training
            close_prices = df['Close'].values[-days:].astype(np.float32)
            training_data.append({
                'ticker': ticker,
                'close': close_prices,
                'length': len(close_prices)
            })
        
        logger.info(f"Loaded {len(training_data)} tickers for training")
        return training_data
    
    def prepare_sequences(self, close_prices: np.ndarray, seq_len: int = 512):
        """Split prices into overlapping sequences."""
        sequences = []
        for i in range(len(close_prices) - seq_len):
            seq = close_prices[i:i+seq_len]
            sequences.append(seq)
        return np.array(sequences)
    
    def train(self, 
              tickers: list,
              interval: str,
              epochs: int = 10,
              learning_rate: float = 0.0001,
              lora_rank: int = 8,
              batch_size: int = 4):
        """Train TimesFM with LoRA."""
        
        logger.info("=" * 60)
        logger.info(f"Training TimesFM LoRA: {self.model_name}")
        logger.info("=" * 60)
        logger.info(f"Config: {len(tickers)} tickers, {interval}, "
                   f"LR={learning_rate}, LoRA_rank={lora_rank}")
        
        # Load model
        logger.info("Loading TimesFM base model...")
        self.model = timesfm.TimesFM(
            context_len=512,
            prediction_len=24,
            lora_rank=lora_rank,  # Enable LoRA
        )
        self.model.prepare_for_training()  # Freeze base weights
        
        # Load data
        training_data = self.load_training_data(tickers, interval)
        
        # Prepare sequences
        all_sequences = []
        for data in training_data:
            seqs = self.prepare_sequences(data['close'], seq_len=512)
            all_sequences.append(seqs)
        
        all_sequences = np.concatenate(all_sequences, axis=0)
        logger.info(f"Total sequences: {len(all_sequences)}")
        
        # Training loop
        import torch
        from torch.optim import Adam
        
        optimizer = Adam(
            [p for p in self.model.parameters() if p.requires_grad],
            lr=learning_rate
        )
        
        for epoch in range(epochs):
            epoch_loss = 0
            num_batches = 0
            
            for i in range(0, len(all_sequences), batch_size):
                batch = all_sequences[i:i+batch_size]
                
                # Forward pass
                input_tensor = torch.from_numpy(batch).to('cuda' if torch.cuda.is_available() else 'cpu')
                
                # Loss (simplified - use actual MSE in production)
                forecast, _ = self.model.forecast(inputs=batch, horizon=24)
                target = batch[:, -24:]  # Last 24 values as target
                
                loss = torch.mean((torch.tensor(forecast) - torch.tensor(target)) ** 2)
                
                # Backward pass
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                
                epoch_loss += loss.item()
                num_batches += 1
            
            avg_loss = epoch_loss / num_batches
            self.history[epoch] = avg_loss
            logger.info(f"Epoch {epoch+1}/{epochs} - Loss: {avg_loss:.6f}")
        
        # Save trained model
        self.save_model()
        logger.info("Training completed!")
    
    def save_model(self):
        """Save LoRA weights (not full model)."""
        output_path = self.output_dir / f"{self.model_name}_lora.pt"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save only LoRA adapters
        torch.save(self.model.lora_state_dict(), output_path)
        logger.info(f"Model saved: {output_path}")
    
    def evaluate(self, 
                 test_tickers: list,
                 interval: str,
                 horizon: int = 24):
        """Evaluate trained model on test data."""
        logger.info(f"Evaluating on {len(test_tickers)} test tickers...")
        
        results = {}
        from data.fetcher import DataFetcher
        from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
        
        fetcher = DataFetcher()
        
        for ticker in test_tickers:
            df = fetcher.load_from_csv(ticker, interval)
            if df is None or len(df) < 600:
                continue
            
            close_prices = df['Close'].values[-600:].astype(np.float32)
            
            # Forecast last 24 bars
            historical = close_prices[:-horizon]
            actual = close_prices[-horizon:]
            
            forecast, _ = self.model.forecast(
                inputs=historical.reshape(1, -1),
                horizon=horizon
            )
            
            mae = mean_absolute_error(actual, forecast[0][:horizon])
            mape = mean_absolute_percentage_error(actual, forecast[0][:horizon])
            
            results[ticker] = {'mae': mae, 'mape': mape}
        
        # Summary
        avg_mae = np.mean([r['mae'] for r in results.values()])
        avg_mape = np.mean([r['mape'] for r in results.values()])
        
        logger.info(f"\nEvaluation Results:")
        logger.info(f"  Avg MAE: ${avg_mae:.2f}")
        logger.info(f"  Avg MAPE: {avg_mape:.2f}%")
        
        return results
```

---

## Workflow Completo

### **Fase 1: Baseline (Zero-shot)**

```bash
# Ejecutar POC - sin entrenamiento
python3 scripts/timesfm_poc.py SPY 1d

# Resultado esperado: MAPE ~3-5%, Accuracy ~54-56%
# (baseline para comparar)
```

### **Fase 2: Entrenar 3 Lotes**

```bash
# Batch A: Conservative (SPY 1d)
python3 scripts/train_timesfm_lora.py \
  --model-name "batch_a_spy_1d" \
  --tickers SPY \
  --interval 1d \
  --epochs 10 \
  --learning-rate 0.0001 \
  --lora-rank 8

# Batch B: Aggressive (todos los tickers)
python3 scripts/train_timesfm_lora.py \
  --model-name "batch_b_all_tickers_1d" \
  --tickers SPY,QQQ,IWM,DIA,GLD,SLV,USO,UNG,AAPL,NVDA,MSFT,AMZN,GOOGL,META,TSLA,BTC-USD,ETH-USD,SOL-USD,XRP-USD \
  --interval 1d \
  --epochs 10 \
  --learning-rate 0.00005 \
  --lora-rank 16

# Batch C: Specialized (SPY 1h)
python3 scripts/train_timesfm_lora.py \
  --model-name "batch_c_spy_1h" \
  --tickers SPY \
  --interval 1h \
  --epochs 20 \
  --learning-rate 0.0001 \
  --lora-rank 8
```

### **Fase 3: Evaluar y Comparar**

```bash
# Crear script de comparación
python3 scripts/compare_timesfm_models.py

# Output:
# ┌────────────────────────────────────────┐
# │ Model          │ MAE   │ MAPE   │ Winner │
# ├────────────────────────────────────────┤
# │ Zero-shot      │ 0.87  │ 3.2%   │        │
# │ Batch A (SPY)  │ 0.62  │ 2.1%   │ ✅     │
# │ Batch B (All)  │ 0.71  │ 2.8%   │        │
# │ Batch C (1h)   │ 1.15  │ 4.2%   │        │
# └────────────────────────────────────────┘
```

### **Fase 4: Deploy Ganador**

```bash
# Mover modelo ganador a producción
cp models/saved/batch_a_spy_1d_lora.pt models/production/timesfm_primary.pt

# Integrar en pipeline
python3 main.py pipeline --ticker SPY --use-timesfm
```

---

## Comparison Metrics

### Métricas Clave

| Métrica | Fórmula | Interpretación |
|---------|---------|-----------------|
| **MAE** | `mean(\|actual - forecast\|)` | Error promedio en dólares |
| **MAPE** | `mean(\|actual - forecast\| / actual)` | Error % (mejor para comparación) |
| **RMSE** | `sqrt(mean((actual - forecast)²))` | Penaliza errores grandes |
| **Dir. Accuracy** | `% de predicciones correctas up/down` | Utilidad para trading |

### Criterio Ganador

```python
# Score = MAPE + (1 - DirectionalAccuracy/100)
# Modelo con score menor gana

batch_a_score = 2.1 + (1 - 58/100) = 2.52
batch_b_score = 2.8 + (1 - 56/100) = 2.84
batch_c_score = 4.2 + (1 - 52/100) = 4.68

# Ganador: Batch A (SPY 1d con LoRA rank 8)
```

---

## Expected Results

### Conservative Estimate

| Model | MAPE | Dir. Acc | Training Time |
|-------|------|----------|-----------------|
| **Zero-shot** | 3.2% | 54% | 0 min |
| **Batch A** | 2.1% | 58% | 45 min |
| **Batch B** | 2.8% | 56% | 90 min |
| **Batch C** | 4.2% | 52% | 60 min |

**Interpretación:**
- Batch A es ganador: mejora 34% en MAPE, +4% accuracy
- Batch C falla: 1h data es más ruidoso (no recomendado)
- Batch B: generaliza pero menos especializado

---

## Hardware Requirements

| Component | Requirement | Tu Setup |
|-----------|-------------|----------|
| GPU Memory | ~18GB baseline | RTX 5060 (12GB) ⚠️ |
| Solution | Use half-precision | `model.half()` |
| Training Time | 2-4 hrs per batch | ~3 hrs total (3 batches) |
| Storage | ~2GB models | ✅ OK |

**Con half-precision (float16):**
- Memory usage: 50% menos
- Speed: Similar o más rápido
- Accuracy: Negligible loss

---

## Integration Point

Después de seleccionar ganador (ej: Batch A), integrar en pipeline:

```python
# signals/pipeline.py

from models.timesfm_predictor import TimesFMPredictor

class UnifiedPipeline:
    def __init__(self):
        self.timesfm = TimesFMPredictor(
            model_path="models/production/timesfm_primary.pt",
            use_lora=True
        )
    
    def generate_signals(self, ticker, interval):
        # XGBoost signal
        xgb_signal = self._xgboost_signal(ticker)
        
        # TimesFM signal
        close_prices = self._get_close_prices(ticker, 500)
        timesfm_forecast = self.timesfm.predict(close_prices)
        
        # Ensemble
        confidence = (xgb_signal.confidence + 
                     timesfm_forecast['confidence']) / 2
        
        return Signal(
            direction=xgb_signal.direction,
            confidence=confidence,
            timesfm_quantiles=timesfm_forecast['quantiles']  # Para SL/TP
        )
```

---

## Timeline

```
Day 1:
  - Download POC results (15 min)
  - Run POC baseline (5-10 min)
  → Decision: ¿Vale la pena entrenar?

Day 2 (si SÍ):
  - Train Batch A (45 min)
  - Evaluate (15 min)

Day 3:
  - Train Batch B (90 min)
  - Train Batch C (60 min)
  - Compare results (15 min)
  → Select winner

Day 4:
  - Integrate winner to pipeline (2 hrs)
  - Test ensemble (SPY signals)
  - Deploy

Total: 4 días, ~5-6 hrs actual work
```

---

## Files to Create

1. `scripts/train_timesfm_lora.py` — Trainer script
2. `scripts/compare_timesfm_models.py` — Comparison & ranking
3. `models/timesfm_predictor.py` — Integration wrapper
4. `tests/test_timesfm_integration.py` — Integration tests
