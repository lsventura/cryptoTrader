import os
import warnings
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from binance.client import Client
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from ta import add_all_ta_features
from ta.utils import dropna

# Configurações iniciais
warnings.filterwarnings("ignore")
load_dotenv()

# Configurar a API
API_KEY = os.getenv("KEY_BINANCE")
API_SECRET = os.getenv("SECRET_BINANCE")
client = Client(API_KEY, API_SECRET)

end_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
start_date = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d %H:%M:%S')
today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')



# Função para extrair dados históricos
def fetch_historical_data(symbol, interval, start_date, end_date=None):
    print(f"Baixando dados históricos para {symbol} de {start_date} até {end_date}...")
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


def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# Função para adicionar indicadores técnicos
def add_technical_indicators(df):

    df["AVG_FAST"] = df["close"].rolling(window = 7).mean()
    df["AVG_LOW"] = df["close"].rolling(window = 40).mean()
    df['SMA_20'] = df['close'].rolling(window=20).mean()
    df['EMA_12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['RSI'] = calculate_rsi(df['close'], window=14)
    df['TR'] = df[['high', 'low', 'close']].apply(lambda x: max(x['high'] - x['low'], abs(x['high'] - x['close']), abs(x['low'] - x['close'])), axis=1)
    df['ATR'] = df['TR'].rolling(14).mean()


    # Remover valores nulos
    return df.dropna()


# Obter dados de hoje para teste
today_data = fetch_historical_data('BTCUSDT', Client.KLINE_INTERVAL_1MINUTE, today_start, end_date)
today_data = add_technical_indicators(today_data)






def estrategia_trade(df, initial_balance=1000.0):
    balance = initial_balance
    position = 0  # Quantidade de BTC
    trade_log = []

    ultima_media_rapida = df["avg_fast"].iloc[-1]
    ultima_media_devagar = df["avg_low"].iloc[-1]
    vl_fechamento = df["close"].iloc[-1]
    dt = df.index[-1]

    print(f"Última Média Rápida: {ultima_media_rapida} | Última Média Devagar: {ultima_media_devagar}")

    if ultima_media_rapida > ultima_media_devagar:

        if posicao == False:

            position = balance / vl_fechamento
            balance = 0
            trade_log.append((dt, 'BUY', vl_fechamento, position))
            
            
            print("COMPROU O ATIVO")

            posicao = True

    elif ultima_media_rapida < ultima_media_devagar:

        if posicao == True:

            balance = position * vl_fechamento
            position = 0
            trade_log.append((dt, 'SELL', vl_fechamento, balance))
            print("VENDER O ATIVO")

            posicao = False

    return posicao

# Função para testar a estratégia com dados de hoje
def test_today(df, initial_balance=1000):
    balance = initial_balance
    posicao = False
    trade_log = []

    for i in range(len(df)):
        row = df.iloc[i]
        
        ultima_media_rapida = row["AVG_FAST"]
        ultima_media_devagar = row["AVG_LOW"]

        # Condições de Compra
        if  ultima_media_rapida > ultima_media_devagar:
            if posicao == False:
                position = balance / row['close']
                balance = 0
                trade_log.append((row.name, 'BUY', row['close'], position))
                posicao = True
        
        # Condições de Venda
        elif  ultima_media_rapida < ultima_media_devagar:
            if posicao == True:
                balance = position * row['close']
                position = 0
                trade_log.append((row.name, 'SELL', row['close'], balance))
                posicao = False

    # Saldo final
    final_balance = balance + (posicao * df.iloc[-1]['close'] if posicao == True else 0)
    return final_balance, trade_log





# Função para treinar o modelo KMeans
def train_kmeans_model(df, n_clusters, use_pca=False, n_components=3):
    # Seleção de features
    features = df[['close', 'BB_upper', 'BB_lower', 'ATR', 'EMA_12', 'EMA_26', 'Stochastic_%K', 'Stochastic_%D']]
    
    # Normalização dos dados
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)
    
    # Aplicar PCA (opcional)
    if use_pca:
        pca = PCA(n_components=n_components)
        features_scaled = pca.fit_transform(features_scaled)
        print(f"Variância explicada pelos {n_components} componentes principais: {pca.explained_variance_ratio_}")
    
    # Treinamento do K-Means
    kmeans = KMeans(n_clusters=n_clusters, random_state=0)
    df['cluster'] = kmeans.fit_predict(features_scaled)
    return kmeans, scaler, df

# Função para testar a estratégia com dados de hoje
def test_today(df, kmeans_model, scaler, initial_balance=1000):
    balance = initial_balance
    position = 0  # Quantidade de BTC
    trade_log = []

    for i in range(len(df)):
        row = df.iloc[i]
        
        # Seleção de features
        features = np.array([[
            row['close'], row['BB_upper'], row['BB_lower'], row['ATR'],
            row['EMA_12'], row['EMA_26'], row['Stochastic_%K'], row['Stochastic_%D']
        ]])
        
        # Normalização
        features_scaled = scaler.transform(features)
        
        # Predizer o cluster atual
        cluster = kmeans_model.predict(features_scaled)[0]
        
        # Condições de Compra
        if (cluster == 0 and row['close'] <= row['BB_lower'] and row['Stochastic_%K'] < 20) and position == 0:
            position = balance / row['close']
            balance = 0
            trade_log.append((row.name, 'BUY', row['close'], position))
        
        # Condições de Venda
        elif (cluster == 2 and row['close'] >= row['BB_upper'] and row['Stochastic_%K'] > 80) and position > 0:
            balance = position * row['close']
            position = 0
            trade_log.append((row.name, 'SELL', row['close'], balance))

    # Saldo final
    final_balance = balance + (position * df.iloc[-1]['close'] if position > 0 else 0)
    return final_balance, trade_log

# Definir datas para o histórico e para hoje
end_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
start_date = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d %H:%M:%S')
today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')

# Obter dados históricos para treinamento
historical_data = fetch_historical_data('BTCUSDT', Client.KLINE_INTERVAL_1MINUTE, start_date, today_start)
historical_data = add_technical_indicators(historical_data)

# Treinar o modelo KMeans
kmeans_model, scaler, historical_data = train_kmeans_model(historical_data, n_clusters=3)

# Obter dados de hoje para teste
today_data = fetch_historical_data('BTCUSDT', Client.KLINE_INTERVAL_1MINUTE, today_start, end_date)
today_data = add_technical_indicators(today_data)

# Testar a estratégia com os dados de hoje
final_balance, trades = test_today(today_data, kmeans_model, scaler)

# Mostrar resultados
trade_df = pd.DataFrame(trades, columns=['Timestamp', 'Action', 'Price', 'Quantity/Balance'])
print("\nHistórico de Trades:")
print(trade_df)

print(f"\nSaldo inicial: $1000")
print(f"Saldo final: ${final_balance:.2f}")

# Visualizar os indicadores e trades
plt.figure(figsize=(14, 7))
plt.plot(today_data['close'], label='Preço de Fechamento', alpha=0.6)
plt.plot(today_data['BB_upper'], label='Bollinger Upper', linestyle='--', alpha=0.6)
plt.plot(today_data['BB_lower'], label='Bollinger Lower', linestyle='--', alpha=0.6)

# Mapear os trades para plotar
buy_points = trade_df[trade_df['Action'] == 'BUY']
sell_points = trade_df[trade_df['Action'] == 'SELL']

plt.scatter(buy_points['Timestamp'], buy_points['Price'], marker='^', color='green', label='Compra', s=100)
plt.scatter(sell_points['Timestamp'], sell_points['Price'], marker='v', color='red', label='Venda', s=100)

plt.title('Backtest - Apenas Hoje')
plt.xlabel('Data')
plt.ylabel('Preço (USD)')
plt.legend()
plt.show()

