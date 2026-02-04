import pandas as pd
import pandas_ta as ta
import yaml
import os
import numpy as np

def optimize_params(candles, current_cfg):
    """
    Otimizador com foco em candles RECENTES (últimas 48-72 barras)
    para evitar overfitting em eventos extremos (crashes, spikes).
    
    Estratégia:
    - Usa apenas os últimos 72 candles
    - Aplica peso 2x para os últimos 24 candles (últimas 6h em 15m)
    - Ignora crashes/eventos de > 24h atrás
    """
    df = candles.copy()
    best_pnl = -9999
    best_params = {"rsi_buy": 45, "rsi_sell": 55, "ema_filter": 20}  # Neutro por padrão
    
    # Limitar ao histórico recente (últimos 72 candles = 18h em 15m)
    window_size = min(72, len(df))
    df_recent = df.tail(window_size).reset_index(drop=True)
    
    if len(df_recent) < 20:
        print("   ⚠️ Tuner: Dados insuficientes para otimizar. Usando padrão neutro.")
        return best_params
    
    print(f"   🔎 Otimizando com foco nos últimos {window_size} candles...")
    
    # Grid de busca
    for rsi_limit in [30, 35, 40, 45, 50, 55]:
        for ema_len in [14, 20, 50]:
            
            # Calcula indicadores
            df_recent['rsi'] = ta.rsi(df_recent['close'], length=14)
            df_recent['ema'] = ta.ema(df_recent['close'], length=ema_len)
            
            # Sinais
            long_condition = (df_recent['rsi'] < rsi_limit) & (df_recent['close'] > df_recent['ema'])
            short_condition = (df_recent['rsi'] > (100 - rsi_limit)) & (df_recent['close'] < df_recent['ema'])
            
            # Retornos (shift -1 = próximo candle)
            df_recent['next_return'] = df_recent['close'].pct_change().shift(-1)
            
            # PnL por tipo de sinal
            pnl_long = df_recent.loc[long_condition, 'next_return'].sum()
            pnl_short = df_recent.loc[short_condition, 'next_return'].sum() * -1
            
            # ===== INOVAÇÃO: PESO RECENTE =====
            # Últimos 24 candles = 2x peso; anteriores = 1x peso
            lookback_recent = min(24, len(df_recent))
            df_recent['weight'] = 1.0
            df_recent.iloc[-lookback_recent:, df_recent.columns.get_loc('weight')] = 2.0
            
            # PnL ponderado
            pnl_long_weighted = (df_recent.loc[long_condition, 'next_return'] * df_recent.loc[long_condition, 'weight']).sum()
            pnl_short_weighted = (df_recent.loc[short_condition, 'next_return'] * df_recent.loc[short_condition, 'weight']).sum() * -1
            
            total_pnl_weighted = pnl_long_weighted + pnl_short_weighted
            
            if total_pnl_weighted > best_pnl:
                best_pnl = total_pnl_weighted
                best_params = {
                    "rsi_buy": int(rsi_limit),
                    "rsi_sell": int(100 - rsi_limit),
                    "ema_filter": int(ema_len)
                }
    
    print(f"   ✅ Melhor Setup (foco recente): RSI {best_params['rsi_buy']} / EMA {best_params['ema_filter']} (Score: {best_pnl:.6f})")
    return best_params

def tuner_agent(state, cfg_path="config/config.yaml"):
    candles = state.get('candles')
    if candles is None or len(candles) < 50:
        print("   ⚠️ Tuner: Poucos dados para otimizar.")
        return {}

    # Carrega config
    if not os.path.exists(cfg_path):
        print(f"   ❌ Erro: Config não encontrado em {cfg_path}")
        return {}
        
    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f)
        
    # Garante que a chave existe
    if 'strategy' not in cfg:
        cfg['strategy'] = {}

    # Otimiza
    try:
        new_params = optimize_params(candles, cfg)
        
        # Salva Forçado
        cfg['strategy'] = new_params
        with open(cfg_path, "w") as f:
            yaml.dump(cfg, f)
        print(f"   💾 Config salva em {cfg_path}")
        
    except Exception as e:
        print(f"   ❌ Erro no Otimizador: {e}")
        
    return {"tuner_done": True}
