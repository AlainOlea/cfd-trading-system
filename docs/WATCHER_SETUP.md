# 🔍 Multi-Timeframe Watcher Setup

**Fecha Creada**: 2026-02-14
**Estado**: ✅ Implementado
**Última Actualización**: 2026-02-14

---

## 📋 Resumen Ejecutivo

Sistema de monitoreo continuo con **dos watchers en paralelo**:

1. **Watch 1H (Cada Hora)** - Análisis táctico continuo
2. **Watch 1D (Una vez al día)** - Plan estratégico diario

```
┌─────────────────────────────────────┐
│ Watch 1H (Continuo 24/7)           │
│ └─ Corre cada 3600 segundos (1h)   │
├─────────────────────────────────────┤
│ Watch 1D (Automático a las 14:00)   │
│ └─ Corre vía CRON job              │
└─────────────────────────────────────┘
```

---

## 🎯 Arquitectura

### Watch 1H (Táctico)
- **Función**: Análisis cada hora, toma táctica de posiciones
- **Intervalo**: 1 hora
- **Modelo**: `multi_ticker_1h` + modelos específicos (SPY_1h, GLD_1h, etc.)
- **Ejecución**: Proceso continuo en terminal
- **Horarios**: Respeta horarios de cada mercado automáticamente

### Watch 1D (Estratégico)
- **Función**: Plan diario, dirección estratégica
- **Intervalo**: 1 día
- **Modelo**: `multi_ticker_1d` (ya entrenado)
- **Ejecución**: Cron job (automático)
- **Horario**: 14:00 UTC (apertura NYSE) cada día

---

## 🚀 Setup Paso a Paso

### Paso 1: Inicia Watch 1H (Ahora)

En **Terminal 1**, ejecuta:

```bash
source venv/bin/activate && nohup python3 main.py watch \
  --tickers "SPY,QQQ,GLD,BTC-USD,ETH-USD,AAPL,NVDA" \
  --interval 1h \
  --every 3600 \
  --use-ml > watcher_1h.log 2>&1 &

echo "✅ Watch 1H iniciado"
```

**Qué hace:**
- ✅ Activar venv
- ✅ Ejecutar watch en background (`nohup`)
- ✅ Intervalo: 1 hora (`--every 3600`)
- ✅ Guardar logs en `watcher_1h.log`
- ✅ Continúa ejecutando aunque cierres la terminal

### Paso 2: Configura Cron para Watch 1D (Una sola vez)

En **Terminal 2**, ejecuta:

```bash
crontab -e
```

Se abrirá un editor de texto. **Copia y pega esta línea exacta al final del archivo:**

```cron
0 14 * * 1-5 bash -c 'source /home/alaindolea/proyectos/cfd-trading-system/venv/bin/activate && cd /home/alaindolea/proyectos/cfd-trading-system && python3 main.py watch --tickers "SPY,QQQ,GLD,BTC-USD,ETH-USD,AAPL,NVDA" --interval 1d --every 86400 --use-ml >> watcher_1d.log 2>&1'
```

**Guarda el archivo:**
- Si usas **nano**: `Ctrl+X` → `Y` → `Enter`
- Si usas **vi**: `:wq` → `Enter`

---

## ✅ Verificación

### Verificar Watch 1H está corriendo

```bash
# Ver proceso activo
ps aux | grep "main.py watch"

# Ver logs en tiempo real
tail -f watcher_1h.log

# Ver último escaneo
tail -50 watcher_1h.log | grep -E "Scan|BUY|SELL|market"
```

### Verificar Cron está configurado

```bash
# Ver cron jobs activos
crontab -l

# Debe mostrar:
# 0 14 * * 1-5 bash -c 'source /home/alaindolea/proyectos/cfd-trading-system/venv/bin/activate && ...'
```

### Verificar logs de Cron

```bash
# Ver logs de ejecución del cron (1D)
tail -50 watcher_1d.log

# Verificar que se ejecutó hoy
cat watcher_1d.log | grep "$(date +%Y-%m-%d)"
```

---

## 📊 Comportamiento Esperado

### Ejemplo: Secuencia de 24 horas

```
14:00 UTC (Apertura NYSE)
├─ CRON: Inicia Watch 1D automáticamente
├─ SPY (indices): ✅ ANALIZADO
├─ QQQ (indices): ✅ ANALIZADO
├─ GLD (commodities): ❌ market closed
└─ BTC-USD (crypto): ✅ ANALIZADO
   └─ Resultado: Plan diario guardado

15:00 UTC (Watch 1H ejecuta)
├─ SPY: ✅ ANALIZADO (1 hora)
├─ QQQ: ✅ ANALIZADO (1 hora)
├─ GLD: ❌ market closed
└─ BTC-USD: ✅ ANALIZADO (1 hora)
   └─ Resultado: Señal táctica

16:00 UTC (Watch 1H ejecuta nuevamente)
├─ SPY: ✅ ANALIZADO
├─ QQQ: ✅ ANALIZADO
├─ GLD: ❌ market closed
└─ BTC-USD: ✅ ANALIZADO

...

21:00 UTC (Cierra NYSE)
├─ SPY: ❌ market closed
├─ QQQ: ❌ market closed
├─ GLD: ❌ market closed
└─ BTC-USD: ✅ ANALIZADO

23:00 UTC (Abre Gold)
├─ SPY: ❌ market closed
├─ QQQ: ❌ market closed
├─ GLD: ✅ ANALIZADO ← AUTOMÁTICO
└─ BTC-USD: ✅ ANALIZADO

14:00 UTC (Día siguiente)
├─ CRON: Inicia Watch 1D automáticamente (nuevamente)
├─ Repite ciclo...
```

---

## 🛠️ Operaciones Comunes

### Ver logs en tiempo real

```bash
# Watch 1H (cada hora)
tail -f watcher_1h.log

# Watch 1D (una vez al día)
tail -f watcher_1d.log

# Ambos simultáneamente
tail -f watcher_1h.log & tail -f watcher_1d.log
```

### Ver último escaneo

```bash
# Últimas 30 líneas
tail -30 watcher_1h.log

# Filtrar solo señales (BUY/SELL)
tail -100 watcher_1h.log | grep -E "BUY|SELL"

# Ver mercados cerrados
tail -100 watcher_1h.log | grep "market closed"
```

### Detener Watch 1H

```bash
# Encontrar PID
ps aux | grep "main.py watch"

# Matar proceso (reemplaza 12345 con el PID)
kill 12345

# O más directo:
pkill -f "main.py watch.*1h"
```

### Modificar Cron Watch 1D

```bash
# Abrir crontab de nuevo
crontab -e

# Buscar la línea con "watcher_1d"
# Editar según necesites
# Guardar

# Ejemplo: cambiar horario de 14:00 a 15:00 UTC
# Cambiar: "0 14 * * 1-5" por "0 15 * * 1-5"
```

### Eliminar Cron Watch 1D

```bash
# Abrir crontab
crontab -e

# Buscar y eliminar la línea con "watcher_1d"
# Guardar

# O simplemente borrar todo:
crontab -r
```

---

## 🎛️ Parámetros Personalizables

### Cambiar tickers

En ambos comandos, reemplaza:
```bash
--tickers "SPY,QQQ,GLD,BTC-USD,ETH-USD,AAPL,NVDA"
```

Con los que desees:
```bash
# Solo Bitcoin
--tickers "BTC-USD"

# Solo stocks
--tickers "SPY,QQQ,AAPL,NVDA,MSFT"

# Todos
--tickers "SPY,QQQ,GLD,BTC-USD,ETH-USD,AAPL,NVDA,MSFT,MSFT"
```

### Cambiar intervalo 1H

```bash
# Más frecuente (cada 15 min)
--interval 15m --every 900

# Menos frecuente (cada 2 horas)
--interval 2h --every 7200

# Cada 5 minutos (muy agresivo)
--interval 5m --every 300
```

### Cambiar estrategias

```bash
# Ver estrategias disponibles
python3 main.py list-strategies

# Usar solo una
--strategies "macd_vwap"

# Usar tres
--strategies "macd_vwap,rsi_bb,ma_crossover"
```

### Desactivar ML filter

```bash
# Sin --use-ml (solo análisis técnico)
python3 main.py watch --tickers "SPY,GLD,BTC" --interval 1h --every 3600
```

---

## 📝 Archivos Generados

```
logs/
├── watcher_1h.log        ← Watch 1H
└── watcher_1d.log        ← Watch 1D

logs/signals.csv          ← Todas las señales generadas
```

---

## 🔧 Troubleshooting

### Problema: Watch 1H no inicia

```bash
# Verificar que venv está bien
source venv/bin/activate
python3 -c "import tensorflow; print('✅ TensorFlow OK')"

# Verificar que los modelos existen
ls models/saved/multi_ticker_1h/
ls models/saved/multi_ticker_1d/

# Ejecutar sin nohup para ver errores
python3 main.py watch --tickers "BTC-USD" --interval 1h --every 3600 --use-ml
```

### Problema: Cron no ejecuta Watch 1D

```bash
# Ver historial de cron
grep CRON /var/log/syslog

# Verificar que la hora UTC es correcta
date -u

# Ver cron jobs activos
crontab -l

# Probar el comando manualmente
bash -c 'source /home/alaindolea/proyectos/cfd-trading-system/venv/bin/activate && cd /home/alaindolea/proyectos/cfd-trading-system && python3 main.py watch --tickers "BTC-USD" --interval 1d --every 86400 --use-ml'
```

### Problema: No recibe notificaciones Telegram

```bash
# Verificar que .env está configurado
cat .env | grep BOT_TOKEN
cat .env | grep CHAT_ID

# Ambos deben tener valores

# Probar envío manual
python3 -c "
from signals.telegram_bot import TelegramNotifier
notifier = TelegramNotifier()
if notifier.is_configured:
    notifier.send_alert('Test message')
    print('✅ Telegram OK')
else:
    print('❌ Telegram no configurado')
"
```

---

## 📚 Comandos de Referencia Rápida

```bash
# INICIAR WATCHERS
# Terminal 1: Watch 1H
source venv/bin/activate && nohup python3 main.py watch --tickers "SPY,QQQ,GLD,BTC-USD,ETH-USD,AAPL,NVDA" --interval 1h --every 3600 --use-ml > watcher_1h.log 2>&1 &

# Terminal 2: Configurar Cron para Watch 1D
crontab -e
# [Pega la línea del Paso 2 arriba]

# VER LOGS
tail -f watcher_1h.log              # Watch 1H tiempo real
tail -f watcher_1d.log              # Watch 1D tiempo real
tail -50 watcher_1h.log             # Últimas 50 líneas 1H
tail -100 watcher_1h.log | grep BUY # Solo señales BUY

# VERIFICACIÓN
ps aux | grep "main.py watch"       # Verificar proceso
crontab -l                          # Verificar Cron
ls -lh watcher_*.log                # Ver tamaño logs

# STOP/RESTART
pkill -f "main.py watch"            # Detener Watch 1H
crontab -e                          # Editar/eliminar Cron
```

---

## 📅 Schedule de Ejecución

```
LUNES-VIERNES:

00:00 UTC: BTC-USD ✅ (24/7)
01:00 UTC: BTC-USD ✅
...
12:00 UTC: BTC-USD ✅
13:00 UTC: BTC-USD ✅
14:00 UTC: ⭐ CRON INICIA WATCH 1D
           + SPY, QQQ, AAPL, NVDA, GLD, BTC-USD ✅
15:00 UTC: Watch 1H ejecuta (SPY, QQQ, AAPL, NVDA, BTC-USD)
16:00 UTC: Watch 1H ejecuta
...
21:00 UTC: SPY, QQQ, AAPL, NVDA cierran
           GLD aún cerrado
           BTC-USD ✅
22:00 UTC: GLD ❌ cierra
           BTC-USD ✅
23:00 UTC: GLD abre ✅
           BTC-USD ✅
...

SÁBADO-DOMINGO:
- Watch 1H: BTC-USD ✅ (24/7)
- Watch 1D: ❌ NO EJECUTA (cron limita a lunes-viernes)
```

---

## 🎓 Explicación Técnica

### ¿Por qué Opción 3 (Cron)?

```
Alternativas:
1. Dos terminals/watchers 24/7: ❌ Desperdicia recursos
2. Manual a las 14:00: ❌ Requiere intervención
3. Cron automático: ✅ Automático, eficiente, sin intervención

Opción 3 ventajas:
✅ Watch 1H continuo (necesario para señales frecuentes)
✅ Watch 1D solo al abrir (eficiente)
✅ Totalmente automático (cero intervención)
✅ Se ejecuta incluso si cierras la terminal
✅ Se ejecuta en background sin ocupar terminal
```

### ¿Cómo funciona Cron?

```
Cron job (línea en crontab):
0 14 * * 1-5 [comando]

0       = Minuto (0 = :00)
14      = Hora (14 = 2 PM UTC)
*       = Día del mes (cualquier día)
*       = Mes (cualquier mes)
1-5     = Día semana (1=lunes, 5=viernes)

Resultado: Se ejecuta cada lunes-viernes a las 14:00 UTC
```

---

## 🚀 Próximas Mejoras

```
[ ] Implementar scripts custom (watch_1d_strategy.py, watch_1h_tactical.py)
[ ] Agregar lógica de confluencia (1d + 1h)
[ ] Email alertas (además de Telegram)
[ ] Dashboard web para monitorear
[ ] Histórico de señales en base de datos
```

---

## 📞 Quick Help

¿Olvidaste cómo hacerlo? Lee esta sección:

| Necesito... | Ir a... |
|-------------|---------|
| Iniciar watchers | "Setup Paso a Paso" |
| Ver logs | "Operaciones Comunes" |
| Cambiar tickers | "Parámetros Personalizables" |
| Modificar hora cron | "Modificar Cron Watch 1D" |
| Solucionar problemas | "Troubleshooting" |

---

## 📋 Checklist Setup

- [ ] Watch 1H iniciado en Terminal 1
- [ ] Cron configurado (ejecutar `crontab -l` para verificar)
- [ ] Ver logs funcionando (`tail -f watcher_1h.log`)
- [ ] Verificar que proceso corre (`ps aux | grep main.py`)
- [ ] Verificar que Telegram está configurado (si lo usas)
- [ ] Crear bookmark a este documento

---

**Última actualización**: 2026-02-14
**Versión**: 1.0
**Status**: ✅ Funcional
