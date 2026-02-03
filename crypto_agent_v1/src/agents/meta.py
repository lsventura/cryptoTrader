import yaml

def evaluator_agent(state):
    # Simula cálculo de Sharpe Ratio simples: retorno médio / desvio padrão
    pnl = state.get('pnl_history', [0])
    win_rate = len([x for x in pnl if x > 0]) / len(pnl) if pnl else 0
    
    return {"metrics": {"win_rate": win_rate, "status": "approved" if win_rate > 0.5 else "review"}}

def tuner_agent(state, cfg_path="config/config.yaml"):
    if state['metrics']['status'] == "review":
        with open(cfg_path, "r") as f:
            cfg = yaml.safe_load(f)
        
        # Auto-ajuste: reduz risco se o winrate cair
        cfg['trading']['risk_per_trade_pct'] *= 0.9
        
        with open(cfg_path, "w") as f:
            yaml.dump(cfg, f)
        print("Tuner: Configurações otimizadas para segurança.")
    return {}
