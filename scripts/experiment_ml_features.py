"""
Experimento offline: compara feature sets x esquemas de etiquetado para el
XGBoost cross-sectional, sin tocar los modelos de producción. Reporta
accuracy/precision/recall vs baseline (feature de precio crudo dominante)
por intervalo. Ver investigación en la sesión 2026-07-28.
"""
import logging, warnings
logging.disable(logging.CRITICAL); warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import MinMaxScaler

from data.fetcher import DataFetcher
from indicators.technical import TechnicalIndicators
from config.settings import DEFAULT_TICKERS, XGBOOST_CONFIG, TRIPLE_BARRIER_CONFIG

fetcher = DataFetcher()

# --- feature sets ---
OLD_FEATURES = ['open', 'high', 'low', 'close', 'volume', 'rsi', 'macd',
                'bb_upper', 'bb_lower', 'return_5d', 'return_20d',
                'volatility_20d', 'atr_ratio']

# All stationary / cross-sectionally comparable
NEW_FEATURES = ['rsi', 'stoch_k', 'adx', 'plus_di', 'minus_di',
                'bb_percent', 'bb_bandwidth', 'return_5d', 'return_20d',
                'volatility_20d', 'atr_ratio',
                'close_vwap_ratio', 'close_sma50_ratio', 'sma50_sma200_ratio',
                'macd_norm', 'macd_hist_norm', 'rel_volume']


def add_stationary(df):
    df = df.copy()
    df['close_vwap_ratio'] = df['close'] / df['vwap'] - 1
    df['close_sma50_ratio'] = df['close'] / df['sma_50'] - 1
    df['sma50_sma200_ratio'] = df['sma_50'] / df['sma_200'] - 1
    df['macd_norm'] = df['macd'] / df['close']
    df['macd_hist_norm'] = df['macd_histogram'] / df['close']
    df['rel_volume'] = df['volume'] / df['volume'].rolling(20).mean()
    return df


def triple_barrier(df, pf=1.5, sf=1.5, h=5):
    close = df['close'].values
    atr = df['atr'].values if 'atr' in df.columns else np.full(len(df), df['close'].std())
    n = len(df); labels = np.full(n, 1.0, dtype=np.float32)
    for i in range(n - 1):
        vol = atr[i]
        if vol <= 0:
            continue
        up, lo = close[i] + pf * vol, close[i] - sf * vol
        for j in range(i + 1, min(i + h + 1, n)):
            if close[j] >= up:
                labels[i] = 2.0; break
            if close[j] <= lo:
                labels[i] = 0.0; break
    return labels


def make_labels(df, scheme):
    if scheme == 'binary_thr':       # actual: masked 0.5%
        ret = df['close'].pct_change(1).shift(-1)
        y = pd.Series(0, index=df.index); y[ret > 0.005] = 1
        mask = (ret > 0.005) | (ret < -0.005)
        return y, mask
    if scheme == 'binary_dir':       # unmasked next-bar direction
        y = (df['close'].shift(-1) > df['close']).astype(int)
        return y, pd.Series(True, index=df.index)
    if scheme == 'triple_barrier':   # all bars, 3-class
        y = pd.Series(triple_barrier(df), index=df.index)
        return y, pd.Series(True, index=df.index)


def build_model(n_classes):
    return xgb.XGBClassifier(
        n_estimators=XGBOOST_CONFIG['n_estimators'], max_depth=XGBOOST_CONFIG['max_depth'],
        learning_rate=XGBOOST_CONFIG['learning_rate'], subsample=XGBOOST_CONFIG['subsample'],
        colsample_bytree=XGBOOST_CONFIG['colsample_bytree'],
        min_child_weight=XGBOOST_CONFIG['min_child_weight'], reg_alpha=XGBOOST_CONFIG['reg_alpha'],
        reg_lambda=XGBOOST_CONFIG['reg_lambda'], random_state=42, verbosity=0,
        eval_metric='mlogloss' if n_classes > 2 else 'logloss')


def run(interval, features, scheme, use_stationary):
    train_X, train_y, test_X, test_y = [], [], [], []
    for t in DEFAULT_TICKERS:
        try:
            df = TechnicalIndicators.add_all_indicators(fetcher.load_from_csv(t, interval))
        except FileNotFoundError:
            continue
        if use_stationary:
            df = add_stationary(df)
        avail = [f for f in features if f in df.columns]
        X = df[avail].replace([np.inf, -np.inf], np.nan).dropna()
        dfa = df.loc[X.index]
        y, mask = make_labels(dfa, scheme)
        y = y.loc[X.index]; mask = mask.loc[X.index]
        if scheme == 'triple_barrier':
            X, y = X.iloc[:-5], y.iloc[:-5]
        X, y = X[mask.loc[X.index]], y[mask.loc[X.index]]
        if len(X) < 50:
            continue
        s = int(len(X) * 0.85)
        train_X.append(X.iloc[:s].values.astype(np.float32)); train_y.append(y.iloc[:s].values)
        test_X.append(X.iloc[s:].values.astype(np.float32)); test_y.append(y.iloc[s:].values)

    Xtr = np.vstack(train_X); ytr = np.concatenate(train_y)
    Xte = np.vstack(test_X); yte = np.concatenate(test_y)
    sc = MinMaxScaler().fit(Xtr)
    Xtr, Xte = sc.transform(Xtr), sc.transform(Xte)

    n_classes = len(np.unique(ytr))
    # class weights
    uniq, cnt = np.unique(ytr, return_counts=True)
    w = np.ones(len(ytr))
    for c, ct in zip(uniq, cnt):
        w[ytr == c] = len(ytr) / (len(uniq) * ct)

    m = build_model(n_classes)
    m.fit(Xtr, ytr, sample_weight=w, verbose=0)
    pred = m.predict(Xte)
    acc = (pred == yte).mean()
    # directional precision (up class = max label)
    up = max(uniq)
    tp = ((pred == up) & (yte == up)).sum()
    prec = tp / max((pred == up).sum(), 1)
    rec = tp / max((yte == up).sum(), 1)
    baseline = max(np.mean(yte == c) for c in np.unique(yte))
    return dict(acc=acc, prec=prec, rec=rec, baseline=baseline, n_test=len(yte), n_train=len(ytr))


if __name__ == '__main__':
    configs = [
        ('OLD feats  + binary_thr  (ACTUAL)', OLD_FEATURES, 'binary_thr', False),
        ('NEW feats  + binary_thr',            NEW_FEATURES, 'binary_thr', True),
        ('NEW feats  + binary_dir',            NEW_FEATURES, 'binary_dir', True),
        ('NEW feats  + triple_barrier',        NEW_FEATURES, 'triple_barrier', True),
        ('OLD feats  + triple_barrier',        OLD_FEATURES, 'triple_barrier', False),
    ]
    for interval in ['1d', '1h', '1m']:
        print(f"\n{'='*90}\nINTERVAL {interval}\n{'='*90}")
        print(f"{'config':38} {'n_train':>8} {'n_test':>7} {'acc':>7} {'base':>7} {'edge':>7} {'prec':>7} {'rec':>7}")
        for name, feats, scheme, stat in configs:
            try:
                r = run(interval, feats, scheme, stat)
                edge = r['acc'] - r['baseline']
                print(f"{name:38} {r['n_train']:>8} {r['n_test']:>7} {r['acc']:>7.4f} "
                      f"{r['baseline']:>7.4f} {edge:>+7.4f} {r['prec']:>7.4f} {r['rec']:>7.4f}")
            except Exception as e:
                print(f"{name:38} ERROR: {e}")
