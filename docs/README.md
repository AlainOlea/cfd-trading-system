# Trading System Documentation

Welcome to the centralized documentation for the CFD Trading System.

## 📁 Directory Structure

```
docs/
├── README.md                          # This file
├── guides/                            # Setup and implementation guides
│   ├── NEWS_ANALYZER_SETUP.md         # News sentiment analysis setup
│   ├── INTEGRATION_SUMMARY.md         # Complete integration overview
│   └── [other guides]
├── prompts/                           # AI prompt optimization and analysis
│   ├── PROMPT_OPTIMIZATION.md         # Prompt improvement strategies
│   ├── PROMPT_IMPROVEMENTS_SUMMARY.md # Before/after comparison
│   └── [other prompt docs]
├── analysis/                          # Technical analysis and research
│   └── [analysis documents]
└── tests/                             # Testing documentation and guides
    └── [test documentation]
```

## 🗂️ Categories

### 📖 Guides (`/guides`)
Setup instructions, implementation guides, and user manuals.

- **NEWS_ANALYZER_SETUP.md** - Complete setup guide for Google AI + NewsAPI integration
  - API key configuration
  - Installation instructions
  - Troubleshooting guide
  - Usage examples

- **INTEGRATION_SUMMARY.md** - Comprehensive integration overview
  - What was built and how it works
  - End-to-end flow diagram
  - Real-world examples
  - Performance metrics

### 🧠 Prompts (`/prompts`)
AI prompt optimization, analysis, and improvements.

- **PROMPT_OPTIMIZATION.md** - Detailed prompt optimization analysis
  - Current vs. improved versions (V1, V2, V3)
  - Comparison matrix
  - Implementation strategy
  - Testing results

- **PROMPT_IMPROVEMENTS_SUMMARY.md** - Before/after detailed comparison
  - Side-by-side examples
  - Quality metrics (70% → 85-90%)
  - Key improvements explained
  - Production readiness status

### 📊 Analysis (`/analysis`)
Technical analysis, research, and performance data.

*Coming soon: Market analysis, model performance, signal accuracy tracking*

### 🧪 Tests (`/tests`)
Testing documentation, test frameworks, and validation guides.

*Coming soon: Test suite documentation, validation procedures*

---

## 🚀 Quick Start

### 1. Setup News Sentiment Analysis
```bash
# Read the setup guide
cat docs/guides/NEWS_ANALYZER_SETUP.md

# Get API keys
# 1. NewsAPI: https://newsapi.org
# 2. Google AI: https://ai.google.dev

# Add to .env:
# NEWS_API_KEY=your_key
# GOOGLE_AI_API_KEY=your_key
```

### 2. Understand the Integration
```bash
# Read the integration overview
cat docs/guides/INTEGRATION_SUMMARY.md
```

### 3. Learn About Prompt Optimization
```bash
# Read prompt analysis
cat docs/prompts/PROMPT_OPTIMIZATION.md

# See before/after comparison
cat docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md
```

---

## 📚 Guides by Use Case

### For Traders
- Start with: `guides/INTEGRATION_SUMMARY.md`
- Then read: `guides/NEWS_ANALYZER_SETUP.md`

### For Developers
- Start with: `prompts/PROMPT_OPTIMIZATION.md`
- Then read: `guides/INTEGRATION_SUMMARY.md`

### For Data Scientists
- Start with: `prompts/PROMPT_IMPROVEMENTS_SUMMARY.md`
- Then read: `prompts/PROMPT_OPTIMIZATION.md`

### For DevOps/Operations
- Start with: Root `README.md` and `CLAUDE.md`
- Then: `guides/NEWS_ANALYZER_SETUP.md`

---

## 🔗 Related Files

### Root-Level Documentation
- **README.md** - Project overview and quick start
- **CLAUDE.md** - Project specifications and architecture
- **INTEGRATION_SUMMARY.md** → *Moved to docs/guides/*
- **PROMPT_OPTIMIZATION.md** → *Moved to docs/prompts/*
- **PROMPT_IMPROVEMENTS_SUMMARY.md** → *Moved to docs/prompts/*
- **NEWS_ANALYZER_SETUP.md** → *Moved to docs/guides/*

### Configuration Files
- **scripts.yaml** - Central script registry (see below)
- **.env.example** - Environment variables template
- **config/settings.py** - System configuration

### Script Manager
- **run_script.py** - Central script runner
- **scripts.yaml** - Script registry and commands

---

## 🎯 Using the Script Manager

The project includes a centralized script manager (`run_script.py`) that makes it easy to run all commands:

### Basic Usage
```bash
# List all categories
python3 run_script.py list

# List scripts in a category
python3 run_script.py list data
python3 run_script.py list signals
python3 run_script.py list test

# Run a script
python3 run_script.py data fetch-all
python3 run_script.py signals ensemble-expanded
python3 run_script.py test test-all
```

### Available Categories
- **data** - Fetch and manage market data
- **train** - Train ML models
- **signals** - Generate trading signals
- **backtest** - Backtest strategies
- **news** - Test news sentiment analysis
- **test** - Run unit tests
- **docs** - Documentation and config
- **workflows** - Pre-configured multi-step workflows

### Example Commands
```bash
# Fetch data
python3 run_script.py data fetch-all

# Train models
python3 run_script.py train lstm-gld
python3 run_script.py train expansion

# Generate signals
python3 run_script.py signals ensemble-expanded
python3 run_script.py signals ensemble-specific --tickers GLD,MSFT

# Test news sentiment
python3 run_script.py news test-gld
python3 run_script.py news test-multi

# Run tests
python3 run_script.py test test-all
python3 run_script.py test test-data

# Run workflows (multi-step)
python3 run_script.py workflows daily-check
python3 run_script.py workflows full-test
```

### Get Help
```bash
# Show main help
python3 run_script.py help

# Show category help
python3 run_script.py list
python3 run_script.py list signals
```

---

## 📋 Document Checklist

### In Progress
- [ ] Market analysis and performance tracking
- [ ] Test suite documentation
- [ ] Model accuracy and validation reports
- [ ] Signal backtesting results
- [ ] Risk management guide

### Completed
- [x] News sentiment analysis setup
- [x] Integration documentation
- [x] Prompt optimization analysis
- [x] Script manager setup

---

## 🔍 Document Search

### By Topic
- **News & Sentiment** → `guides/NEWS_ANALYZER_SETUP.md`, `guides/INTEGRATION_SUMMARY.md`
- **AI & Prompts** → `prompts/PROMPT_OPTIMIZATION.md`, `prompts/PROMPT_IMPROVEMENTS_SUMMARY.md`
- **Setup & Configuration** → `guides/INTEGRATION_SUMMARY.md`, root `CLAUDE.md`
- **Scripts & Commands** → Root `run_script.py` and `scripts.yaml`

### By Audience
- **Traders** → Start with `guides/INTEGRATION_SUMMARY.md`
- **Developers** → Start with `prompts/PROMPT_OPTIMIZATION.md`
- **DevOps** → Start with root `README.md`
- **Data Scientists** → Start with `prompts/PROMPT_IMPROVEMENTS_SUMMARY.md`

---

## 💡 Tips

1. **New to the project?** Start with root `README.md` and `CLAUDE.md`
2. **Setting up news?** Follow `guides/NEWS_ANALYZER_SETUP.md`
3. **Understanding the system?** Read `guides/INTEGRATION_SUMMARY.md`
4. **Improving prompts?** Study `prompts/PROMPT_OPTIMIZATION.md`
5. **Running scripts?** Use `python3 run_script.py help`

---

## 🔄 Maintenance

Documentation is organized by:
- **Topic/Feature** (guides, prompts, analysis, tests)
- **Completeness** (guides are complete, analysis is growing)
- **Audience** (guides for users, prompts for developers)

Keep docs updated when:
- Adding new features
- Changing API behavior
- Improving prompts
- Adding new test suites
- Optimizing performance

---

## 📞 Questions?

For specific topics:
- News setup → See `guides/NEWS_ANALYZER_SETUP.md`
- Integration → See `guides/INTEGRATION_SUMMARY.md`
- Prompts → See `prompts/PROMPT_OPTIMIZATION.md`
- Running scripts → Run `python3 run_script.py help`

---

**Last Updated:** 2026-02-14
**Status:** Organized and Accessible ✅
