#!/usr/bin/env python3
"""
LoRA fine-tuning for TimesFM 2.5 on CFD trading data.

Applies LoRA to the native timesfm PyTorch module (tfm.model) by calling
model.forward() directly, bypassing model.decode() which has torch.no_grad().

Training objective:
  - RevIN-normalize input patches
  - Forward pass through LoRA-modified transformer
  - Reshape output_ts (batch, patches, o*q) → (batch, o, q)
  - MSE on point forecast (quantile index 5 = median) vs normalized target

Inference evaluation uses tfm.forecast() unchanged — LoRA weights apply
automatically through the modified Linear layers.

Usage:
    python3 scripts/train_timesfm_lora.py --batch A   # SPY 1d
    python3 scripts/train_timesfm_lora.py --batch B   # all 19 tickers 1d
    python3 scripts/train_timesfm_lora.py --batch C   # SPY 1h
    python3 scripts/train_timesfm_lora.py --compare   # compare saved models
"""

import argparse
import logging
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yfinance as yf
from torch.utils.data import DataLoader, Dataset

os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ALL_TICKERS = [
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "USO", "UNG",
    "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "TSLA",
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD",
]

BATCH_CONFIGS = {
    "A": dict(tickers=["SPY"],     interval="1d", period="5y",   epochs=10, lora_r=4, lr=1e-4, desc="SPY 1d (conservative)"),
    "B": dict(tickers=ALL_TICKERS, interval="1d", period="5y",   epochs=10, lora_r=8, lr=5e-5, desc="All 19 tickers 1d (generalist)"),
    "C": dict(tickers=["SPY"],     interval="1h", period="730d", epochs=15, lora_r=4, lr=1e-4, desc="SPY 1h (intraday)"),
}

CONTEXT_LEN = 512    # context bars (must be divisible by patch_size=32)
HORIZON_LEN = 24     # forecast steps
N_SAMPLES   = 5000
BATCH_SIZE  = 32
SAVE_DIR    = Path("models/saved")

# LoRA target modules inside the timesfm internal module
LORA_TARGETS = ["attn.qkv_proj", "attn.out", "ff0", "ff1"]


# ── Dataset ───────────────────────────────────────────────────────────────────

class PriceWindowDataset(Dataset):
    def __init__(self, series_list: list[np.ndarray], n_samples: int = N_SAMPLES):
        min_len = CONTEXT_LEN + HORIZON_LEN
        valid   = [s for s in series_list if len(s) >= min_len]
        if not valid:
            raise ValueError(f"No series long enough ({min_len} bars required)")
        rng = np.random.default_rng(42)
        self.samples = []
        for _ in range(n_samples):
            s     = valid[rng.integers(len(valid))]
            start = int(rng.integers(0, len(s) - min_len + 1))
            self.samples.append((s, start))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        s, start = self.samples[i]
        ctx = torch.tensor(s[start:start + CONTEXT_LEN],                              dtype=torch.float32)
        tgt = torch.tensor(s[start + CONTEXT_LEN:start + CONTEXT_LEN + HORIZON_LEN], dtype=torch.float32)
        return ctx, tgt


# ── Data loading ──────────────────────────────────────────────────────────────

def load_series(tickers, interval, period) -> list[np.ndarray]:
    out = []
    for ticker in tickers:
        try:
            df = yf.download(ticker, period=period, interval=interval,
                             progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            close = df["Close"].dropna().values.astype(np.float32)
            if len(close) >= CONTEXT_LEN + HORIZON_LEN:
                out.append(close)
                log.info(f"  {ticker}: {len(close)} bars")
            else:
                log.warning(f"  {ticker}: {len(close)} bars — skipped")
        except Exception as e:
            log.warning(f"  {ticker}: {e}")
    return out


# ── Walk-forward evaluation ───────────────────────────────────────────────────

def walk_forward_mape(tfm, prices: np.ndarray, n_windows: int = 5) -> float:
    step  = len(prices) // (n_windows + 1)
    mapes = []
    for w in range(n_windows):
        end   = len(prices) - (n_windows - w) * step
        start = max(0, end - CONTEXT_LEN)
        ctx   = prices[start:end]
        act   = prices[end:end + HORIZON_LEN]
        if len(act) < HORIZON_LEN:
            continue
        pf, _ = tfm.forecast(horizon=HORIZON_LEN, inputs=[ctx])
        pred  = pf[0][:HORIZON_LEN]
        mapes.append((np.abs(pred - act) / act).mean() * 100)
    return float(np.mean(mapes)) if mapes else float("nan")


# ── Training forward pass ─────────────────────────────────────────────────────

def training_forward(inner_lora, ctx_batch: torch.Tensor, tgt_batch: torch.Tensor,
                     patch_size: int, o: int, q: int) -> torch.Tensor:
    """
    Differentiable forward pass through LoRA-modified transformer.

    Steps:
      1. RevIN normalize context per series
      2. Reshape flat context → patches (batch, num_patches, patch_size)
      3. Call inner_lora.forward(patches, masks) — gradients flow through LoRA
      4. Interpret output_ts[:, -1, :] as (o, q) point+quantile predictions
      5. MSE loss of median forecast (quantile index q//2) vs normalized target

    Returns: scalar loss
    """
    dev = ctx_batch.device

    # RevIN: normalize per series
    mu    = ctx_batch.mean(dim=1, keepdim=True)
    sigma = ctx_batch.std(dim=1, keepdim=True).clamp(min=1e-6)
    ctx_n = (ctx_batch - mu) / sigma
    tgt_n = (tgt_batch - mu) / sigma                   # same scale

    # Patch the context
    batch      = ctx_batch.shape[0]
    num_patches = CONTEXT_LEN // patch_size
    patches    = ctx_n.reshape(batch, num_patches, patch_size)
    masks      = torch.zeros(batch, num_patches, patch_size, dtype=torch.bool, device=dev)

    # Forward through LoRA model (gradients flow here)
    (_, _, output_ts, _), _ = inner_lora(patches, masks)
    # output_ts: (batch, num_patches, hidden=1280) where 1280 = o * q / 8
    # The last patch's output predicts the next o=128 steps
    last_patch_out = output_ts[:, -1, :]               # (batch, 1280)

    # Reshape: (batch, o, q) — each of o steps has q quantile values
    # 1280 / (q=10) = 128 = o  ✓
    forecast = last_patch_out.reshape(batch, q, o).permute(0, 2, 1)  # (batch, o, q)
    # Point forecast = median quantile (index q//2 = 5)
    point = forecast[:, :HORIZON_LEN, q // 2]          # (batch, HORIZON_LEN)

    loss = torch.nn.functional.mse_loss(point, tgt_n)
    return loss


# ── Training ──────────────────────────────────────────────────────────────────

def train_batch(batch_name: str):
    import timesfm
    from timesfm import ForecastConfig
    from peft import LoraConfig, get_peft_model

    cfg = BATCH_CONFIGS[batch_name]
    log.info(f"\n{'='*60}")
    log.info(f"Batch {batch_name}: {cfg['desc']}")
    log.info(f"  Tickers: {len(cfg['tickers'])} | interval: {cfg['interval']}"
             f" | epochs: {cfg['epochs']} | LoRA r={cfg['lora_r']}")
    log.info(f"{'='*60}")

    # ── Load data ──
    log.info("Loading price data...")
    series_list = load_series(cfg["tickers"], cfg["interval"], cfg["period"])
    if not series_list:
        log.error("No data — aborting")
        return None

    dataset    = PriceWindowDataset(series_list, n_samples=N_SAMPLES)
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    log.info(f"Dataset: {len(dataset)} windows from {len(series_list)} series")

    # ── Load TimesFM ──
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info(f"Loading TimesFM on {device}...")
    tfm = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    tfm.compile(ForecastConfig(
        max_context=CONTEXT_LEN, max_horizon=128,
        normalize_inputs=True, infer_is_positive=True,
    ))

    p, o, q = tfm.model.p, tfm.model.o, tfm.model.q
    log.info(f"Model arch: patch={p}, output={o}, quantiles={q}")

    # ── Apply LoRA ──
    lora_cfg = LoraConfig(
        r=cfg["lora_r"], lora_alpha=cfg["lora_r"] * 2,
        target_modules=LORA_TARGETS, lora_dropout=0.05, bias="none",
    )
    inner_lora = get_peft_model(tfm.model, lora_cfg)
    trainable, total = inner_lora.get_nb_trainable_parameters()
    log.info(f"Trainable params: {trainable:,} / {total:,} ({100*trainable/total:.3f}%)")

    # ── Baseline MAPE before training ──
    log.info("Evaluating zero-shot baseline...")
    zs_mape = walk_forward_mape(tfm, series_list[0])
    log.info(f"Zero-shot MAPE ({cfg['tickers'][0]}): {zs_mape:.2f}%")

    # ── Optimizer ──
    optimizer = torch.optim.AdamW(
        [p for p in inner_lora.parameters() if p.requires_grad],
        lr=cfg["lr"], weight_decay=1e-2,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=cfg["epochs"] * len(dataloader),
    )

    # ── Training loop ──
    inner_lora.train()
    t0 = time.time()
    for epoch in range(cfg["epochs"]):
        epoch_loss, n_batches = 0.0, 0
        for ctx_batch, tgt_batch in dataloader:
            ctx_batch = ctx_batch.to(device)
            tgt_batch = tgt_batch.to(device)

            loss = training_forward(inner_lora, ctx_batch, tgt_batch, p, o, q)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(inner_lora.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            epoch_loss += loss.item()
            n_batches  += 1

        avg = epoch_loss / max(n_batches, 1)
        log.info(f"  Epoch {epoch+1:>2}/{cfg['epochs']} — loss: {avg:.6f}")

    elapsed = time.time() - t0
    log.info(f"Training done in {elapsed/60:.1f} min")

    # ── Save LoRA weights ──
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    save_path = SAVE_DIR / f"timesfm_lora_{batch_name}.pt"
    lora_state = {k: v for k, v in inner_lora.state_dict().items() if "lora_" in k}
    torch.save(lora_state, save_path)
    log.info(f"Saved LoRA weights ({len(lora_state)} tensors): {save_path}")

    # ── Post-training eval ──
    inner_lora.eval()
    # LoRA weights are now part of tfm.model's Linear layers — forecast() uses them
    ft_mape = walk_forward_mape(tfm, series_list[0])
    log.info(f"Fine-tuned MAPE ({cfg['tickers'][0]}): {ft_mape:.2f}%  (was {zs_mape:.2f}%)")

    improvement = zs_mape - ft_mape
    sign = "+" if improvement >= 0 else ""
    log.info(f"Improvement: {sign}{improvement:.2f}% MAPE  "
             f"({'better' if improvement >= 0 else 'worse than zero-shot'})")

    return {
        "batch": batch_name, "desc": cfg["desc"],
        "zs_mape": zs_mape, "ft_mape": ft_mape,
        "improvement": improvement, "time_min": elapsed / 60,
        "save_path": str(save_path),
    }


# ── Compare saved batches ─────────────────────────────────────────────────────

def compare_batches():
    import timesfm
    from timesfm import ForecastConfig
    from peft import LoraConfig, get_peft_model

    spy = yf.download("SPY", period="3y", interval="1d", progress=False, auto_adjust=True)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    prices = spy["Close"].dropna().values.astype(np.float32)

    device = "cuda" if torch.cuda.is_available() else "cpu"

    def make_tfm():
        t = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
        t.compile(ForecastConfig(max_context=CONTEXT_LEN, max_horizon=128,
                                 normalize_inputs=True, infer_is_positive=True))
        return t

    log.info("Zero-shot baseline...")
    tfm_zs = make_tfm()
    zs_mape = walk_forward_mape(tfm_zs, prices)

    print(f"\n{'='*60}")
    print(f"{'Model':<35} {'MAPE':>8}  {'vs Baseline':>12}")
    print(f"{'-'*60}")
    print(f"{'Zero-shot (no fine-tuning)':<35} {zs_mape:>7.2f}%  {'—':>12}")

    for name, cfg in BATCH_CONFIGS.items():
        path = SAVE_DIR / f"timesfm_lora_{name}.pt"
        if not path.exists():
            print(f"  Batch {name}: not trained yet")
            continue

        tfm = make_tfm()
        lora_cfg = LoraConfig(
            r=cfg["lora_r"], lora_alpha=cfg["lora_r"] * 2,
            target_modules=LORA_TARGETS, lora_dropout=0.05, bias="none",
        )
        tfm.model = get_peft_model(tfm.model, lora_cfg)
        lora_state = torch.load(path, map_location=device, weights_only=True)
        tfm.model.load_state_dict(lora_state, strict=False)
        tfm.model.eval()

        mape  = walk_forward_mape(tfm, prices)
        delta = mape - zs_mape
        flag  = "✅" if mape < zs_mape else "❌"
        sign  = "+" if delta >= 0 else ""
        label = f"Batch {name} — {cfg['desc']}"
        print(f"  {label:<33} {mape:>7.2f}%  {sign}{delta:.2f}% {flag}")

    print(f"{'='*60}")
    print("✅ better | ❌ worse than zero-shot")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TimesFM LoRA fine-tuning")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch",   choices=["A", "B", "C"])
    group.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    if args.compare:
        compare_batches()
    else:
        result = train_batch(args.batch)
        if result:
            log.info(f"\nDone. MAPE {result['zs_mape']:.2f}% → {result['ft_mape']:.2f}% "
                     f"in {result['time_min']:.1f} min")


if __name__ == "__main__":
    main()
