import pandas as pd
import numpy as np
from binance.client import Client
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv
from backtest import *

# Carregar variáveis de ambiente
load_dotenv()

# Configurar a API
API_KEY = os.getenv("KEY_BINANCE_PROD")
API_SECRET = os.getenv("SECRET_BINANCE_PROD")
client = Client(API_KEY, API_SECRET)

# Parâmetros globais
PAIRS = ["BTCUSDT", "ETHUSDT", "SHIBUSDT"]
INTERVALS = [Client.KLINE_INTERVAL_1MINUTE, Client.KLINE_INTERVAL_15MINUTE, Client.KLINE_INTERVAL_1HOUR]
STRATEGIES = {
    "EMA Crossover": strategy_ema_crossover,
    "RSI": strategy_rsi,
    "Bollinger Bands": strategy_bollinger_bands,
    "OBV": strategy_obv,
    "MACD": strategy_macd,
    "Momentum": strategy_momentum,
    # "ADX": strategy_adx,
    "Parabolic SAR": strategy_parabolic_sar
}

# Função para determinar o melhor par e estratégia
def find_best_strategies():
    end_date = datetime.now() + timedelta(days=1)
    start_date = end_date - timedelta(days=3)
    
    results = test_multiple_pairs_strategies_intervals(
        PAIRS, INTERVALS, STRATEGIES, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    )

    best_results = []
    for pair in PAIRS:
        pair_results = [r for r in results if r['pair'] == pair and r['final_balance'] > 1.03]
        if pair_results:
            best_result = max(pair_results, key=lambda x: x["final_balance"])
            best_results.append(best_result)
    return best_results

def adjust_quantity(symbol, quantity):
    """Ajusta a quantidade para atender às restrições de LOT_SIZE."""
    exchange_info = client.get_symbol_info(symbol)
    for filter in exchange_info['filters']:
        if filter['filterType'] == 'LOT_SIZE':
            step_size = float(filter['stepSize'])
            precision = int(round(-np.log10(step_size)))  # Calcula a precisão do step_size
            quantity = round(quantity - (quantity % step_size), precision)
            return quantity
    return quantity

# Função para calcular quantidade com base no valor desejado
def calculate_quantity(symbol, investment):
    """Calcula a quantidade baseada no valor de investimento e ajusta ao stepSize."""
    ticker = client.get_symbol_ticker(symbol=symbol)
    price = float(ticker['price'])
    quantity = investment / price
    return adjust_quantity(symbol, quantity) # Ajustar precisão conforme necessário

# Função para monitorar stop loss e take profit
def monitor_trade(symbol, quantity, entry_price, stop_loss, take_profit):
    while True:
        ticker = client.get_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])

        # Verificar Take Profit
        if current_price >= take_profit:
            print(f"Take Profit atingido: {current_price}. Vendendo...")
            client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )
            break

        # Verificar Stop Loss
        if current_price <= stop_loss:
            print(f"Stop Loss atingido: {current_price}. Vendendo...")
            client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )
            break

        time.sleep(5)  # Aguardar 5 segundos antes de verificar novamente

# Função para operar automaticamente com base na melhor estratégia
def auto_trade():
    active_trades = {}
    investment_amount = 10  # Valor a ser investido em dólares por par

    while True:
        best_results = find_best_strategies()

        for result in best_results:
            pair = result['pair']
            strategy = result['strategy']
            interval = result['interval']

            if pair in active_trades:
                print(f"{pair}: Já monitorando uma operação ativa.")
                continue

            print(f"\nNova estratégia encontrada para {pair}:")
            print(f"Estratégia: {strategy}, Intervalo: {interval}, Saldo final: ${result['final_balance']:.2f}")

            # Dados mais recentes para operações
            recent_data = fetch_data(
                pair,
                interval,
                (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

            recent_data = calculate_indicators(recent_data)
            strategy_function = STRATEGIES[strategy]
            recent_data = strategy_function(recent_data)

            # Obter último sinal
            last_signal = recent_data.iloc[-1].get("signal", 0)

            if last_signal == 1:
                print(f"Sinal de COMPRA identificado para {pair}. Executando ordem de compra...")
                quantity = calculate_quantity(pair, investment_amount)
                entry_price = float(client.get_symbol_ticker(symbol=pair)['price'])

                # Calcular Stop Loss e Take Profit
                stop_loss = entry_price * 0.98  # Exemplo: 2% abaixo do preço de entrada
                take_profit = entry_price * 1.02  # Exemplo: 2% acima do preço de entrada

                # Executar ordem de compra
                client.order_market_buy(
                    symbol=pair,
                    quantity=quantity
                )

                print(f"Compra executada para {pair}. Monitorando Stop Loss ({stop_loss}) e Take Profit ({take_profit})...")
                active_trades[pair] = {
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit
                }

                monitor_trade(pair, quantity, entry_price, stop_loss, take_profit)
                del active_trades[pair]  # Remover da lista de operações ativas após conclusão

            elif last_signal == -1:
                print(f"Sinal de VENDA identificado para {pair}. Executando ordem de venda...")
                quantity = calculate_quantity(pair, investment_amount)
                entry_price = float(client.get_symbol_ticker(symbol=pair)['price'])

                # Calcular Stop Loss e Take Profit para posição vendida
                stop_loss = entry_price * 1.02  # Exemplo: 2% acima do preço de entrada
                take_profit = entry_price * 0.98  # Exemplo: 2% abaixo do preço de entrada

                # Executar ordem de venda
                client.order_market_sell(
                    symbol=pair,
                    quantity=quantity
                )

                print(f"Venda executada para {pair}. Monitorando Stop Loss ({stop_loss}) e Take Profit ({take_profit})...")
                active_trades[pair] = {
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit
                }

                monitor_trade(pair, quantity, entry_price, stop_loss, take_profit)
                del active_trades[pair]  # Remover da lista de operações ativas após conclusão

            else:
                print(f"Nenhum sinal de operação identificado para {pair}.")

        time.sleep(60)  # Aguardar 1 minuto antes de reavaliar

# Iniciar automação
if __name__ == "__main__":
    auto_trade()
