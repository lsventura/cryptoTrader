import ccxt
import pandas as pd
import pandas_ta as ta

def get_market_data(cfg):
    ex = getattr(ccxt, cfg['exchange']['name'])()
    if cfg['exchange']['testnet']: ex.set_sandbox_mode(True)
    
    bars = ex.fetch_ohlcv(cfg['trading']['symbol'], timeframe=cfg['trading']['timeframe'], limit=100)
    df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    
    # Indicadores Técnicos 2026
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['ema_20'] = ta.ema(df['close'], length=20)
    return df
