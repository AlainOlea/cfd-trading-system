# Agent Context - Quick Reference

**READ THIS FIRST when starting a Claude session**

## 🔴 MANDATORY: You MUST read these documents

1. ✅ CLAUDE.md (main specifications)
2. ✅ docs/README.md (documentation index)
3. ✅ docs/guides/INTEGRATION_SUMMARY.md (system overview)
4. ✅ docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md (recent improvements)
5. ✅ docs/guides/NEWS_ANALYZER_SETUP.md (news integration)

**⚠️ Do not proceed without reading all 5.**

---

## 📊 Current System State

### Latest Session Accomplishments
- ✅ Sentiment analysis optimized (V2 prompt: +15-20% accuracy)
- ✅ Project reorganized (/docs with 4 subdirectories)
- ✅ Centralized script manager created (41 scripts, 8 categories)
- ✅ Google Gemini AI + NewsAPI integrated
- ✅ Documentation fully organized and indexed

### Key Files (Don't Miss!)
- **run_script.py** - Central script executor (NEW)
- **scripts.yaml** - Script registry with 41 commands (NEW)
- **signals/news_analyzer.py** - Sentiment analysis with V2 prompt (UPDATED)
- **docs/** - Complete documentation (NEW STRUCTURE)

### Quick Commands
```bash
# List all available scripts
python3 run_script.py list

# Test news sentiment
python3 run_script.py news test-gld

# Generate signals
python3 run_script.py signals ensemble-expanded

# Run all tests
python3 run_script.py test test-all

# View documentation
cat docs/README.md
```

---

## 🎯 What NOT to Suggest

❌ **Don't suggest:**
- Creating a documentation folder (already exists: /docs)
- Building a script manager (already exists: run_script.py)
- Improving sentiment analysis prompts (already done: V2 with +15-20% improvement)
- Integrating news sentiment (already done: Google Gemini + NewsAPI)
- Creating docs README (already done: docs/README.md)

✅ **DO suggest improvements to:**
- Existing sentiment analysis (but reference V2 baseline)
- New script additions (add to scripts.yaml)
- Documentation improvements
- ML model enhancements
- New trading strategies
- Additional backtesting analysis

---

## 📚 Documentation Quick Navigation

| Need | Location |
|------|----------|
| Setup & Installation | docs/guides/NEWS_ANALYZER_SETUP.md |
| System Architecture | docs/guides/INTEGRATION_SUMMARY.md |
| Sentiment Analysis Details | docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md |
| Prompt Engineering | docs/prompts/PROMPT_OPTIMIZATION.md |
| Docs Index | docs/README.md |
| Project Specs | CLAUDE.md |

---

## 🤖 Model Information

- **ML Architecture**: LSTM + Transformer hybrid (70,587 params)
- **Ensemble Method**: LSTM + XGBoost voting
- **Sentiment Model**: Google Gemini 2.5 Flash
- **News Source**: NewsAPI (5 articles per signal)
- **Accuracy**: 85-90% (after V2 prompt optimization)

---

## 📋 Available Scripts (41 Total)

### Data (4)
- fetch-spy, fetch-multi, fetch-all, status

### Train (6)
- lstm-gld, lstm-msft, lstm-btc, lstm-all, expansion, ensemble

### Signals (7)
- signal-gld, signal-single, ensemble-basic, ensemble-expanded, ensemble-specific, scan, watch

### Backtest (4)
- backtest-macd, backtest-rsi, backtest-ma, backtest-all

### News (5)
- test-gld, test-msft, test-btc, test-multi, test-custom

### Test (7)
- test-all, test-data, test-indicators, test-strategies, test-backtesting, test-signals, test-coverage

### Docs (3)
- list-strategies, show-config, view-guide

### Workflows (5)
- daily-check, quick-signals, full-backtest, ml-update, full-test

---

## 🚨 Critical Points

1. **Always acknowledge** you've read all 5 required documents
2. **Check scripts.yaml** before suggesting new scripts
3. **Reference V2 prompt** when discussing sentiment analysis
4. **Use run_script.py** to show command examples
5. **Maintain /docs structure** when adding new documentation

---

## 📞 When Stuck

- Check **docs/README.md** for navigation
- Review **scripts.yaml** for available commands
- Read **CLAUDE.md** for architecture decisions
- Check recent commits: `git log --oneline -10`

---

## ✅ Verification Checklist

Before helping the user, confirm:

- [ ] Read CLAUDE.md completely
- [ ] Read docs/README.md
- [ ] Read docs/guides/INTEGRATION_SUMMARY.md
- [ ] Read docs/prompts/PROMPT_IMPROVEMENTS_SUMMARY.md
- [ ] Read docs/guides/NEWS_ANALYZER_SETUP.md
- [ ] Understood current system state
- [ ] Aware of all 41 available scripts
- [ ] Ready to help without suggesting already-implemented features

**Do not proceed until all items are checked.**

---

## 🎓 Pro Tips for Agents

1. **Always start sessions by reading /docs** - It's the source of truth
2. **Use run_script.py examples** - Shows modern project structure
3. **Reference V2 prompt improvements** - Show you understand recent work
4. **Check git log** - Understand recent changes
5. **Maintain documentation** - Keep /docs updated with new changes

---

**Last Updated:** 2026-02-14
**Status:** Ready for Production ✅
**Next Session:** Please read all 5 required documents first!
