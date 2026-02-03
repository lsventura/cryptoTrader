import yaml
from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.tools.market import get_market_data
from src.agents.strategy import sentiment_agent, quant_agent
from src.agents.meta import evaluator_agent, tuner_agent
from src.tools.execution import execute_trade

print("Carregando configurações...")
with open("config/config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

print("Conectando com mercado...")
candles = get_market_data(cfg)
print(f"✅ Dados OK: {len(candles)} candles, preço atual: ${candles['close'].iloc[-1]:.2f}")

print("Executando análise...")
strategy_output = {**sentiment_agent({"candles": candles}, cfg), **quant_agent({"candles": candles})}
print(f"📊 Sentimento: {strategy_output['sentiment']}")
print(f"📊 Quant: {strategy_output['quant_signal']}")

print("Avaliando risco...")
risk_output = execute_trade({"sentiment": strategy_output['sentiment'], "quant_signal": strategy_output['quant_signal']}, cfg)
print(f"⚡ Decisão: {risk_output}")

print("✅ Ciclo completo! Bot funcionando.")
