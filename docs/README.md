# CFD Trading System - Complete Documentation

**Last Updated**: 2026-07-13
**Status**: Active

---

## Directory Structure

```
docs/
├── README.md
├── WATCHER_SETUP.md
│
├── archive/                          # Superseded — historical reference only, not current
│   ├── AGENT_CONTEXT.md
│   ├── GUIA_COMPLETA.md
│   ├── INTEGRATION_SUMMARY.md
│   ├── ML_RETRAINING.md
│   ├── ML_RETRAINING_IMPLEMENTATION.md
│   ├── ML_RETRAINING_SUMMARY.md
│   ├── PROJECT_SPECS.md
│   └── TRADING_SYSTEM_COMPLETE.md
│
├── guides/
│   ├── NEWS_ANALYZER_SETUP.md
│   ├── SIGNAL_GENERATION_GUIDE.md
│   ├── MULTIFREQ_TRADING_STRATEGY.md
│   ├── GPU_SETUP.md
│   ├── UNIFIED_PIPELINE_IMPLEMENTATION.md
│   ├── TIMESFM_GUIDE.md
│   ├── TIMESFM_INTEGRATION_PLAN.md
│   └── TIMESFM_TRAINING_STRATEGY.md
│
├── prompts/
│   ├── PROMPT_IMPROVEMENTS_SUMMARY.md
│   └── PROMPT_OPTIMIZATION.md
│
├── analysis/                         # Point-in-time session logs / audit notes, not living docs
│   ├── SESSION_CHANGELOG.md
│   ├── SESSION_2026-05-19.md
│   ├── SESSION_2026-06-05.md
│   ├── FRESH_DATA_FIX.md
│   ├── IMPLEMENTATION_COMPLETE.md
│   ├── GPU_CUDA_SUMMARY.md
│   ├── SYSTEM_AUDIT_GUIDE.md
│   └── TODO_LABELING_BUG.md
│
├── reference/
│   ├── ML_RESEARCH.md
│   ├── MODULES_API.md                # Full module API — source of truth for current code
│   ├── TIMESFM_EXECUTIVE_SUMMARY.md
│   └── TIMESFM_2P5_API_REFERENCE.md
│
└── research/
    ├── NORMALIZED_TIME_PROFILE.md
    └── TIMESFM_DEEP_RESEARCH.md
```
(`quickstart/` is now empty — both its docs moved to `archive/` — and will disappear once git
stops tracking any file under it.)

> **`docs/archive/`** holds documents that describe an architecture the codebase no longer
> has (the pre-Alpaca `run_script.py` era, or the 9-model LSTM+Transformer era before
> XGBoost became primary — including the LSTM retraining guides, `ML_RETRAINING*.md`, moved
> here once LSTM was fully retired). Each file has a banner at the top explaining what
> superseded it. Don't use these as a reference for current behavior — they're kept only so
> history isn't lost.

---

## Quick Navigation

### Start here
- Setup + architecture: `CLAUDE.md` (repo root) — read this first
- Full module API: `reference/MODULES_API.md`
- Paper trading automation: `CLAUDE.md` → "Paper Trading Automation" section

### For Traders
- Strategy logic: `guides/SIGNAL_GENERATION_GUIDE.md`
- News setup: `guides/NEWS_ANALYZER_SETUP.md`
- Multi-timeframe approach: `guides/MULTIFREQ_TRADING_STRATEGY.md`

### For Developers
- Module reference: `reference/MODULES_API.md`
- Pipeline internals: `guides/UNIFIED_PIPELINE_IMPLEMENTATION.md`
- GPU setup: `guides/GPU_SETUP.md`
- Watcher/cron reference: `WATCHER_SETUP.md` (flags still valid; automation itself is now
  Windows Task Scheduler — see `CLAUDE.md`)

### For Data Scientists
- ML papers & theory: `reference/ML_RESEARCH.md`
- TimesFM integration: `guides/TIMESFM_GUIDE.md`, `research/TIMESFM_DEEP_RESEARCH.md`
- Prompt analysis: `prompts/PROMPT_IMPROVEMENTS_SUMMARY.md`

---

## Key Documents

| Document | Description |
|----------|-------------|
| `CLAUDE.md` (repo root) | Setup, architecture, current commands — the canonical entry point |
| `reference/MODULES_API.md` | Detailed API for every module, kept in sync with the codebase |
| `reference/ML_RESEARCH.md` | 8 papers + 2 books on ML for trading, underpins `config/settings.py`'s ML params |
| `guides/UNIFIED_PIPELINE_IMPLEMENTATION.md` | How `UnifiedPipeline` orchestrates fetch → indicators → strategies → ML → TimesFM |
| `analysis/SYSTEM_AUDIT_GUIDE.md` | Financial-advisor-style evaluation guide for the system's risk approach |
| `analysis/SESSION_CHANGELOG.md` | Running log of past session changes |
