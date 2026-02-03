from binance.client import Client
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
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

# ================================
# 1. Função para Extrair Dados Históricos
# ================================
def fetch_historical_data(symbol, interval, start_date, end_date=None):
    print(f"Baixando dados históricos para {symbol}...")
    klines = client.get_historical_klines(symbol, interval, start_date, end_date)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df.astype(float)

# Exemplo de uso: Captura dados históricos (últimos 3 anos até o dia de hoje)
historical_data = fetch_historical_data('BTCUSDT', Client.KLINE_INTERVAL_1HOUR, '3 years ago UTC', None)
# print(historical_data.head())

# ================================
# 2. Adicionar Indicadores Técnicos
# ================================
def add_technical_indicators(df):
    df['SMA_50'] = df['close'].rolling(window=50).mean()
    df['SMA_200'] = df['close'].rolling(window=200).mean()
    df['RSI'] = calculate_rsi(df['close'], 14)
    return df.dropna()

def calculate_rsi(series, period):
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

historical_data = add_technical_indicators(historical_data)
# print(historical_data.tail())

# ================================
# 3. Criar o Modelo Não Supervisionado
# ================================
def train_kmeans_model(df, n_clusters):
    features = df[['close', 'SMA_50', 'SMA_200', 'RSI']]
    kmeans = KMeans(n_clusters=n_clusters, random_state=0)
    df['cluster'] = kmeans.fit_predict(features)
    return kmeans, df

kmeans_model, historical_data = train_kmeans_model(historical_data, 3)
# print(historical_data[['close', 'cluster']].tail())

# ================================
# 4. Função de Backtest
# ================================
def backtest_strategy(df, kmeans_model, initial_balance=1000):
    balance = initial_balance
    position = 0  # Quantidade de BTC
    trade_log = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        cluster = kmeans_model.predict([[row['close'], row['SMA_50'], row['SMA_200'], row['RSI']]])[0]
        
        # Estratégia baseada no cluster
        if cluster == 0 and position == 0:  # Compra
            position = balance / row['close']
            balance = 0
            trade_log.append((row.name, 'BUY', row['close'], position))
        elif cluster == 2 and position > 0:  # Venda
            balance = position * row['close']
            position = 0
            trade_log.append((row.name, 'SELL', row['close'], balance))
    
    # Calcula o valor final
    final_value = balance + (position * df.iloc[-1]['close'] if position > 0 else 0)
    return final_value, trade_log

# ================================
# 5. Executar o Backtest
# ================================
final_balance, trades = backtest_strategy(historical_data, kmeans_model)

# ================================
# 6. Mostrar Resultados
# ================================
# Exibir trades realizados
trade_df = pd.DataFrame(trades, columns=['Timestamp', 'Action', 'Price', 'Quantity/Balance'])
print("\nHistórico de Trades:")
# print(trade_df)

# Exibir saldo final
print(f"\nSaldo inicial: $1000")
print(f"Saldo final: ${final_balance:.2f}")

# Plotar clusters
plt.figure(figsize=(12, 6))
plt.scatter(historical_data.index, historical_data['close'], c=historical_data['cluster'], cmap='viridis', label='Clusters')
plt.title('Clusters de Preços - Estratégia')
plt.xlabel('Data')
plt.ylabel('Preço de Fechamento (USD)')
plt.legend()
plt.show()
