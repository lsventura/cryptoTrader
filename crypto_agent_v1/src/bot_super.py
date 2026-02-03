import time
import sys
import os
import yaml
import pandas as pd
from datetime import datetime

# Importações internas
# Tenta importar market data com tratamento de erro
try:
    from src.tools.market import get_market_data
except ImportError:
    try:
        from src.tools.market_data import get_market_data
    except ImportError:
        print("❌ Erro: Não foi possível encontrar 'get_market_data'. Verifique a pasta src/tools/.")
        sys.exit(1)

from src.tools.sentiment import analyze_sentiment
from src.tools.execution import execute_trade, fetch_position
from src.strategies.super_strategy import Strategy

# Carrega Config
def load_config():
    try:
        with open("config/config.yaml", 'r') as stream:
            return yaml.safe_load(stream)
    except FileNotFoundError:
        print("❌ Erro: Arquivo config/config.yaml não encontrado.")
        sys.exit(1)

def main():
    print("\n🔥 SUPER BOT INICIADO | MODE: GESTÃO ATIVA & PROTEÇÃO TRIPLA 🔥")
    print("=================================================================\n")
    
    cfg = load_config()
    strategy = Strategy(cfg)
    symbol = cfg['trading']['symbol']
    timeframe = cfg['trading']['timeframe']
    
    print(f"🌍 Mercado: {symbol} [{timeframe}]")
    print(f"🛡️ Risco: Stop Fixo {cfg['risk_management']['initial_stop_loss_pct']*100}% | Trailing Ativa em {cfg['risk_management']['activation_threshold']*100}%")
    print("-----------------------------------------------------------------\n")

    while True:
        try:
            print(f"⏰ {datetime.now().strftime('%H:%M:%S')} - Analisando Mercado...")
            
            # 1. Dados de Mercado
            try:
                df = get_market_data(symbol, timeframe, limit=100)
                current_price = df.iloc[-1]['close']
                print(f"💲 Preço: ${current_price:.2f}")
            except Exception as e:
                print(f"⚠️ Erro ao baixar dados: {e}")
                time.sleep(10)
                continue

            # 2. Sentimento IA
            # (Aqui usamos uma chamada simulada ou real se disponível)
            sentiment = "NEUTRAL"
            try:
                # Se tiver a função real conectada no Phi-3:
                # sentiment_res = analyze_sentiment("Crypto market news")
                # sentiment = sentiment_res if isinstance(sentiment_res, str) else "NEUTRAL"
                pass 
            except: pass
            
            # 3. Posição Atual
            # Pegamos detalhado para saber o lado (long/short)
            from src.tools.execution import _get_exchange
            exchange = _get_exchange(cfg)
            
            my_pos = None
            try:
                # Usa a flag interna para evitar erros de config
                exchange.has['fetchCurrencies'] = False 
                positions = exchange.fetch_positions([symbol])
                for p in positions:
                    if p['symbol'] == symbol and float(p['contracts']) > 0:
                        side = 'long' if float(p['contracts']) > 0 else 'short'
                        # Na Binance USD-M, posições short aparecem como contracts negativo? 
                        # Geralmente 'side': 'long'/'short' é explicito na v2, mas contracts negativo pode acontecer na v1
                        # Vamos confiar no campo 'side' ou no sinal do 'positionAmt'
                        amt = float(p['info'].get('positionAmt', p['contracts']))
                        
                        if amt != 0:
                            my_pos = {
                                'amount': abs(amt),
                                'entryPrice': float(p['entryPrice']),
                                'side': 'long' if amt > 0 else 'short',
                                'pnl': float(p['unrealizedPnl'])
                            }
                            print(f"📊 Posição: {my_pos['side'].upper()} | Entrada: ${my_pos['entryPrice']} | PNL: ${my_pos['pnl']}")
            except Exception as e:
                print(f"⚠️ Erro ao ler posição: {e}")

            if not my_pos:
                print("⚪ Sem posição aberta.")

            # 4. O Cérebro Decide
            decision = strategy.combine_signals(df, sentiment, my_pos)
            
            # 5. Execução (Com Inversão de Mão)
            if decision == "BUY":
                if my_pos and my_pos['side'] == 'short':
                    print("🔄 FLIP: Fechando Short para abrir Long!")
                    # Para inverter, precisamos fechar a anterior primeiro
                    # A maneira mais rápida é mandar ordem de COMPRA com DOBRO da quantidade?
                    # Ou fechar e abrir. Vamos fechar e abrir para garantir limpeza dos stops.
                    
                    # 1. Fecha Short (Compra a qtd que tem)
                    exchange.create_market_order(symbol, 'buy', my_pos['amount'], {'reduceOnly': True})
                    print("✅ Short Fechado.")
                    time.sleep(1)
                    
                    # 2. Abre Long (O execute_trade já bota os novos stops)
                    execute_trade("BUY", cfg)
                    
                elif not my_pos:
                    print("🚀 Sinal de COMPRA! Entrando...")
                    execute_trade("BUY", cfg)
                    
            elif decision == "SELL":
                if my_pos and my_pos['side'] == 'long':
                    print("🔄 FLIP: Fechando Long para abrir Short!")
                    
                    # 1. Fecha Long (Vende a qtd que tem)
                    exchange.create_market_order(symbol, 'sell', my_pos['amount'], {'reduceOnly': True})
                    print("✅ Long Fechado.")
                    time.sleep(1)
                    
                    # 2. Abre Short
                    execute_trade("SELL", cfg)
                    
                elif not my_pos:
                    print("🚀 Sinal de VENDA! Entrando...")
                    execute_trade("SELL", cfg)

            elif decision == "HOLD":
                if my_pos:
                    print("🛡️ Mantendo posição (Stops automáticos já estão cuidando do risco).")
                else:
                    print("⏳ Mercado lateral/neutro. Aguardando oportunidade.")

            # Aguarda próximo ciclo
            print("💤 Dormindo 60s...")
            time.sleep(60)

        except KeyboardInterrupt:
            print("\n🛑 Parando Super Bot...")
            break
        except Exception as e:
            print(f"❌ Erro Crítico no Loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
