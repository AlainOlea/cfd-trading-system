---
name: strategy-research
description: Use when the user wants to research, evaluate, or add new trading strategies to this CFD system — e.g. "busca estrategias nuevas", "qué otras estrategias hay", "/strategy-research", or when proposing a strategy not yet in STRATEGY_MAP.
---

# Strategy Research → Backtest → Production

## Overview

Pipeline con compuertas humanas para incorporar estrategias de trading nuevas.
**El usuario decide en cada compuerta; nunca se salta una.** Nada entra a
producción (`PIPELINE_TICKERS` en `config/settings.py`) sin backtest revisado
y aprobación explícita.

## Fase 1 — Investigación (web, con validación externa)

Buscar estrategias de intraday/swing trading que:
- NO estén ya en `STRATEGY_MAP` (`strategies/__init__.py`)
- Tengan validación externa: papers/estudios, backtests publicados, o adopción
  documentada por traders con resultados. **Sin evidencia externa, no se presenta.**
- Se ajusten al comportamiento actual del mercado (buscar análisis recientes, no solo clásicos).

Presentar al usuario una tabla: nombre, cómo funciona (2-3 líneas en lenguaje
llano, sin jerga), qué la valida (con links), y en qué timeframe/régimen aplica.

**COMPUERTA 1:** el usuario elige. Si pide "descríbeme más la X", hacer una
investigación rápida ampliada solo de esa. Si ninguna le gusta → fin del proceso.

## Fase 2 — Implementación + Backtest

Para cada estrategia elegida:
1. Implementar siguiendo el patrón del proyecto: subclase de `BaseStrategy`
   (`strategies/base.py`), parámetros en `config/settings.py` (nunca hardcoded),
   registrar en `STRATEGY_MAP`, agregar al `click.Choice` de `main.py`,
   tests en `tests/test_strategies.py` (mínimo: columnas, SL/TP del lado
   correcto, valores de señal válidos).
2. Backtest en varios tickers/intervalos:
   `python3 main.py backtest --strategy X --ticker Y --interval Z`
   Reportar: retorno, # trades, win rate, profit factor, y comparación contra
   la estrategia existente más parecida en los mismos datos.
3. Advertir siempre: el backtest sale por señal opuesta, no por SL/TP como el
   paper trading real; pocos trades (<20) = resultado no confiable.

**COMPUERTA 2:** presentar números sin filtrar (no hay umbral automático — el
usuario juzga). Preguntar: ¿a productivo, o se descarta? Si se descarta, la
estrategia queda en `STRATEGY_MAP` (disponible para backtest/replay) pero
NUNCA se agrega a `PIPELINE_TICKERS`.

## Fase 3 — Activación en productivo (solo con aprobación)

Mostrar en qué tickers el backtest fue mejor y **preguntar al usuario en cuáles
activarla**. Editar solo esos en `PIPELINE_TICKERS`. Recordar que el replay
(`scripts/replay_signals.py`) medirá su desempeño real en unos días.

## Fase 4 — Prompt para NotebookLM (ofrecer siempre al final)

Preguntar si quiere un prompt para estudiar las estrategias por su cuenta en
NotebookLM. NotebookLM trabaja sobre fuentes: su botón **"Discover sources"**
recibe una descripción de tema y trae ~10 fuentes web curadas. El prompt debe
tener dos partes:

```
[Para Discover sources — descripción de tema:]
Estrategia <nombre> para trading intradía: explicación de cómo funciona,
niveles de entrada/salida, estudios o backtests publicados sobre su
efectividad, errores comunes al usarla. Prefiere fuentes educativas
reconocidas (Investopedia, papers, brokers regulados), con fecha, de los
últimos 2 años; evita foros sin autor.

[Para el chat de la libreta — preguntas guía:]
1. Explícame <estrategia> como si fuera principiante, con un ejemplo numérico.
2. ¿En qué condiciones de mercado funciona y en cuáles falla?
3. ¿Qué dicen los estudios sobre su rentabilidad real?
```

## Errores comunes

- Presentar estrategias sin evidencia externa "porque son conocidas" → no: link o no se presenta.
- Activar en todos los tickers tras un backtest bueno en uno → no: el usuario elige tickers.
- Saltarse tests "porque el backtest ya corrió" → no: tests primero, patrón de `tests/test_strategies.py`.
- Olvidar `require_trend`/`require_ranging`/`mean_reversion` — clasificar la
  estrategia (momentum vs reversión) y setear los flags; `mean_reversion=True`
  evita que TimesFM pise SL/TP.
