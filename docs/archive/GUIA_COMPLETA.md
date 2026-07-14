> **ARCHIVADO** — describe `live_signals.py`/`scripts/improve_best_models.py` como flujo
> principal y "10 comandos" (hoy son 17+). Superseded por `main.py` + XGBoost + TimesFM. Solo
> referencia histórica — para empezar hoy, ver `CLAUDE.md` (sección "Setup Commands").

# Guía Completa: CFD Trading System

## Tabla de Contenidos
1. [Escalping: Conceptos Fundamentales](#escalping-conceptos)
2. [Las 3 Estrategias del Sistema](#estrategias)
3. [Cómo Usar el Proyecto](#uso)
4. [Análisis Técnico Explicado](#analisis-tecnico)
5. [Generación de Señales](#generacion-senales)
6. [Telegram Bot Setup](#telegram-setup)
7. [Flujo Completo Step-by-Step](#flujo-completo)
8. [FAQ](#faq)

---

## <a name="escalping-conceptos"></a> 1. Escalping: Conceptos Fundamentales

### ¿Qué es Scalping?

**Scalping** es una estrategia de trading a corto plazo donde:
- Entras y sales en minutos (no horas/días)
- Buscas ganancias pequeñas pero frecuentes: 0.5% - 2% por trade
- Aprovechas movimientos rápidos del mercado
- Usas mucho apalancamiento (CFDs permiten esto)

### Ventajas
✅ Menos exposición a riesgo (posiciones cortas)
✅ Muchas oportunidades por día
✅ No necesitas esperar a tendencias largas
✅ Ideal para mercados volátiles

### Desventajas
❌ Requiere atención constante o automatización
❌ Comisiones/spreads comen ganancias
❌ Requiere disciplina emocional
❌ Necesitas reacción rápida

### Tu Setup Recomendado
```
Laptop en casa con:
- Watch mode corriendo 24/7 (si está en WSL2 siempre conectada)
- Telegram activo para recibir alertas
- Plus500 abierto para ejecutar manualmente (CFDs)
- Para crypto: solo señales (no ejecutas automático)
```

---

## <a name="estrategias"></a> 2. Las 3 Estrategias del Sistema

### Estrategia 1: MACD + VWAP (Scalping - 1-15 min)

**Indicadores usados:**
- **MACD**: captura cambios de momentum
- **VWAP**: soporte/resistencia dinámico basado en volumen

**Lógica:**
```
ENTRY LONG:
  ✓ MACD cruza por ENCIMA de su línea de señal (momentum alcista)
  ✓ Precio ARRIBA del VWAP (tendencia al alza)
  → Entra LONG (compra CFD)

ENTRY SHORT:
  ✓ MACD cruza por DEBAJO de su línea de señal (momentum bajista)
  ✓ Precio DEBAJO del VWAP (tendencia a la baja)
  → Entra SHORT (venta CFD)

EXIT (toma ganancias):
  - TP (Take Profit): 1% de ganancia
  - SL (Stop Loss): 0.5% de pérdida
```

**Cuándo usar:**
- Mercados trending (no laterales)
- Volatilidad media
- Ideal para SPY, BTC, oro

---

### Estrategia 2: RSI + Bollinger Bands (Scalping - 1-5 min)

**Indicadores usados:**
- **RSI**: detecta sobrecompra/sobreventa
- **BB**: bandas que muestran niveles extremos

**Lógica:**
```
ENTRY LONG (mean reversion - vuelta al promedio):
  ✓ RSI < 30 (sobreventa - precio muy bajo)
  ✓ Precio TOCA Banda Inferior de Bollinger
  → Esperamos vuelta al alza
  → TP = Bollinger Middle Band (media móvil)

ENTRY SHORT (mean reversion):
  ✓ RSI > 70 (sobrecompra - precio muy alto)
  ✓ Precio TOCA Banda Superior de Bollinger
  → Esperamos caída
  → TP = Bollinger Middle Band

EXIT:
  - TP: cuando toca la media
  - SL: 0.7% de pérdida
```

**Cuándo usar:**
- Mercados laterales/rango
- Cuando ves picos extremos
- Oro y índices son mejores

---

### Estrategia 3: MA Crossover (Swing Trading - 1h/1d)

**Indicadores usados:**
- **SMA50**: media móvil corta
- **SMA200**: media móvil larga

**Lógica:**
```
ENTRY LONG (Golden Cross):
  ✓ SMA50 cruza ARRIBA de SMA200
  → Señal de cambio de tendencia alcista
  → Entra LONG

ENTRY SHORT (Death Cross):
  ✓ SMA50 cruza DEBAJO de SMA200
  → Señal de cambio de tendencia bajista
  → Entra SHORT

EXIT:
  - SL: 2% de pérdida
  - TP: 3% de ganancia
```

**Cuándo usar:**
- Tendencias claras (no scalping rapido)
- Trades más largas (horas)
- Mejor para daily

---

## <a name="uso"></a> 3. Cómo Usar el Proyecto

### Setup Inicial (una sola vez)

```bash
# 1. Activar virtual environment
source venv/bin/activate

# 2. Crear archivo .env con credenciales
cp .env.example .env
# Editar .env y agregar (opcional pero recomendado):
# TELEGRAM_BOT_TOKEN=tu_token_de_bot
# TELEGRAM_CHAT_ID=tu_chat_id
```

### Flujo Típico de Uso

#### Opción A: Día 1 - Backtest (validar estrategia)
```bash
# Descargar 1 año de datos
python3 main.py fetch-data --ticker SPY --interval 1d --days 365

# Testear estrategia sobre datos históricos
python3 main.py backtest --strategy macd_vwap --ticker SPY --interval 1d

# Verás:
# - Total Return: 7.16%
# - Win Rate: 37.5%
# - Sharpe Ratio: 0.94
# - HTML report en results/
```

#### Opción B: Día 2 - Senal Única
```bash
# Obtener senal actual para un ticker
python3 main.py signal --strategy macd_vwap --ticker SPY --interval 1d

# Output:
# ==================================================
#   SIGNAL: BUY
#   Entry:  $690.50
#   SL:     $689.00
#   TP:     $696.50
#   Confidence: 85%
# ==================================================
```

#### Opción C: Día 3+ - Monitoreo Continuo (RECOMENDADO)
```bash
# Corre continuamente, monitorea multiples tickers
python3 main.py watch \
  --tickers SPY,GLD,BTC-USD \
  --strategies macd_vwap,rsi_bb \
  --interval 15m \
  --every 900

# Cada 15 minutos:
# - Revisa 3 tickers
# - Aplica 2 estrategias cada uno (6 análisis)
# - Solo muestra BUY/SELL (filtra HOLD)
# - Envía Telegram si hay senal
```

#### Opción D: Escaneo Multi-Ticker
```bash
# Chequea todo de una vez
python3 main.py scan \
  --tickers SPY,GLD,BTC-USD,AAPL,MSFT \
  --strategies macd_vwap,rsi_bb \
  --interval 1h

# Output: todas las señales BUY/SELL encontradas
```

### Entrenar Modelo ML (Opcional - mejora accuracy)

```bash
# Entrenar híbrido LSTM+Transformer con 1 año de datos
python3 main.py train-lstm --ticker SPY --epochs 50

# Luego usar el filtro:
python3 main.py signal --strategy macd_vwap --ticker SPY --use-ml

# El modelo dirá: "Esta senal tiene 85% probabilidad de acertar"
# y la rechaza si probabilidad < 80%
```

---

## <a name="analisis-tecnico"></a> 4. Análisis Técnico Explicado

### MACD (Moving Average Convergence Divergence)

**¿Qué es?**
- Compara 2 promedios móviles (12 días rápido, 26 días lento)
- Detecta cambios de momentum (velocidad del precio)

**Cómo leerlo:**
```
Línea MACD (azul):       promedio móvil rápido - lento
Línea Signal (roja):     promedio suave de MACD
Histogram (barras):      diferencia MACD - Signal

Si MACD > Signal:  momentum POSITIVO (comprar)
Si MACD < Signal:  momentum NEGATIVO (vender)
```

**En el gráfico:**
```
              Precio sube
                  ↑
         ╱────────┘
        ╱
       ╱  ← MACD también sube
      ╱
     ╱____

Cuando MACD sube pero precio baja = DIVERGENCIA = advertencia
```

---

### RSI (Relative Strength Index)

**¿Qué es?**
- Mide qué tan fuerte/débil es el movimiento (0-100)
- Detecta cuando precio se fue demasiado lejos

**Niveles clave:**
```
RSI > 70:  SOBRECOMPRA (precio muy alto, posible caída)
RSI < 30:  SOBREVENTA (precio muy bajo, posible alza)
30-70:     ZONA NORMAL (puede ir en cualquier dirección)
```

**Estrategia mean reversion:**
```
Precio muy bajo (RSI < 30)
        ↓
Activa compra automática
        ↓
Precio rebota al promedio
        ↓
Vendes ganancia 0.5-1%
```

---

### Bollinger Bands

**¿Qué son?**
- 3 líneas alrededor del precio:
  - **Banda Superior**: resistencia (techo)
  - **Banda Media**: promedio (soporte/resistencia)
  - **Banda Inferior**: soporte (piso)

**La teoría:**
```
Precio NORMAL: oscila entre bandas
Precio EXTREMO: toca banda superior/inferior
→ Tiende a volver a la media (mean reversion)
```

**En el gráfico:**
```
     ═══════════════ Banda Superior

              Precio aquí
             (zona normal)

     ─────────────── Banda Media

              Precio aquí
             (toca banda)
     ═══════════════ Banda Inferior

Si precio toca Inferior + RSI < 30 = FUERTE COMPRA
```

---

### VWAP (Volume Weighted Average Price)

**¿Qué es?**
- Precio promedio ponderado por volumen
- Muestra el "precio justo" según volumen

**Interpretación:**
```
Si precio > VWAP:  mercado está ALCISTA (arriba del promedio)
Si precio < VWAP:  mercado está BAJISTA (abajo del promedio)

Es como el "equilibrio" del mercado
Cuando se rompe = movimiento fuerte
```

---

### Media Móviles (SMA)

**¿Qué son?**
- Promedio del precio en últimos N días
- SMA50 = promedio últimos 50 días
- SMA200 = promedio últimos 200 días

**Señales:**
```
SMA50 > SMA200:  TENDENCIA ALCISTA (cruza hacia arriba)
SMA50 < SMA200:  TENDENCIA BAJISTA (cruza hacia abajo)

Se usan para trading swing (horas/días), no scalping
```

---

## <a name="generacion-senales"></a> 5. Generación de Señales

### Pipeline Completo

```
1. DESCARGA DATOS FRESCOS
   ↓
   Última hora/día del precio

2. CALCULA INDICADORES
   ↓
   MACD, RSI, Bollinger, VWAP, SMA, etc.

3. APLICA ESTRATEGIA
   ↓
   Revisa condiciones de entrada

4. GENERA SENAL
   ↓
   Signal: BUY/SELL/HOLD
   Entry Price: precio actual
   Stop Loss: precio máximo pérdida
   Take Profit: precio mínimo ganancia
   Confidence: 0-100% qué tan segura es

5. FILTRO ML (opcional)
   ↓
   Modelo LSTM+Transformer predice
   Si probabilidad < 80%: rechaza senal

6. ENVIA TELEGRAM + LOGUEA
   ↓
   Si BUY/SELL: notificación inmediata
   CSV log guarda historial
```

### Significado de Confidence (Confianza)

```
Confidence = qué tan fuerte es la senal

0-30%:   MUY DÉBIL (evita)
30-60%:  DÉBIL (ten cuidado)
60-80%:  FUERTE (buena oportunidad)
80-100%: MUY FUERTE (excelente)
```

**Cómo se calcula por estrategia:**

**MACD+VWAP:**
- Basada en qué tan lejos está MACD de la línea signal
- Si histogram grande = confianza alta

**RSI+BB:**
- Basada en distancia de RSI a 50
- Si RSI 10 o 90 = confianza alta

**MA Crossover:**
- Basada en ángulo del cruce
- Cruce abrupto = confianza alta

---

### Risk/Reward Ratio

```
Entry:  $100
SL:     $99.50  (riesgo = $0.50)
TP:     $101.00 (recompensa = $1.00)

Ratio: 1.00 / 0.50 = 2.0
Significa: por cada $1 que riesgas, ganas $2

Ratio 1:1 = breakeven si aciertas 50%
Ratio 1:2 = ganas si aciertas > 33%
Ratio 1:3 = ganas si aciertas > 25%
```

---

## <a name="telegram-setup"></a> 6. Telegram Bot Setup

### Paso 1: Crear Bot con @BotFather

```
1. En Telegram:
   - Busca "BotFather"
   - Abre chat

2. Envía comando:
   /newbot

3. Sigue instrucciones:
   - Nombre: "CFD Trading Alerts"
   - Username: "cfd_trading_alerts_bot" (debe ser único)

4. BotFather te da el TOKEN:
   "5123456789:ABCdefGHIjklmNOpqrstUVwxyz1234567890"

5. COPIA ESTE TOKEN (necesitarás en paso 3)
```

### Paso 2: Obtener tu Chat ID

```
1. Busca tu bot en Telegram
   (usuario @cfd_trading_alerts_bot)

2. Envía cualquier mensaje
   (ej: "test")

3. En terminal/navegador:
   curl "https://api.telegram.org/bot5123456789:ABCdefGHIjklmNOpqrstUVwxyz/getUpdates"

4. Verás respuesta con tu chat_id:
   {
     "ok": true,
     "result": [
       {
         "message": {
           "chat": {
             "id": 123456789,
             ...
           }
         }
       }
     ]
   }

5. COPIA TU CHAT_ID: 123456789
```

### Paso 3: Configurar el Proyecto

```bash
# 1. Editar .env
nano .env

# 2. Agregar:
TELEGRAM_BOT_TOKEN=5123456789:ABCdefGHIjklmNOpqrstUVwxyz1234567890
TELEGRAM_CHAT_ID=123456789

# 3. Editar config/settings.py
nano config/settings.py

# 4. Cambiar:
TELEGRAM_ALERTS_ENABLED = False
# por:
TELEGRAM_ALERTS_ENABLED = True

# 5. Guardar y listo
```

### Paso 4: Test

```bash
python3 main.py signal --strategy macd_vwap --ticker SPY --interval 1d

# Deberías recibir notificación en Telegram
# (si hay senal BUY/SELL, HOLD no envía)
```

### Ejemplo de Notificación

```
🟢 BUY - SPY
Strategy: macd_vwap (1d)

Entry:   $690.50
SL:      $689.00
TP:      $696.50
R/R:     2.0
Conf:    85%

2026-02-12 15:30:45
```

---

## <a name="flujo-completo"></a> 7. Flujo Completo Step-by-Step

### Escenario Real: Tu Primera Operación

#### 1️⃣ Lunes 9:00 AM - Setup

```bash
# Descargar datos históricos (una sola vez)
python3 main.py fetch-data --ticker SPY --interval 1d --days 365
python3 main.py fetch-data --ticker GLD --interval 1d --days 365
python3 main.py fetch-data --ticker BTC-USD --interval 1h --days 90

# Hacer backtest para validar
python3 main.py backtest --strategy macd_vwap --ticker SPY --interval 1d

# Si resultado bueno (>5% return), proceder
```

#### 2️⃣ Lunes 15:00 - Watch Mode Iniciado

```bash
# Correr en una terminal (se queda corriendo)
python3 main.py watch \
  --tickers SPY,GLD,BTC-USD \
  --strategies macd_vwap,rsi_bb \
  --interval 15m \
  --every 900

# Output cada 15 minutos:
--- Scan #1 at 15:00:00 UTC ---
   SPY (indices): BUY signal @ $690.50 (conf: 85%)
   GLD (commodities): HOLD
   BTC-USD (crypto): SELL signal @ $66900 (conf: 72%)
   Next scan in 900s...
```

#### 3️⃣ Telegram Notificación (inmediata)

```
🟢 BUY - SPY
Entry: $690.50 | SL: $689.00 | TP: $696.50
Conf: 85% | R/R: 2.0

🔴 SELL - BTC-USD
Entry: $66900 | SL: $67500 | TP: $65900
Conf: 72% | R/R: 4.0
```

#### 4️⃣ Lunes 15:05 - Ejecutar Manual en Plus500

```
1. Abres Plus500 app
2. Ves notificación de Telegram
3. SPY: BUY @ $690.50
   - Abres posición LONG (compra CFD)
   - SL: $689.00
   - TP: $696.50
4. BTC-USD: SELL @ $66900
   - Abres posición SHORT (venta CFD)
   - SL: $67500
   - TP: $65900
```

#### 5️⃣ Lunes 15:30 - Resultado

```
SPY: Sube a $693.50
 → Ganancia: $3.00 (0.43% ≈ $43 en lote de 100)
 → ¡CLOSE manual a $693!

BTC: Baja a $65950
 → Ganancia: $950 (1.4% ≈ ganancia)
 → ¡CLOSE manual a $65950!

Total: +$993 ganancia en 25 minutos
```

#### 6️⃣ Lunes 16:00 - Historial

```bash
# Ver todos los signals generados
tail logs/signals.csv

# Output:
timestamp,strategy,ticker,interval,direction,entry_price,confidence
2026-02-12T15:00:00,macd_vwap,SPY,15m,BUY,690.50,0.85
2026-02-12T15:00:00,rsi_bb,BTC-USD,1h,SELL,66900,0.72
```

---

## <a name="faq"></a> 8. FAQ

### P: ¿Cuánto capital necesito?
**R:** Plus500 permite desde $100-200. CFDs amplían tu poder (apalancamiento 1:30), pero **RIESGO = Mayor pérdida posible**.
- Recomendación: $5000+ para dormir tranquilo

### P: ¿Qué es apalancamiento?
**R:** Con $1000 y apalancamiento 1:10, controlas $10,000.
- Ganancia se multiplica: 0.5% = $50
- Pérdida también se multiplica: 0.5% = -$50
- **MÁS RIESGO = MÁS RECOMPENSA (pero cuidado)**

### P: ¿Por qué el sistema dice "HOLD"?
**R:** Porque NO cumple las condiciones:
- MACD no está en cruce
- RSI no está en extremo
- Precio no toca Bollinger
- = No hay oportunidad clara

### P: ¿Watch mode 24/7?
**R:** Puedes si tienes laptop siempre conectada.
- Recomendación: $10/mes en Hetzner o Oracle Cloud
- O: cron jobs (Linux) cada hora si tu laptop está on

### P: ¿El ML mejora mucho?
**R:** Sí, pero necesita:
- 1000+ datos de entrenamiento (6 meses histórico)
- 30-60 minutos para entrenar
- GPU (sin GPU toma 3-5 minutos)
- Retorna ~2-5% de mejora en accuracy

### P: ¿Qué si el bot falla?
**R:** Todas las señales se guardan en `logs/signals.csv`.
- Puedes revisar historial manual
- Telegram notifica, no depende de tu sistema
- Plus500 tiene SMS backup si quieres

### P: ¿Crypto vs Stocks?
**R:**
- **Crypto (BTC, ETH)**: 24/7, muy volátil, ideal scalping
- **Stocks (SPY, AAPL)**: 9:30-16 ET (14-21 UTC), menos volátil
- **Commodities (Oro, Petróleo)**: Casi 24h, tendencias claras

### P: ¿Cuántas trades por día?
**R:** Con watch cada 15 min:
- 96 escaneos por día
- ~5-10% tienen senal = 5-10 trades/día
- Si ganas 0.5% cada uno = 2.5-5% diario (compuesto)

### P: ¿Patrón de pérdidas?
**R:** Es NORMAL:
- Ganar 60%, perder 40% con buen sistema
- Si Win Rate = 40% con ratio 1:2 = ganas
- Ej: 100 trades, 40 ganan 1% = +40%, 60 pierden 0.5% = -30% = +10% neto

### P: ¿Tax implications?
**R:** Depende país:
- Muchos países = cada trade es evento taxable
- Consulta contador
- En scalping rápido algunos países permiten tratamiento "business"

### P: ¿Mejor SPY o crypto?
**R:**
- **SPY**: Más predecible, datos mejores, comisiones bajas
- **Crypto**: Más oportunidades, movimientos mayores, más volátil
- **Recomendación**: Empieza SPY, luego agrega crypto

---

## Comandos Rápidos de Referencia

```bash
# Setup una sola vez
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Descargar datos
python3 main.py fetch-data --ticker SPY --interval 1d --days 365

# Validar estrategia
python3 main.py backtest --strategy macd_vwap --ticker SPY --interval 1d

# Senal única
python3 main.py signal --strategy macd_vwap --ticker SPY --interval 1d

# Con ML
python3 main.py signal --strategy macd_vwap --ticker SPY --use-ml

# Entrenar modelo
python3 main.py train-lstm --ticker SPY --epochs 50

# Escaneo rápido
python3 main.py scan --tickers SPY,GLD,BTC-USD --strategies macd_vwap,rsi_bb

# Monitoreo continuo (LO QUE NECESITAS)
python3 main.py watch --tickers SPY,GLD,BTC-USD --strategies macd_vwap,rsi_bb --every 900

# Ver listado de estrategias
python3 main.py list-strategies

# Estado del sistema
python3 main.py status

# Tests
pytest tests/ -v
```

---

## Próximos Pasos

1. **Semana 1**: Setup + backtest en SPY con MACD+VWAP
2. **Semana 2**: Habilitar Telegram + Watch mode 2 horas/día
3. **Semana 3**: Agregar más tickers (GLD, BTC-USD)
4. **Semana 4**: Entrenar ML para mejorar accuracy
5. **Mes 2+**: Optimizar según resultados reales

---

## Recursos Externos

- **MACD**: https://www.investopedia.com/terms/m/macd.asp
- **RSI**: https://www.investopedia.com/terms/r/rsi.asp
- **Bollinger Bands**: https://www.investopedia.com/terms/b/bollingerbands.asp
- **Scalping**: https://www.investopedia.com/terms/s/scalping.asp
- **Risk Management**: https://www.investopedia.com/articles/trading/11/trade-what-you-can-afford-to-lose.asp

---

**¡Buena suerte trading! 🚀**

Recuerda: Start small, test thoroughly, scale gradually.
