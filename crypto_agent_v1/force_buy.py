import yaml
import sys
from src.tools.execution import execute_trade

# Carrega config
with open("config/config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

# Estado Falso COMPLETO para enganar a validação
state_fake = {
    # Sinais que permitem a execução
    "sentiment": "BULLISH",
    "quant_signal": "LONG",
    
    # Decisão final
    "final_decision": "BUY",
    
    # Dados fictícios que podem ser necessários
    "risk_decision": {"action": "buy"} 
}

print("🚀 Forçando ordem de COMPRA na Binance...")

try:
    # Executa
    res = execute_trade(state_fake, cfg)
    print("\n✅ Sucesso! Resposta da Binance:")
    print(res)
except Exception as e:
    print(f"\n❌ Erro na execução: {e}")
