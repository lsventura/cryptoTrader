import optuna
import logging
import pandas as pd
from research_engine import run_single_backtest

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# --- Bloco Corrigido e Mais Flexível ---
def objective(trial: optuna.trial.Trial):
    params = {
        'symbol': trial.suggest_categorical('symbol', ['ETH/USDT', 'BTC/USDT']),
        'timeframe': trial.suggest_categorical('timeframe', ['15m', '1h']),
        'atr_multiplier': trial.suggest_float('atr_multiplier', 2.0, 4.0),
        'rr_ratio': trial.suggest_float('rr_ratio', 1.5, 3.0),

        # Tornamos ambos os limiares de probabilidade otimizáveis
        'prob_threshold': trial.suggest_float('prob_threshold', 0.60, 0.75),
        'bull_prob_threshold': trial.suggest_float('bull_prob_threshold', 0.50, 0.65), # Reduzimos o limite mínimo
        
        'tsl_pct': trial.suggest_float('tsl_pct', 0.03, 0.12), # Aumentámos o limite máximo
        
        # Parâmetros Fixos
        'risk_per_trade': 0.015,
        'leverage': 5.0,
        'initial_capital': 10000
    }    
    logger.info(f"---> A testar Trial #{trial.number} com os parâmetros: {params}")
    stats = run_single_backtest(params)
    if stats is None or pd.isna(stats['Sortino Ratio']) or stats['Total Trades'] < 10:
        logger.warning(f"<--- Trial #{trial.number} inválido ou com poucos trades. A penalizar.")
        return -1.0 
    sortino_ratio = stats['Sortino Ratio']
    logger.info(f"<--- Trial #{trial.number} concluído. Sortino Ratio: {sortino_ratio:.4f}")
    return sortino_ratio

if __name__ == '__main__':
    study = optuna.create_study(direction="maximize")
    try:
        study.optimize(objective, n_trials=100)
    except KeyboardInterrupt:
        logger.info("Otimização interrompida pelo utilizador.")
    print("\n\n" + "="*50)
    print("--- OTIMIZAÇÃO CONCLUÍDA ---")
    if study.best_trial:
        print(f"Melhor Trial: #{study.best_trial.number}")
        print(f"Melhor Sortino Ratio: {study.best_value:.4f}")
        print("\nMelhores Parâmetros Encontrados:")
        for key, value in study.best_params.items():
            print(f"  - {key}: {value}")
    else:
        print("Nenhum trial foi concluído com sucesso.")
    print("="*50)

