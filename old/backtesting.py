import pandas as pd
import os
from binance.client import Client
from dotenv import load_dotenv
import numpy as np
from sklearn.cluster import KMeans
import talib

# Carregar as variáveis de ambiente
load_dotenv()

# Configurar a API
api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")
cliente_binance = Client(api_key, secret_key, testnet=True)

# Configurações iniciais
moedas = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]  # Lista de moedas para análise
periodos = [Client.KLINE_INTERVAL_1HOUR, Client.KLINE_INTERVAL_4HOUR, Client.KLINE_INTERVAL_1DAY]
capital_inicial = 10000
stop_loss_fixo = 0.02  # Stop Loss inicial de 2%
take_profit_fixo = 0.05  # Take Profit inicial de 5%
n_clusters = 7

# Função para obter dados históricos
def pegar_dados(codigo, intervalo):
    candles = cliente_binance.get_historical_klines(symbol=codigo, interval=intervalo, start_str="1 year ago UTC")
    precos = pd.DataFrame(candles)
    precos.columns = [
        "tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume",
        "tempo_fechamento", "moedas_negociadas", "numero_trades",
        "volume_ativo_base_compra", "volume_ativo_cotacao", "-"]
    precos = precos[["abertura", "maxima", "minima", "fechamento", "volume", "tempo_fechamento"]]
    precos["abertura"] = precos["abertura"].astype(float)
    precos["maxima"] = precos["maxima"].astype(float)
    precos["minima"] = precos["minima"].astype(float)
    precos["fechamento"] = precos["fechamento"].astype(float)
    precos["volume"] = precos["volume"].astype(float)
    precos["tempo_fechamento"] = pd.to_datetime(precos["tempo_fechamento"], unit="ms")
    return precos

# Função para extrair características dos dados
def extrair_caracteristicas(dados):
    dados["variaçao"] = (dados["fechamento"] - dados["abertura"]) / dados["abertura"] * 100
    dados["amplitude"] = (dados["maxima"] - dados["minima"]) / dados["abertura"] * 100
    dados["media_preco"] = (dados["abertura"] + dados["fechamento"] + dados["maxima"] + dados["minima"]) / 4
    dados["volume_normalizado"] = (dados["volume"] - dados["volume"].mean()) / dados["volume"].std()
    return dados

# Função para adicionar indicadores técnicos
def adicionar_indicadores(dados):
    dados["rsi"] = talib.RSI(dados["fechamento"], timeperiod=14)
    dados["ema_12"] = talib.EMA(dados["fechamento"], timeperiod=12)
    dados["ema_26"] = talib.EMA(dados["fechamento"], timeperiod=26)
    dados["macd"], dados["macd_signal"], _ = talib.MACD(dados["fechamento"], fastperiod=12, slowperiod=26, signalperiod=9)
    dados["atr"] = talib.ATR(dados["maxima"], dados["minima"], dados["fechamento"], timeperiod=14)
    return dados

# Função para aplicar K-Means e identificar clusters
def identificar_oportunidades(dados, n_clusters=5):
    features = dados[["variaçao", "amplitude", "volume_normalizado", "media_preco"]]
    features = features.dropna()

    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    clusters = kmeans.fit_predict(features)

    dados["cluster"] = np.nan
    dados.loc[features.index, "cluster"] = clusters

    return dados, kmeans

# Função para analisar clusters
def analisar_clusters(dados):
    cluster_analysis = dados.groupby("cluster").agg({
        "variaçao": ["mean", "std"],
        "amplitude": ["mean", "std"],
        "volume_normalizado": ["mean", "std"],
        "media_preco": ["mean", "std"],
    })

    clusters_lucrativos = dados.groupby("cluster")["variaçao"].mean().nlargest(2).index.tolist()
    print(f"Clusters mais lucrativos: {clusters_lucrativos}")
    print(cluster_analysis)

    return clusters_lucrativos, cluster_analysis

# Função de Backtesting com clusters e gestão de risco
def realizar_backtesting_com_clusters(dados, clusters_lucrativos, capital_inicial=10000):
    capital = capital_inicial
    lucro_total = 0
    drawdown_maximo = 0

    for i in range(len(dados)):
        if dados["cluster"].iloc[i] not in clusters_lucrativos:
            continue  # Ignorar operações fora dos clusters lucrativos

        preco_atual = dados["fechamento"].iloc[i]
        stop_loss_percentual = dados["atr"].iloc[i] / preco_atual if not np.isnan(dados["atr"].iloc[i]) else stop_loss_fixo
        take_profit_percentual = stop_loss_percentual * 2

        # Simples lógica de compra e venda baseada na variação
        if dados["variaçao"].iloc[i] > 0:
            capital -= preco_atual * 0.01  # Comprar 0.01 da moeda
            preco_entrada = preco_atual

        elif dados["variaçao"].iloc[i] < 0:
            lucro_total += (preco_atual - preco_entrada) * 0.01
            capital += preco_atual * 0.01  # Vender 0.01 da moeda

        # Atualizar drawdown
        drawdown = (capital_inicial - capital) / capital_inicial
        drawdown_maximo = max(drawdown_maximo, drawdown)

    return capital, lucro_total, drawdown_maximo

# Aplicação do modelo para múltiplas moedas e períodos
resultados_backtest = []

for moeda in moedas:
    for periodo in periodos:
        dados = pegar_dados(moeda, periodo)
        dados = extrair_caracteristicas(dados)
        dados = adicionar_indicadores(dados)
        dados, kmeans_model = identificar_oportunidades(dados, n_clusters=n_clusters)

        clusters_lucrativos, _ = analisar_clusters(dados)

        capital_final, lucro_total, drawdown_maximo = realizar_backtesting_com_clusters(dados, clusters_lucrativos)
        resultados_backtest.append({
            "moeda": moeda,
            "periodo": periodo,
            "clusters_lucrativos": clusters_lucrativos,
            "capital_final": capital_final,
            "lucro_total": lucro_total,
            "drawdown_maximo": drawdown_maximo,
        })

# Exibir resultados do Backtesting
print("\nResultados do Backtesting:")
for resultado in resultados_backtest:
    print(f"Moeda: {resultado['moeda']}, Período: {resultado['periodo']}")
    print(f"Clusters Lucrativos: {resultado['clusters_lucrativos']}")
    print(f"Capital Final: {resultado['capital_final']:.2f}, Lucro Total: {resultado['lucro_total']:.2f}, Drawdown Máximo: {resultado['drawdown_maximo']:.2%}")
