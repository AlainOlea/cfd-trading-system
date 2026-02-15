#!/bin/bash
# ============================================
# WATCHER SETUP - QUICK START
# ============================================
# Archivo: WATCHER_QUICKSTART.sh
# Propósito: Comandos listos para copiar/pegar
# Fecha: 2026-02-14
#
# USO:
# 1. Lee este archivo
# 2. Copia/pega los comandos en terminal
# 3. O ejecuta: bash WATCHER_QUICKSTART.sh
# ============================================

echo "🔍 WATCHER SETUP - QUICK START"
echo "=============================="
echo ""
echo "Paso 1: Watch 1H (Copia/Pega en Terminal 1)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "source venv/bin/activate && nohup python3 main.py watch \\"
echo "  --tickers \"SPY,QQQ,GLD,BTC-USD,ETH-USD,AAPL,NVDA\" \\"
echo "  --interval 1h \\"
echo "  --every 3600 \\"
echo "  --use-ml > watcher_1h.log 2>&1 &"
echo ""
echo "✅ Esto inicia Watch 1H en background"
echo ""
echo ""
echo "Paso 2: Watch 1D vía CRON (Ejecuta en Terminal 2)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "crontab -e"
echo ""
echo "Luego PEGA esta línea exacta al final del archivo:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "0 14 * * 1-5 bash -c 'source /home/alaindolea/proyectos/cfd-trading-system/venv/bin/activate && cd /home/alaindolea/proyectos/cfd-trading-system && python3 main.py watch --tickers \"SPY,QQQ,GLD,BTC-USD,ETH-USD,AAPL,NVDA\" --interval 1d --every 86400 --use-ml >> watcher_1d.log 2>&1'"
echo ""
echo "Guarda: Ctrl+X (nano) o :wq (vi)"
echo ""
echo ""
echo "VERIFICACIÓN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Ver logs 1H en tiempo real:"
echo "  tail -f watcher_1h.log"
echo ""
echo "Ver logs 1D:"
echo "  tail -f watcher_1d.log"
echo ""
echo "Verificar proceso activo:"
echo "  ps aux | grep \"main.py watch\""
echo ""
echo "Verificar Cron configurado:"
echo "  crontab -l"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup completado!"
echo "📖 Ver docs/WATCHER_SETUP.md para más detalles"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
