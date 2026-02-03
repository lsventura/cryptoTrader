import pandas as pd
import os
from binance.client import Client
from dotenv import load_dotenv
from openai import ChatCompletion  # Para integrar o GPT

# Carregar as variáveis de ambiente
load_dotenv()

# Configurar a API
api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")
openai_api_key = os.getenv("OPENAI_API_KEY")
cliente_binance = Client(api_key, secret_key, testnet=True)

# Configurações iniciais
codigo_operado = "SOLBRL"
periodos = [Client.KLINE_INTERVAL_1MINUTE, Client.KLINE_INTERVAL_1HOUR, Client.KLINE_INTERVAL_1DAY]
capital_inicial = 10000  # Capital inicial em BRL
quantidade_padrao = 0.015

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
    
    sinais = []
    for i in range(len(dados)):
        if dados["media_rapida"].iloc[i] > dados["media_devagar"].iloc[i]:
            sinais.append("COMPRA")
        elif dados["media_rapida"].iloc[i] < dados["media_devagar"].iloc[i]:
            sinais.append("VENDA")
        else:
            sinais.append("NEUTRO")
    
    dados["sinal_mm"] = sinais
    return dados

def estrategia_rsi(dados):
    delta = dados["fechamento"].diff()
    ganho = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    perda = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = ganho / perda
    rsi = 100 - (100 / (1 + rs))

    sinais = []
    for i in range(len(rsi)):
        if rsi.iloc[i] < 30:
            sinais.append("COMPRA")
        elif rsi.iloc[i] > 70:
            sinais.append("VENDA")
        else:
            sinais.append("NEUTRO")
    
    dados["rsi"] = rsi
    dados["sinal_rsi"] = sinais
    return dados

def estrategia_bollinger(dados):
    media = dados["fechamento"].rolling(window=20).mean()
    desvio = dados["fechamento"].rolling(window=20).std()
    upper_band = media + (2 * desvio)
    lower_band = media - (2 * desvio)

    sinais = []
    for i in range(len(dados)):
        if dados["fechamento"].iloc[i] < lower_band.iloc[i]:
            sinais.append("COMPRA")
        elif dados["fechamento"].iloc[i] > upper_band.iloc[i]:
            sinais.append("VENDA")
        else:
            sinais.append("NEUTRO")
    
    dados["sinal_bollinger"] = sinais
    return dados

def estrategia_macd(dados):
    ema12 = dados["fechamento"].ewm(span=12, adjust=False).mean()
    ema26 = dados["fechamento"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    sinais = []
    for i in range(len(dados)):
        if macd.iloc[i] > signal.iloc[i]:
            sinais.append("COMPRA")
        elif macd.iloc[i] < signal.iloc[i]:
            sinais.append("VENDA")
        else:
            sinais.append("NEUTRO")
    
    dados["sinal_macd"] = sinais
    return dados

# Função para integrar com o GPT
def analisar_com_gpt(dados):
    prompt = (
        "Você é um analista financeiro. Analise a massa de dados a seguir e recomende a melhor estratégia de trading: \n"
        + dados.tail(50).to_string(index=False) +
        "\nConsiderando as estratégias disponíveis: Média Móvel, RSI, Bandas de Bollinger, MACD."
    )
    response = ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Você é um assistente especializado em trading."},
            {"role": "user", "content": prompt}
        ]
    )
    return response['choices'][0]['message']['content']

# Função para backtesting
def realizar_backtesting(dados, capital_inicial, quantidade_padrao, estrategia):
    capital = capital_inicial
    posicao = 0
    lucro_por_estrategia = {estr: 0 for estr in estrategia}

    for i in range(len(dados)):
        sinais = [dados[col].iloc[i] for col in estrategia]
        preco_atual = dados["fechamento"].iloc[i]

        if "COMPRA" in sinais and posicao == 0:
            posicao = quantidade_padrao
            capital -= posicao * preco_atual

        elif "VENDA" in sinais and posicao > 0:
            capital += posicao * preco_atual
            posicao = 0

        # Registrar lucro parcial
        for estr in estrategia:
            if dados[estr].iloc[i] == "COMPRA" and posicao == 0:
                lucro_por_estrategia[estr] -= quantidade_padrao * preco_atual
            elif dados[estr].iloc[i] == "VENDA" and posicao > 0:
                lucro_por_estrategia[estr] += quantidade_padrao * preco_atual

    # Valor final (considerando posição ainda aberta)
    valor_final = capital + (posicao * dados["fechamento"].iloc[-1])

    return valor_final, lucro_por_estrategia

# Obter dados históricos para diferentes intervalos
dados_geral = pd.DataFrame()
for periodo in periodos:
    dados = pegar_dados(codigo_operado, periodo)
    dados = estrategia_media_movel(dados)
    dados = estrategia_rsi(dados)
    dados = estrategia_bollinger(dados)
    dados = estrategia_macd(dados)
    dados["periodo"] = periodo
    dados_geral = pd.concat([dados_geral, dados])

# Estratégias para avaliar
estrategias = ["sinal_mm", "sinal_rsi", "sinal_bollinger", "sinal_macd"]

# Realizar o backtesting
valor_final, lucro_por_estrategia = realizar_backtesting(dados_geral, capital_inicial, quantidade_padrao, estrategias)
lucro = valor_final - capital_inicial

# Analisar dados com GPT
recomendacao_gpt = analisar_com_gpt(dados_geral)

print(f"Capital inicial: BRL {capital_inicial:.2f}")
print(f"Valor final: BRL {valor_final:.2f}")
print(f"Lucro total: BRL {lucro:.2f}")
print("Lucro por estratégia:")
for estr, lucro_estr in lucro_por_estrategia.items():
    print(f" - {estr}: BRL {lucro_estr:.2f}")
print(f"Períodos testados: {', '.join(periodos)}")
print("\nRecomendação do GPT:")
print(recomendacao_gpt)
