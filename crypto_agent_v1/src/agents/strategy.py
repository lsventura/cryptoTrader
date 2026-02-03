import pandas_ta as ta
from langchain_ollama import OllamaLLM

def sentiment_agent(state, cfg):
    try:
        llm = OllamaLLM(base_url=cfg['ai']['ollama_url'], model=cfg['ai']['model'])
        prices = state['candles']['close'].tail(10).tolist()
        
        # Prompt mais rigoroso e direto
        prompt = (
            f"Dados de preço Bitcoin recentes: {prices}.\n"
            "Tarefa: Classifique a tendência imediata.\n"
            "Regra: Responda APENAS com uma das três palavras: BULLISH, BEARISH, NEUTRAL.\n"
            "Não explique. Não use pontuação. Apenas a palavra."
        )
        
        res = llm.invoke(prompt).strip().upper()
        
        # Filtro de Segurança (Sanity Check)
        valid_responses = ["BULLISH", "BEARISH", "NEUTRAL"]
        
        # Se a resposta contiver a palavra chave, aceita. Senão, NEUTRAL.
        sentiment = "NEUTRAL"
        for v in valid_responses:
            if v in res:
                sentiment = v
                break
                
        return {"sentiment": sentiment}
        
    except Exception as e:
        print(f"Erro no LLM: {e}")
        return {"sentiment": "NEUTRAL"}


def quant_agent(state, cfg): # Adicione cfg aqui
    df = state['candles']
    
    # Pega parâmetros do config (ou usa padrão se não tiver)
    params = cfg.get('strategy', {"rsi_buy": 60, "rsi_sell": 70, "ema_filter": 50})
    
    rsi_buy = params['rsi_buy']
    rsi_sell = params['rsi_sell']
    ema_len = params['ema_filter']

    # Calcula com os parâmetros da IA
    rsi = ta.rsi(df['close'], length=14)
    ema_trend = ta.ema(df['close'], length=ema_len) # Dinâmico!
    
    last_rsi = rsi.iloc[-1]
    last_close = df['close'].iloc[-1]
    last_ema = ema_trend.iloc[-1]
    
    signal = "NEUTRAL"
    
    # Usa variáveis dinâmicas
    if last_rsi < rsi_buy and last_close > last_ema:
        signal = "LONG"
    elif last_rsi > rsi_sell and last_close < last_ema:
        signal = "SHORT"
        
    return {"quant_signal": signal}
