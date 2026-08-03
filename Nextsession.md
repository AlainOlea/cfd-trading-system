# Nextsession.md — Plan de trabajo para la próxima sesión

> Documento de handoff único. Se **borra** cuando todo lo de la sección 8 esté cumplido.

---

## 1. Estado actual (contexto)

- **Sistema**: Fedora 44, kernel 7.1.5-201.fc44, laptop MSI Crosshair A17 HX (MS-17TL), 38Gi RAM, RTX 5060 Laptop 8GB (Blackwell, sm_120) + iGPU AMD Raphael. nvidia-powerd activo, límite GPU 70W.
- **Python**: 3.12.13 instalado vía `dnf` (el Python 3.14 del sistema es incompatible; `python3.12-pip` no existe en Fedora).
- **Entorno**: `venv/` en la raíz del repo, stack completo: numpy 2.2.6, pandas 2.3.2, **pandas-ta 0.4.71b0 (instalado con `--no-deps` — la 0.3.14b no existe en PyPI y la 0.4.71b0 pura rompe con pandas)**, **vectorbt 0.28.4 (NUNCA instalar 1.0.0, rompe API)**, xgboost 3.3.0, alpaca-py 0.43.5, yfinance 1.1.0, ccxt 4.5.37, numba 0.61.2, scikit-learn 1.9.0, matplotlib 3.11.1.
- **No instalados (a propósito)**: torch, timesfm, tensorflow. El pipeline degrada silenciosamente: máximo 4/5 estrellas, SL/TP con % fijos, tabla `tfm_forecasts` vacía.
- **Nota trampa**: `main.py status` imprime "TensorFlow GPU configured" — es texto hardcodeado en `config/settings.py`; TF no está instalado, no es un error.
- **Tests**: 162 passed en ~26s. `git` y SSH ed25519 configurados (AlainOlea / alaindcontreras@gmail.com).
- **`.env`**: ALPACA_API_KEY (26 chars), ALPACA_SECRET_KEY (44 chars), TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, NEWS_API_KEY llenos. GOOGLE_AI_API_KEY y BITSO_* vacíos (opcionales, el pipeline los salta).
- **Auditoría realizada** (2 agentes): hallazgos detallados en sección 5. Infraestructura/riesgo: nivel profesional; validez estadística: cuestionable (backtest sin SL/TP real).
- **Hardware/particiones**: nvme0n1p3 NTFS 822.5G = Windows (no montada). No montar; transferencia manual por USB.

---

## 2. Paso 0 — Traer datos desde WSL (USB)

1. Conectar USB → identificar con `lsblk -f` → montar en `/run/media/alainolea` (modo read-only recomendado).
2. Copiar desde WSL al repo clonado:
   - `.env` (comparar claves antes de sobrescribir)
   - `models/saved/` (modelos XGBoost entrenados)
   - `data/raw/*.csv` (históricos por ticker+intervalo)
   - `logs/signals.db` (historial de señales, cooldowns)
3. Verificar con `git log --oneline` si el repo de WSL tenía commits locales que no estén en GitHub (si los hay: `git pull` primero o aplicar después del paso 1).
4. Desmontar limpio. No dejar la partición Windows montada.

**Aceptación**: `python main.py status` muestra "0 archivos de datos aún" → carga los CSVs; `logs/signals.db` existe con filas.

---

## 3. Paso 1 — Estructura de paquete (`pyproject.toml`)

No hay packaging hoy (ni setup.py ni pyproject). Crear `pyproject.toml` en la raíz:

- `[project]`: name `cfd-trading-system`, requires-python `>=3.12`, `dependencies` = núcleo (los listados en sección 1, sin ML pesado).
- `[project.optional-dependencies]` — esto elimina la necesidad de `requirements-fedora.txt` (era un `grep -v tensorflow`):
  - `timesfm = ["timesfm[torch]"]`
  - `tensorflow = ["tensorflow==2.21.0"]`
  - `kronos = []` (no es pip-installable; ver paso 2)
- `[project.scripts]`: `cfd-trade = "main:cli"` (el CLI de Typer ya existe en `main.py`).
- `[tool.setuptools.packages.find]` incluyendo `backtesting, config, data, indicators, models, signals, strategies`.
- `[tool.pytest.ini_options]` (testpaths, pythonpath) y `[tool.ruff]` si se quiere.
- Instalar: `venv/bin/pip install -e .` y correr `pytest` para validar que no rompe imports.

**Consecuencia directa**: los 3 `.ps1` y `setup_tasks.ps1` pasan de rutas absolutas a `cfd-trade paper-trade ...`. Corrige de paso el typo `/home/alaindolea/proyectos/...` (los `.ps1` actuales apuntan a ese path inexistente — la automatización Windows probablemente estaba rota).

**Aceptación**: `cfd-trade --help` funciona; `pytest` verde; `.ps1` corregidos.

---

## 4. Paso 2 — Evaluación Kronos (A/B vs TimesFM)

### Qué es (investigación hecha)
- Modelo fundacional **específico de velas K-line (OHLCV)** financieras. Paper arXiv 2508.02739, aceptado AAAI 2026, licencia MIT, ~35.6k estrellas.
- Entrenado en **12 mil millones de velas de 45 exchanges** (vs TimesFM: Google Trends/Wikipedia).
- **Pesos ya entrenados** en HuggingFace (org `NeoQuasar`): Kronos-mini 4.1M (contexto 2048), Kronos-small 24.7M (contexto 512), Kronos-base 102.3M (contexto 512), Kronos-large 499M **no open source**.
- El **código no es pip-installable** (sin setup.py en el repo): hay que clonar `github.com/shiyu-coder/Kronos` o **copiar solo la carpeta `model/`** al repo (recomendado).
- API: `KronosPredictor(model, tokenizer, max_context).predict(df, x_timestamp, y_timestamp, pred_len, T, top_p, sample_count)` → devuelve **OHLCV pronosticado** (multivariable; TimesFM solo da close + cuantiles).
- Probabilístico por muestreo (T, top_p, sample_count) — no da cuantiles directos: derivar percentiles de las trayectorias muestreadas.

### Por qué es candidato
- Dominio-financiero: ataca la crítica #1 a TimesFM (entrenado en datos no financieros).
- **SL/TP dinámico natural**: pronostica high/low directamente (hoy tu sistema deriva SL/TP de cuantiles del *close* — un hack; `models/timesfm_predictor.py:177-178`).
- Mucho más pequeño → inferencia CPU viable; con la 5060, rápido.
- Tu data layer ya produce DataFrames OHLCV 1m/1h — encaja con su API.
- Bonus: podría dar estrella ML y SL/TP dinámico en **1d** (hoy las señales swing corren sin validación ML; TimesFM se limita a 1m/1h, `timesfm_predictor.py:63`, en 1d la precisión direccional cae a ~44%).

### Pasos
1. Instalar torch CUDA: **torch ≥2.7** (RTX 5060 = Blackwell sm_120; versiones viejas caen a CPU o fallan). `pip install torch --index-url https://download.pytorch.org/whl/cu128` (ajustar a la wheel cu disponible). Verificar: `python -c "import torch; print(torch.cuda.is_available())"`.
2. Copiar `model/` de Kronos al repo (p.ej. `vendor/kronos/model/`) + sus deps ligeras (einops, huggingface_hub, safetensors — compatibles con pandas 2.3.2; NO instalar su requirements.txt completo que fija pandas==2.2.2).
3. Wrapper `KronosPredictor` espejo de `TimesFMPredictor` (misma interfaz: lazy load, `predict_batch`, dirección, y SL/TP desde percentiles de `sample_count` muestras; respetar el patrón de degradación actual de `signals/pipeline.py:130-135,418-419,456-459`).
4. **No tocar producción**: correr en paralelo offline con el harness existente `scripts/validate_tfm_forecasts.py` (dirección, orden min/max, MAE %, cobertura de banda q10-q80). Necesita `tfm_forecasts` — puede llenarse vía modo validación sin trading.
5. Comparar vs TimesFM en 1m y 1h (y opcionalmente 1d).

### Criterio de decisión (documentar en este archivo antes de borrarlo)
- Gana Kronos si supera a TimesFM en dirección **y** cobertura de banda en 1m/1h con datos reales.
- Si empata o pierde → se queda TimesFM y Kronos se elimina. Si no hay suficientes datos aún → posponer la decisión, no forzarla.

### Caveats (no ignorar)
- Métricas del paper son estadísticas (RankIC/MSE/CRPS), no P&L.
- Modelo nuevo (ago 2025), validación independiente limitada; benchmarks de TSFM pueden tener solapamiento train/test (estudios reportan inflación de 47–184%).
- Fine-tuning disponible (tokenizer + predictor, torchrun) — opcional, no necesario para el A/B.

---

## 5. Paso 3 — Fixes de auditoría (3 ALTOS + menores)

1. **Backtest sin SL/TP** (`backtesting/engine.py:101-109`): el motor entra/sale sin simular stops ni targets → resultados irreales. Implementar bracket simulado (precios intrabarra o aproximación conservadora) y re-correr.
2. **Drawdown halt por proceso** (`signals/alpaca_broker.py:199-223`): el estado de drawdown se pierde si el proceso muere/reinicia → el halt no persiste. Persistir en `logs/` o SQLite (el sistema ya usa escrituras atómicas en `signals/store.py`).
3. **Zona HOLD muerta en XGBoost** (`models/xgboost_model.py:507-521`): el clasificador puede devolver HOLD pero el código lo descarta — o se implementa o se elimina el estado.
4. Menores: `requirements.txt` incompleto (falta xgboost, alpaca-py, torch/timesfm opcionales); `ML_PROMOTION_GATE` definido pero nunca usado (`config/settings.py`) — implementar o eliminar.

**Aceptación**: tests nuevos cubriendo los 3 ALTOS; `pytest` verde.

---

## 6. Paso 4 — Automatización (systemd timers)

Reemplazo de Task Scheduler de Windows. Replicar horarios de `run_paper_hourly.ps1`, `run_paper_daily.ps1`, `run_paper_1min.ps1` (flag `--min-confluence 3`):

- 1min → solo en horario de mercado (recordar: scalping 1m requiere el proceso corto; el sistema maneja cooldowns).
- hourly → ciclo normal.
- daily → reporte/cierre del día.
- Considerar `OnCalendar` con zonas horarias de mercado; logs de systemd a `logs/` del proyecto.
- Entry point `cfd-trade` + `[Service] ExecStart` apuntando al venv absoluto.

**Aceptación**: `systemctl list-timers` muestra los 3 activos; un dry-run programado dispara sin error.

---

## 7. Opcionales (sin presión)

- Instalar TimesFM completo (~2GB con torch) si el A/B decide mantenerlo.
- LoRA finetune: `scripts/train_timesfm_lora.py` (batches A/B/C definidos).
- Perfil GPU: LACT / MControlCenter (usuario decidió no tocar; el límite actual 70W está bien).
- Terminal: Ghostty (candidata futura; kitty actual está bien).
- Slack: nada.

---

## 8. Definición de "listo" (al cumplirse todo → borrar este archivo)

- [ ] USB transferido (sección 2) y `main.py status` carga datos reales.
- [ ] `pip install -e .` limpio, `cfd-trade` funciona, `.ps1` corregidos (sección 3).
- [ ] Torch CUDA OK en la RTX 5060; wrapper Kronos probado; comparación A/B documentada **con decisión escrita** (sección 4).
- [ ] Fixes ALTOS de auditoría implementados con tests (sección 5).
- [ ] Timers systemd activos y disparando (sección 6).
- [ ] `pytest` verde al cierre.
- [ ] Decisión Kronos/TimesFM anotada aquí → **borrar `Nextsession.md`**.

---

*Última actualización: 2026-08-02. Estado al crear: todo el setup de Fedora completo (sección 1), resto pendiente.*
