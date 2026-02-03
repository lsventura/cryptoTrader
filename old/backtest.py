

import pandas as pd
import numpy as np
from binance.client import Client
from ta.trend import EMAIndicator, SMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator
from ta.trend import ADXIndicator
from ta.trend import PSARIndicator
from datetime import datetime
import os
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore")
# Carregar as variáveis de ambiente
load_dotenv()

# Configurar a API
API_KEY = os.getenv("KEY_BINANCE")
API_SECRET = os.getenv("SECRET_BINANCE")
client = Client(API_KEY, API_SECRET)

# Função para buscar dados históricos
def fetch_data(symbol, interval, start_date, end_date):
    start_timestamp = int(pd.Timestamp(start_date).timestamp() * 1000)
    end_timestamp = int(pd.Timestamp(end_date).timestamp() * 1000)
    klines = client.get_klines(symbol=symbol, interval=interval, startTime=start_timestamp, endTime=end_timestamp)
    df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df

# Função para calcular indicadores
def calculate_indicators(df):
    df["ema9"] = EMAIndicator(close=df["close"], window=9).ema_indicator()
    df["ema21"] = EMAIndicator(close=df["close"], window=21).ema_indicator()
    df["sma50"] = SMAIndicator(close=df["close"], window=50).sma_indicator()
    df["sma200"] = SMAIndicator(close=df["close"], window=200).sma_indicator()
    macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["momentum"] = df["close"].diff()
    # adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
    # df["adx"] = adx.adx()
    # df["+di"] = adx.adx_pos()
    # df["-di"] = adx.adx_neg()
    psar = PSARIndicator(high=df["high"], low=df["low"], close=df["close"], step=0.02, max_step=0.2)
    df["psar"] = psar.psar()
    df["rsi"] = RSIIndicator(close=df["close"], window=14).rsi()
    bollinger = BollingerBands(close=df["close"], window=20)
    df["bb_high"] = bollinger.bollinger_hband()
    df["bb_low"] = bollinger.bollinger_lband()
    df["obv"] = OnBalanceVolumeIndicator(close=df["close"], volume=df["volume"]).on_balance_volume()
    return df

# Estratégias para backtest
def strategy_ema_crossover(df):
    df["signal"] = 0
    df.loc[(df["ema9"] > df["ema21"]) & (df["ema9"].shift(1) <= df["ema21"].shift(1)), "signal"] = 1
    df.loc[(df["ema9"] < df["ema21"]) & (df["ema9"].shift(1) >= df["ema21"].shift(1)), "signal"] = -1
    return df

def strategy_rsi(df, overbought=70, oversold=30):
    df["signal"] = 0
    df.loc[df["rsi"] > overbought, "signal"] = -1
    df.loc[df["rsi"] < oversold, "signal"] = 1
    return df

def strategy_bollinger_bands(df):
    df["signal"] = 0
    df.loc[df["close"] < df["bb_low"], "signal"] = 1
    df.loc[df["close"] > df["bb_high"], "signal"] = -1
    return df

def strategy_obv(df):
    df["signal"] = 0
    df["obv_diff"] = df["obv"].diff()
    df.loc[df["obv_diff"] > 0, "signal"] = 1
    df.loc[df["obv_diff"] < 0, "signal"] = -1
    return df

def strategy_macd(df):
    df["signal"] = 0
    df.loc[(df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1)), "signal"] = 1
    df.loc[(df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1)), "signal"] = -1
    return df

def strategy_momentum(df):
    df["signal"] = 0
    df.loc[df["momentum"] > 0, "signal"] = 1
    df.loc[df["momentum"] < 0, "signal"] = -1
    return df

def strategy_adx(df):
    df["signal"] = 0
    df.loc[(df["adx"] > 25) & (df["+di"] > df["-di"]), "signal"] = 1
    df.loc[(df["adx"] > 25) & (df["+di"] < df["-di"]), "signal"] = -1
    return df

def strategy_parabolic_sar(df):
    df["signal"] = 0
    df.loc[df["close"] > df["psar"], "signal"] = 1
    df.loc[df["close"] < df["psar"], "signal"] = -1
    return df

# Backtest para uma estratégia com operação comprada e vendida
def backtest(df):
    balance = 100  # Saldo inicial em USD
    position = 0
    buy_price = 0
    sell_price = 0
    operations = []

    for i in range(len(df)):
        current_price = df.iloc[i]["close"]
        signal = df.iloc[i].get("signal", 0)

        if signal == 1:  # Compra
            if position <= 0:  # Fecha posição vendida, se houver
                balance += abs(position) * current_price
                sell_price = current_price
                position = 0
                operations.append({"type": "buy_close", "price": sell_price, "time": df.iloc[i]["timestamp"]})
            if position == 0:  # Abre posição comprada
                position = balance / current_price
                buy_price = current_price
                balance = 0
                operations.append({"type": "buy", "price": buy_price, "time": df.iloc[i]["timestamp"]})

        elif signal == -1:  # Venda
            if position > 0:  # Fecha posição comprada, se houver
                balance += position * current_price
                sell_price = current_price
                position = 0
                operations.append({"type": "sell_close", "price": sell_price, "time": df.iloc[i]["timestamp"]})
            if position == 0:  # Abre posição vendida
                position = -balance / current_price
                sell_price = current_price
                balance = 0
                operations.append({"type": "sell", "price": sell_price, "time": df.iloc[i]["timestamp"]})

    # Lucro final
    if position > 0:
        balance += position * df.iloc[-1]["close"]
    elif position < 0:
        balance += abs(position) * df.iloc[-1]["close"]

    return balance, operations

# Testar múltiplos pares, estratégias e intervalos
def test_multiple_pairs_strategies_intervals(pairs, intervals, strategies, start_date, end_date):
    results = []

    for pair in pairs:
        for interval in intervals:
            # print(f"Testando par: {pair} no intervalo: {interval}")
            data = fetch_data(pair, interval, start_date, end_date)
            data = calculate_indicators(data)

            for strategy_name, strategy_func in strategies.items():
                df = strategy_func(data.copy())
                final_balance, operations = backtest(df)

                results.append({
                    "pair": pair,
                    "interval": interval,
                    "strategy": strategy_name,
                    "final_balance": final_balance,
                    "operations": operations
                })

                print(f"{strategy_name} - Intervalo: {interval} - Saldo final: ${final_balance:.2f}")

    return results

# Função principal
if __name__ == "__main__":
    pairs = ["BTCUSDT", "ETHUSDT", "SHIBUSDT", "SOLUSDT", "MOVEUSDT"]
    intervals = [Client.KLINE_INTERVAL_1MINUTE, Client.KLINE_INTERVAL_15MINUTE, Client.KLINE_INTERVAL_1HOUR]
    start_date = "2024-12-19"
    end_date = "2024-12-20"
    strategies = {
        "EMA Crossover": strategy_ema_crossover,
        "RSI": strategy_rsi,
        "Bollinger Bands": strategy_bollinger_bands,
        "OBV": strategy_obv,
        "MACD": strategy_macd,
        "Momentum": strategy_momentum,
        # "ADX": strategy_adx,
        "Parabolic SAR": strategy_parabolic_sar
    }

    try:
        results = test_multiple_pairs_strategies_intervals(pairs, intervals, strategies, start_date, end_date)
        # Encontrar os 5 melhores resultados
        top_results = sorted(results, key=lambda x: x["final_balance"], reverse=True)[:5]
        print("\nTop 5 melhores resultados:")
        for idx, result in enumerate(top_results, 1):
            first_op_time = result['operations'][0]['time'] if result['operations'] else 'N/A'
            last_op_time = result['operations'][-1]['time'] if result['operations'] else 'N/A'
            print(f"{idx}. Par: {result['pair']}, Intervalo: {result['interval']}, Estratégia: {result['strategy']}, Saldo final: ${result['final_balance']:.2f}, Período: {first_op_time} a {last_op_time}")
    except ValueError as e:
        print(f"Erro: {e}")

