import ccxt
import pandas as pd
import numpy as np
import ta
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
import vectorbt as vbt
import logging
import warnings

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def _fetch_data(symbol, timeframe, num_days=730):
    exchange = ccxt.binance()
    end_timestamp = exchange.milliseconds()
    since = end_timestamp - (num_days * 24 * 60 * 60 * 1000)
    all_ohlcv = []
    while since < end_timestamp:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv: break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
        except Exception as e:
            logger.error(f"Erro ao buscar dados para {symbol}: {e}")
            return None
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    if df.empty: return None
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df.index = df.index.tz_localize('UTC')
    df = df[~df.index.duplicated(keep='first')]
    return df

def _engineer_features(df: pd.DataFrame):
    df['rsi_14'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['atr_14'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    for tf in ['1H', '4H']:
        df_resampled = df.resample(tf).agg({'close': 'last', 'high': 'max', 'low': 'min'})
        ema_fast = ta.trend.EMAIndicator(df_resampled['close'], window=20).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(df_resampled['close'], window=50).ema_indicator()
        df[f'ema_trend_{tf}'] = (ema_fast > ema_slow).astype(int).reindex(df.index, method='ffill')
    df_weekly = df.resample('D').agg({'close': 'last'}).resample('W').last()
    weekly_ema_fast = ta.trend.EMAIndicator(df_weekly['close'], window=10).ema_indicator()
    weekly_ema_slow = ta.trend.EMAIndicator(df_weekly['close'], window=21).ema_indicator()
    df_weekly['is_macro_bull'] = (weekly_ema_fast > weekly_ema_slow)
    df['is_macro_bull'] = df_weekly['is_macro_bull'].reindex(df.index, method='ffill')
    df['is_macro_bull'].fillna(False, inplace=True)
    return df

def _define_target(df: pd.DataFrame, periods=5, threshold=0.004):
    df['future_return'] = df['close'].shift(-periods) / df['close'] - 1
    df['target'] = 0
    df.loc[df['future_return'] > threshold, 'target'] = 1
    df.loc[df['future_return'] < -threshold, 'target'] = -1
    df.drop(columns=['future_return'], inplace=True)
    df.dropna(inplace=True)
    return df

def _train_model(train_df: pd.DataFrame, test_df: pd.DataFrame):
    features = [col for col in train_df.columns if col not in ['open', 'high', 'low', 'close', 'volume', 'target']]
    X_train = train_df[features]
    y_train = train_df['target']
    X_test = test_df[features]
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    y_train_mapped = y_train + 1
    params = {'objective': 'multiclass', 'num_class': 3, 'metric': 'multi_logloss', 'boosting_type': 'gbdt',
              'n_estimators': 500, 'learning_rate': 0.01, 'num_leaves': 20, 'max_depth': 5,
              'seed': 42, 'n_jobs': -1, 'verbose': -1, 'colsample_bytree': 0.7, 'subsample': 0.7}
    lgbm = lgb.LGBMClassifier(**params)
    lgbm.fit(X_train_scaled, y_train_mapped)
    probabilities = lgbm.predict_proba(X_test_scaled)
    test_df_processed = test_df.copy()
    test_df_processed['P_BAIXA'] = probabilities[:, 0]
    test_df_processed['P_NEUTRO'] = probabilities[:, 1]
    test_df_processed['P_ALTA'] = probabilities[:, 2]
    return test_df_processed

def _run_backtest_logic(df: pd.DataFrame, params: dict):
    sniper_filter = ~df['is_macro_bull'] & (df['ema_trend_1H'] == 1)
    entries_sniper = (df['P_ALTA'] > params['prob_threshold']) & sniper_filter
    hunter_filter = df['is_macro_bull'] & (df['ema_trend_1H'] == 1)
    entries_hunter = (df['P_ALTA'] > params['bull_prob_threshold']) & hunter_filter
    entries_long = entries_sniper | entries_hunter
    regime_change_exit = (df['is_macro_bull'].shift(1) == True) & (df['is_macro_bull'] == False)
    sl_long = df['close'] - (df['atr_14'] * params['atr_multiplier'])
    tp_long = np.where(entries_sniper, df['close'] + ((df['close'] - sl_long) * params['rr_ratio']), np.nan)
    tsl_long = np.where(entries_hunter, params['tsl_pct'], np.nan)
    sl_pct = (df['close'] - sl_long) / df['close']
    size = (params['risk_per_trade'] / sl_pct) * params['leverage']
    size.clip(upper=params['leverage'], inplace=True)
    
    pf = vbt.Portfolio.from_signals(
        close=df['close'], entries=entries_long, exits=regime_change_exit,
        short_entries=pd.Series(False, index=df.index), sl_stop=sl_long,
        tp_stop=tp_long, sl_trail=tsl_long,
        size=size, size_type='percent', init_cash=params['initial_capital'], freq=params['timeframe']
    )
    return pf.stats()

def run_single_backtest(params: dict):
    try:
        logger.info(f"A iniciar backtest para: {params['symbol']} @ {params['timeframe']}")
        raw_df = _fetch_data(params['symbol'], params['timeframe'])
        if raw_df is None or len(raw_df) < 500:
            logger.warning("Dados insuficientes para o backtest.")
            return None
        featured_df = _engineer_features(raw_df.copy())
        final_df = _define_target(featured_df.copy())
        split_date = (final_df.index.max() - pd.Timedelta(days=180))
        train_df = final_df.loc[final_df.index < split_date]
        test_df = final_df.loc[final_df.index >= split_date]
        if train_df.empty or test_df.empty or len(train_df) < 200 or len(test_df) < 200:
            logger.warning("Dados insuficientes nos conjuntos de treino/teste.")
            return None
        test_data_with_probs = _train_model(train_df, test_df)
        stats = _run_backtest_logic(test_data_with_probs, params)
        return stats
    except Exception as e:
        logger.error(f"Falha irrecuperável no backtest para os parâmetros {params}. Erro: {e}", exc_info=False)
        return None