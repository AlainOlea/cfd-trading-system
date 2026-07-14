# `main.py watch` — Reference

**Estado**: los flags del comando siguen vigentes. La sección de automatización de este
documento (cron + `nohup`, modelos `multi_ticker_1h`/`multi_ticker_1d`) describía el setup
original de 2026-02-14 y **ya no es como corre el sistema en producción** — ver más abajo.

---

## Qué es

`main.py watch` corre un loop continuo que reevalúa señales para una lista de tickers cada
N segundos, respetando el horario de cada mercado automáticamente. Es una herramienta manual
de monitoreo/desarrollo — no es el mecanismo de producción.

```bash
python3 main.py watch --tickers "SPY,QQQ,GLD,BTC-USD" --interval 1h --every 3600 --use-ml
```

## Parámetros

| Flag | Qué hace |
|---|---|
| `--tickers` | Lista separada por comas de los tickers a monitorear |
| `--interval` | Timeframe (`1m`, `5m`, `15m`, `1h`, `1d`, etc.) |
| `--every` | Segundos entre cada re-evaluación (ej. `3600` = cada hora) |
| `--strategies` | Estrategias a usar, ver `python3 main.py list-strategies` (default: todas) |
| `--use-ml` | Activa el filtro ML sobre la señal técnica |

## Automatización en producción

`watch` **no** es lo que corre en producción hoy. La automatización real usa Windows Task
Scheduler invocando `run_paper_hourly.ps1`/`run_paper_daily.ps1` (que a su vez llaman
`main.py paper-trade`, no `watch`) — ver la tabla "Paper Trading Automation" en `CLAUDE.md`
para el detalle completo (horarios, tipo de órdenes, SL/TP).

Si necesitás un monitoreo manual puntual (no automatizado) para debugging, `watch` en una
terminal con `nohup ... &` sigue siendo válido para eso — solo no es cómo se ejecuta el
sistema día a día.
