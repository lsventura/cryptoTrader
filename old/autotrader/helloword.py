# ==============================================================================
# MÓDULOS 1-5: SISTEMA COMPLETO DE TRADING ALGORÍTMICO
# ==============================================================================
import ccxt
import pandas as pd
import numpy as np
import ta
import lightgbm as lgb
import vectorbt as vbt   # <--- ADICIONE ESTA LINHA
from sklearn.preprocessing import StandardScaler
import vectorbt as vbt
import warnings

warnings.filterwarnings('ignore')

# ==============================================================================
# MÓDULO 1: COLETA E ENGENHARIA DE FEATURES
# ==============================================================================
# Substitua sua função fetch_data por esta versão mais robusta
# Substitua sua função fetch_data por esta versão final
def fetch_data(symbol='BTC/USDT', timeframe='15m', num_days=365, end_date_str=None):
    """
    Busca dados históricos para um número específico de dias, terminando em uma data específica.
    Se end_date_str for None, usa a data e hora atuais.
    """
    print(f"Buscando dados para {symbol} nos últimos {num_days} dias...")
    exchange = ccxt.binance()
    
    if end_date_str:
        end_timestamp = exchange.parse8601(end_date_str)
    else:
        end_timestamp = exchange.milliseconds()

    since = end_timestamp - (num_days * 24 * 60 * 60 * 1000)
    
    all_ohlcv = []
    while since < end_timestamp:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
        except Exception as e:
            print(f"Erro ao buscar dados: {e}")
            break
            
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    if df.empty:
        print("Nenhum dado foi retornado. Verifique o par e as datas.")
        return df
        
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # CORREÇÃO: Torna o índice 'tz-aware' (consciente do fuso horário UTC)
    # Isso garante que o índice e a data de comparação tenham o mesmo fuso horário.
    df.index = df.index.tz_localize('UTC')
    
    df = df[~df.index.duplicated(keep='first')]
    
    if end_date_str:
        # Agora a comparação funciona, pois ambos os lados são 'tz-aware' em UTC.
        df = df[df.index <= pd.to_datetime(end_date_str, utc=True)]
    
    print(f"Dados coletados com sucesso: {len(df)} candles de {df.index.min()} a {df.index.max()}")
    return df


# Substitua sua função engineer_features por esta
def engineer_features(df: pd.DataFrame):
    print("Iniciando a engenharia de features...")
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    
    # --- Indicadores Padrão (15m) ---
    df['rsi_14'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['rsi_28'] = ta.momentum.RSIIndicator(df['close'], window=28).rsi()
    stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    df['ema_200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
    df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
    df['atr_14'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    
    # --- Contexto de Timeframes Médios (1H, 4H) ---
    for tf in ['1H', '4H']:
        df_resampled = df.resample(tf).agg({'close': 'last', 'high': 'max', 'low': 'min'})
        df[f'rsi_14_{tf}'] = ta.momentum.RSIIndicator(df_resampled['close'], window=14).rsi().reindex(df.index, method='ffill')
        ema_fast = ta.trend.EMAIndicator(df_resampled['close'], window=20).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(df_resampled['close'], window=50).ema_indicator()
        df[f'ema_trend_{tf}'] = (ema_fast > ema_slow).astype(int).reindex(df.index, method='ffill')
        
    # --- NOVO: FILTRO DE REGIME MACRO (SEMANAL) ---
    print("Criando filtro de regime macro (semanal)...")
    # Para obter dados semanais, primeiro resample para diário e depois para semanal
    df_weekly = df.resample('D').agg({'close': 'last'}).resample('W').last()
    
    # Usamos EMAs mais longas para o regime macro
    weekly_ema_fast = ta.trend.EMAIndicator(df_weekly['close'], window=10).ema_indicator()
    weekly_ema_slow = ta.trend.EMAIndicator(df_weekly['close'], window=21).ema_indicator()
    
    # O sinal de 'macro bull' é quando a EMA rápida está acima da lenta
    df_weekly['is_macro_bull'] = (weekly_ema_fast > weekly_ema_slow)
    
    # Mapeia o estado do regime semanal de volta para cada vela de 15m
    df['is_macro_bull'] = df_weekly['is_macro_bull'].reindex(df.index, method='ffill')
    df['is_macro_bull'].fillna(False, inplace=True) # Preenche NaNs no início como 'False' (seguro)

    print("Engenharia de features concluída.")
    return df


def define_target(df: pd.DataFrame, periods=5, threshold=0.004):
    print("Definindo a variável alvo...")
    df['future_return'] = df['close'].shift(-periods) / df['close'] - 1
    
    df['target'] = 0 # NEUTRO
    df.loc[df['future_return'] > threshold, 'target'] = 1  # ALTA
    df.loc[df['future_return'] < -threshold, 'target'] = -1 # BAIXA
    
    df.drop(columns=['future_return'], inplace=True)
    df.dropna(inplace=True)
    
    print("Distribuição das classes:")
    print(df['target'].value_counts(normalize=True))
    return df

# ==============================================================================
# MÓDULO 2: ARQUITETURA E TREINAMENTO DO MODELO
# ==============================================================================
# Substitua sua função train_model por esta
def train_model(train_df: pd.DataFrame, test_df: pd.DataFrame):
    """
    Treina o modelo usando o train_df e faz previsões no test_df.
    """
    print("\n--- Iniciando Módulo 2: Treinamento de Modelo (Out-of-Sample) ---")
    
    features = [col for col in train_df.columns if col not in ['open', 'high', 'low', 'close', 'volume', 'target']]
    
    # Prepara os dados de treino e teste
    X_train = train_df[features]
    y_train = train_df['target']
    X_test = test_df[features]

    # Mapeia y para [0, 1, 2] para o LightGBM
    y_train_mapped = y_train + 1
    
    print(f"Treinando modelo em {len(X_train)} amostras do período de treino...")
    
    params = {'objective': 'multiclass', 'num_class': 3, 'metric': 'multi_logloss', 'boosting_type': 'gbdt',
              'n_estimators': 500, 'learning_rate': 0.01, 'num_leaves': 20, 'max_depth': 5,
              'seed': 42, 'n_jobs': -1, 'verbose': -1, 'colsample_bytree': 0.7, 'subsample': 0.7}
    
    lgbm = lgb.LGBMClassifier(**params)
    lgbm.fit(X_train, y_train_mapped)
    
    print("Modelo treinado. Fazendo previsões no período de teste (dados não vistos)...")
    probabilities = lgbm.predict_proba(X_test)
    
    # Adiciona as probabilidades ao dataframe de teste
    test_df_processed = test_df.copy()
    test_df_processed['P_BAIXA'] = probabilities[:, 0]
    test_df_processed['P_NEUTRO'] = probabilities[:, 1]
    test_df_processed['P_ALTA'] = probabilities[:, 2]
    
    return test_df_processed

# ==============================================================================
# MÓDULOS 3, 4, 5: SINAL, RISCO E BACKTEST
# ==============================================================================
# Substitua sua função run_backtest por esta versão corrigida
# Substitua sua função run_backtest por esta versão final e mais segura
# Substitua sua função run_backtest por esta versão final e compatível
# Substitua sua função run_backtest por esta versão final, focada apenas em LONG
# Substitua sua função run_backtest por esta versão final e corrigida
# Substitua sua função run_backtest por esta versão final e correta
# Substitua sua função run_backtest por esta versão final e simplificada
# Substitua sua função run_backtest por esta versão final, compatível e estrategicamente correta
# Substitua sua função run_backtest por esta versão para testar o Time Stop
def run_backtest(df: pd.DataFrame, prob_threshold=0.65, atr_multiplier=2.5, rr_ratio=1.7, 
                 bull_prob_threshold=0.60, time_stop_candles=192, # Parâmetro do time stop está de volta
                 risk_per_trade=0.015, initial_capital=10000, leverage=3.0):
    
    print(f"\n--- Iniciando Backtest (MODO HÍBRIDO com TIME STOP DE {time_stop_candles / 4} HORAS) ---")
    
    # --- LÓGICA DE ENTRADA ---
    sniper_long_filter = ~df['is_macro_bull'] & (df['ema_trend_1H'] == 1) & (df['adx'] > 20)
    entries_sniper = (df['P_ALTA'] > prob_threshold) & sniper_long_filter
    hunter_long_filter = df['is_macro_bull'] & (df['ema_trend_1H'] == 1)
    entries_hunter = (df['P_ALTA'] > bull_prob_threshold) & hunter_long_filter
    entries_long = entries_sniper | entries_hunter

    # --- LÓGICA DE SAÍDA ---
    # A única saída explícita manual é a mudança de regime.
    exits_long = (df['is_macro_bull'].shift(1) == True) & (df['is_macro_bull'] == False)

    # --- GERENCIAMENTO DE RISCO com Time Stop ---
    sl_long = df['close'] - (df['atr_14'] * atr_multiplier)
    
    # TP para Sniper
    tp_long = np.where(entries_sniper, df['close'] + ((df['close'] - sl_long) * rr_ratio), np.nan)
    
    # TRAILING STOP ESTÁ DESATIVADO (np.nan) para permitir que o Time Stop funcione
    tsl_long = np.nan 
    
    # TIME STOP está ATIVADO para as entradas "Hunter"
    final_ts_stop = np.where(entries_hunter, time_stop_candles, np.nan)

    # Dimensionamento de Posição
    sl_pct = (df['close'] - sl_long) / df['close']
    size = (risk_per_trade / sl_pct) * leverage
    size.clip(upper=leverage, inplace=True)
    
    # --- BACKTESTING (com os erros de versão corrigidos) ---
    pf = vbt.Portfolio.from_signals(
        close=df['close'],
        entries=entries_long,
        exits=exits_long,
        short_entries=pd.Series(False, index=df.index), # Shorts desativados
        sl_stop=sl_long,
        tp_stop=tp_long, 
        sl_trail=tsl_long,
        ts_stop=final_ts_stop,
        size=size,
        size_type='percent',
        init_cash=initial_capital,
        freq='15T'
    )
    
    print("\n--- RESULTADOS DO BACKTEST ---")
    print(pf.stats())
    pf.plot().show()
    
# ==============================================================================
# Execução Principal
# ==============================================================================
# Substitua seu bloco de execução principal por este
if __name__ == '__main__':
    # --- Parâmetros de Configuração ---
    SYMBOL = 'ETH/USDT'
    TIMEFRAME = '15m'
    
    PROBABILITY_THRESHOLD = 0.65
    ATR_MULTIPLIER = 2.5
    RR_RATIO = 1.7
    BULL_PROB_THRESHOLD = 0.60
    TIME_STOP_CANDLES = 96 # <-- Testando com 24 horas (48h * 4 candles/h)
    RISK_PER_TRADE = 0.015
    INITIAL_CAPITAL = 10000
    LEVERAGE = 5.0

    # --- Lógica de Dados e Separação ---
    END_DATE = pd.to_datetime('now', utc=True).strftime('%Y-%m-%dT%H:%M:%SZ')
    raw_df = fetch_data(symbol=SYMBOL, timeframe=TIMEFRAME, num_days=730, end_date_str=END_DATE)
    featured_df = engineer_features(raw_df.copy())
    final_df = define_target(featured_df.copy())
    
    split_date = (pd.to_datetime(END_DATE) - pd.Timedelta(days=180)).strftime('%Y-%m-%d')
    train_df = final_df.loc[:split_date]
    test_df = final_df.loc[split_date:]

    print("\n--- SEPARAÇÃO DE DADOS EM TREINO E TESTE ---")
    print(f"Período de Treino: {train_df.index.min()} a {train_df.index.max()} ({len(train_df)} amostras)")
    print(f"Período de Teste:  {test_df.index.min()} a {test_df.index.max()} ({len(test_df)} amostras)")

    if not train_df.empty and not test_df.empty:
        test_data_with_probs = train_model(train_df, test_df)
        
        # Executa o backtest com a nova configuração
        run_backtest(
            df=test_data_with_probs,
            prob_threshold=PROBABILITY_THRESHOLD,
            atr_multiplier=ATR_MULTIPLIER,
            rr_ratio=RR_RATIO,
            bull_prob_threshold=BULL_PROB_THRESHOLD,
            time_stop_candles=TIME_STOP_CANDLES, # <-- Parâmetro está de volta
            risk_per_trade=RISK_PER_TRADE,
            initial_capital=INITIAL_CAPITAL,
            leverage=LEVERAGE
        )
    else:
        print("Falha na separação de treino/teste. Verifique as datas e a quantidade de dados.")

