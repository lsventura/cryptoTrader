import pandas as pd
import pandas_ta as ta
import yaml
import os

def optimize_params(candles, current_cfg):
    df = candles.copy()
    best_pnl = -9999
    # Padrão de segurança caso não ache nada
    best_params = {"rsi_buy": 35, "rsi_sell": 65, "ema_filter": 50}
    
    print("   🔎 Otimizando: Testando combinações...")
    
    # Reduzi o grid para ser mais rápido e garantir execução
    for rsi_limit in [30, 35, 40, 45, 50]:
        for ema_len in [20, 50, 100]:
            
            # Recalcula indicadores
            df['rsi'] = ta.rsi(df['close'], length=14)
            df['ema'] = ta.ema(df['close'], length=ema_len)
            
            # Simulação Vetorizada (MUITO mais rápida e segura que loop for)
            # Regra Long: RSI < limit E Close > EMA
            long_condition = (df['rsi'] < rsi_limit) & (df['close'] > df['ema'])
            # Regra Short: RSI > (100-limit) E Close < EMA
            short_condition = (df['rsi'] > (100-rsi_limit)) & (df['close'] < df['ema'])
            
            # Calcula retornos onde a condição foi atendida
            # Simplificação: Soma dos retornos dos candles seguintes aos sinais
            df['next_return'] = df['close'].pct_change().shift(-1)
            
            pnl_long = df.loc[long_condition, 'next_return'].sum()
            pnl_short = df.loc[short_condition, 'next_return'].sum() * -1
            
            total_pnl = pnl_long + pnl_short
            
            if total_pnl > best_pnl:
                best_pnl = total_pnl
                best_params = {
                    "rsi_buy": int(rsi_limit),
                    "rsi_sell": int(100 - rsi_limit),
                    "ema_filter": int(ema_len)
                }
    
    print(f"   ✅ Melhor Setup: RSI {best_params['rsi_buy']} / EMA {best_params['ema_filter']} (Score: {best_pnl:.4f})")
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
