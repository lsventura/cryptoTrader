import time
import yaml
import sys
from datetime import datetime

# Importações dos seus módulos
from src.tools.market import get_market_data
from src.agents.strategy import sentiment_agent, quant_agent
from src.agents.optimizer import tuner_agent
from src.tools.execution import execute_trade, check_exit 

# Configuração de logs
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def reload_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

# Carrega config inicial
cfg = reload_config()
SYMBOL = cfg['trading']['symbol']
TIMEFRAME = cfg['trading']['timeframe']

print(f"\n🚀 ROBÔ INICIADO | {SYMBOL} {TIMEFRAME} | AI MODE: ON")
print(f"{'='*65}")

ciclo = 0

while True:
    try:
        ciclo += 1
        print(f"\n🔄 CICLO #{ciclo}")

        # 0. GESTÃO DE POSIÇÃO (TP/SL)
        # -----------------------------------------------------------
        # Verifica se precisa fechar lucro ou prejuízo antes de qualquer coisa
        res_exit = check_exit(cfg)
        if res_exit == "CLOSED_TP":
            log("💰 TAKE PROFIT EXECUTADO! Lucro garantido.")
        elif res_exit == "CLOSED_SL":
            log("🛑 STOP LOSS EXECUTADO. Proteção acionada.")
        elif res_exit == "HOLD":
            # Se tem posição aberta e não bateu alvo, avisa
            # (Opcional: printar "Posição aberta mantida")
            pass

        # 1. OBTER DADOS
        # -----------------------------------------------------------
        log("Baixando dados de mercado...")
        candles = get_market_data(cfg)
        current_price = candles['close'].iloc[-1]
        log(f"Preço Atual: ${current_price:,.2f}")

        # 2. AUTO-OTIMIZAÇÃO (AI TUNER)
        # -----------------------------------------------------------
        # Roda a cada 60 min ou no primeiro ciclo
        if ciclo == 1 or ciclo % 60 == 0:
            log("🤖 AI Tuner: Verificando calibração da estratégia...")
            tuner_agent({"candles": candles}, "config/config.yaml")
            cfg = reload_config() # Atualiza variáveis
            params = cfg.get('strategy', {})
            log(f"⚙️  Parâmetros Ativos: RSI<{params.get('rsi_buy')} / EMA{params.get('ema_filter')}")

        # 3. ANÁLISE (SENTIMENTO + QUANT)
        # -----------------------------------------------------------
        state = {"candles": candles}
        
        # Agentes
        q_res = quant_agent(state, cfg) 
        s_res = sentiment_agent(state, cfg)
        
        sinais = {**q_res, **s_res}
        log(f"🧠 Análise: Sentimento={sinais['sentiment']} | Quant={sinais['quant_signal']}")

        # 4. EXECUÇÃO DE ENTRADA
        # -----------------------------------------------------------
        state_exec = {**state, **sinais}
        
        # Confluência rigorosa
        decisao_final = "WAIT"
        if sinais['sentiment'] == "BULLISH" and sinais['quant_signal'] == "LONG":
            decisao_final = "BUY"
        elif sinais['sentiment'] == "BEARISH" and sinais['quant_signal'] == "SHORT":
            decisao_final = "SELL"
            
        if decisao_final != "WAIT":
            log(f"⚡ OPORTUNIDADE CONFIRMADA: {decisao_final}")
            
            # Tenta executar a entrada
            # Nota: O execution.py deve tratar se já existe posição para não dobrar a mão se não quiser
            res_exec = execute_trade({**state_exec, "final_decision": decisao_final}, cfg)
            
            if "order_id" in res_exec:
                log(f"📝 Ordem Enviada: {res_exec['status']} @ {res_exec['price']}")
            elif "error" in res_exec:
                log(f"⚠️ Erro na Ordem: {res_exec['error']}")
            else:
                log(f"ℹ️ Execução: {res_exec}")
        else:
            log("⏳ Aguardando confluência de sinais...")

        # 5. ESPERA
        # -----------------------------------------------------------
        time.sleep(60) # 1 minuto

    except KeyboardInterrupt:
        print("\n🛑 Robô parado pelo usuário.")
        sys.exit()
    except Exception as e:
        log(f"❌ ERRO NO LOOP: {e}")
        time.sleep(10) # Espera e tenta de novo
