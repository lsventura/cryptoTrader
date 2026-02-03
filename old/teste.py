import pandas as pd
import os
import time
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv

# Carregar as variáveis de ambiente
load_dotenv()

# Configurar a API
api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")
cliente_binance = Client(api_key, secret_key, testnet=True)

# Configurações iniciais
codigo_operado = "SOLBRL"
ativo_operado = "SOL"
periodo_candle = Client.KLINE_INTERVAL_1MINUTE
quantidade = 0.015

# Função para obter dados históricos
def pegar_dados(codigo, intervalo):
    candles = cliente_binance.get_klines(symbol=codigo, interval=intervalo, limit=1000)
    precos = pd.DataFrame(candles)
    precos.columns = [
        "tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume",
        "tempo_fechamento", "moedas_negociadas", "numero_trades",
        "volume_ativo_base_compra", "volume_ativo_cotacao", "-"
    ]
    precos = precos[["fechamento", "tempo_fechamento"]]
    precos["fechamento"] = precos["fechamento"].astype(float)
    precos["tempo_fechamento"] = pd.to_datetime(precos["tempo_fechamento"], unit="ms")
    return precos

# Estratégias
def estrategia_media_movel(dados):
    dados["media_rapida"] = dados["fechamento"].rolling(window=7).mean()
    dados["media_devagar"] = dados["fechamento"].rolling(window=40).mean()
    
    ultima_media_rapida = dados["media_rapida"].iloc[-1]
    ultima_media_devagar = dados["media_devagar"].iloc[-1]

    if ultima_media_rapida > ultima_media_devagar:
        return "COMPRA"
    elif ultima_media_rapida < ultima_media_devagar:
        return "VENDA"
    return "NEUTRO"

def estrategia_rsi(dados):
    delta = dados["fechamento"].diff()
    ganho = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    perda = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = ganho / perda
    rsi = 100 - (100 / (1 + rs))

    ultimo_rsi = rsi.iloc[-1]

    if ultimo_rsi < 30:
        return "COMPRA"
    elif ultimo_rsi > 70:
        return "VENDA"
    return "NEUTRO"

# Função para executar operações
def executar_estrategia(acao, codigo_ativo, quantidade):
    if acao == "COMPRA":
        cliente_binance.create_order(
            symbol=codigo_ativo,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=quantidade
        )
        print(f"Comprou {quantidade} de {codigo_ativo}")

    elif acao == "VENDA":
        cliente_binance.create_order(
            symbol=codigo_ativo,
            side=SIDE_SELL,
            type=ORDER_TYPE_MARKET,
            quantity=quantidade
        )
        print(f"Vendeu {quantidade} de {codigo_ativo}")

# Loop principal para executar estratégias em tempo real
while True:
    try:
        dados = pegar_dados(codigo_operado, periodo_candle)

        # Aplicar estratégias
        acao_media_movel = estrategia_media_movel(dados)
        acao_rsi = estrategia_rsi(dados)

        # Decisão combinada (você pode ajustar a lógica aqui)
        if acao_media_movel == "COMPRA" or acao_rsi == "COMPRA":
            executar_estrategia("COMPRA", codigo_operado, quantidade)
        elif acao_media_movel == "VENDA" or acao_rsi == "VENDA":
            executar_estrategia("VENDA", codigo_operado, quantidade)

        print(f"Ação: Média Móvel: {acao_media_movel}, RSI: {acao_rsi}")
        time.sleep(60)

    except Exception as e:
        print(f"Erro: {e}")
        time.sleep(60)
