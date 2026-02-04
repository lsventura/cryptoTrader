import time
import yaml
import os
import json
from datetime import datetime
from pathlib import Path
from src.tools.execution import execute_trade_v2, close_position, list_monitors, start_position_monitor, stop_monitor, get_position_info, monitor_status
from src.tools.market import get_market_data
from src.agents.strategy import sentiment_agent
from src.agents.optimizer import tuner_agent
from src.agents.super_strategy import Strategy

LOG = lambda m: print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")

MONITORS_FILE = str(Path(__file__).resolve().parents[1] / 'logs' / 'monitors.json')
CYCLES_LOG_FILE = str(Path(__file__).resolve().parents[1] / 'logs' / 'cycles.jsonl')


def reload_config():
    cfg_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(cfg_path, 'r') as f:
        return yaml.safe_load(f)


def log_cycle(cycle_num, sentiment, decision, current_pos, current_price, cfg, pnl_data=None):
    """Registra informações do ciclo em JSON Lines para análise posterior"""
    try:
        cycle_data = {
            'timestamp': datetime.now().isoformat(),
            'cycle': cycle_num,
            'sentiment': sentiment,
            'decision': decision,
            'price': float(current_price) if current_price else None,
            'has_position': bool(current_pos),
        }
        
        # Adiciona dados de P&L se houver posição
        if pnl_data:
            cycle_data['pnl'] = {
                'usdt': float(pnl_data.get('pnl_usdt', 0)),
                'pct': float(pnl_data.get('pnl_pct', 0)),
                'side': pnl_data.get('side'),
                'entry_price': float(pnl_data.get('entry_price', 0)),
                'contracts': float(pnl_data.get('contracts', 0))
            }
        
        # Adiciona parâmetros da estratégia
        strategy_params = cfg.get('strategy', {})
        cycle_data['strategy_params'] = {
            'rsi_buy': strategy_params.get('rsi_buy'),
            'rsi_sell': strategy_params.get('rsi_sell'),
            'ema_filter': strategy_params.get('ema_filter')
        }
        
        # Persiste em JSONL (uma linha por ciclo)
        Path(CYCLES_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(CYCLES_LOG_FILE, 'a') as f:
            f.write(json.dumps(cycle_data, default=str) + '\n')
    except Exception as e:
        LOG(f"⚠️ Erro ao registrar ciclo no log: {e}")


def main_loop():
    cfg = reload_config()
    cycle = 0
    active_monitors = {}
    strategy_engine = Strategy(cfg)  # Instancia a estratégia avançada UMA VEZ

    LOG('BOT V2 iniciado com Strategy Engine (Super Strategy)')

    # Re-hidratar monitores salvos (se houver)
    try:
        if os.path.exists(MONITORS_FILE):
            with open(MONITORS_FILE, 'r') as f:
                saved = json.load(f)
            updated_saved = {}
            removed = []
            for mid, meta in saved.items():
                try:
                    sym = meta.get('symbol')
                    entry_price = float(meta.get('entry_price', meta.get('entryPrice', 0)))
                    amount = float(meta.get('amount', meta.get('qty', 0)))
                    side = meta.get('side', 'buy')
                    # Verifica se posição ainda existe na exchange antes de re-hidratar
                    pos = get_position_info(sym, cfg)
                    if not pos:
                        LOG(f'Monitor {mid} descartado: posição não encontrada na exchange')
                        removed.append(mid)
                        continue
                    # se posição existe, re-hidrata monitor
                    if sym and entry_price and amount:
                        nid, thread = start_position_monitor(sym, entry_price, amount, side, cfg,
                                                             stop_loss_pct=cfg.get('risk_management', {}).get('stop_loss_pct', 0.02),
                                                             trailing_activation=cfg.get('risk_management', {}).get('trailing_activation_pct', 0.005),
                                                             callback_rate=cfg.get('risk_management', {}).get('trailing_callback_rate', 1.0),
                                                             monitor_id=mid, extra_meta=meta)
                        active_monitors[nid] = meta
                        updated_saved[nid] = meta
                        LOG(f'Re-hidratado monitor {nid} para {sym}')
                except Exception as e:
                    LOG(f'Erro ao re-hidratar monitor {mid}: {e}')

            # Persiste apenas monitores válidos (remove órfãos)
            try:
                with open(MONITORS_FILE, 'w') as f:
                    json.dump(updated_saved, f, default=str)
                if removed:
                    LOG(f'Removidos monitores órfãos do arquivo: {removed}')
            except Exception as e:
                LOG(f'Erro ao atualizar arquivo de monitores: {e}')
    except Exception as e:
        LOG(f'Erro lendo arquivo de monitores: {e}')

    while True:
        try:
            cycle += 1
            LOG(f'Cycle {cycle}')

            # 1. Obter dados de mercado
            candles = get_market_data(cfg)
            
            # 2. Auto-otimização (AI Tuner) - roda no primeiro ciclo e a cada 60 ciclos
            if cycle == 1 or cycle % 60 == 0:
                LOG('🤖 AI Tuner: Verificando calibração (foco em candles recentes)...')
                try:
                    tuner_agent({'candles': candles}, os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml'))
                    cfg = reload_config()  # Recarrega config com novos parâmetros
                    strategy_engine = Strategy(cfg)  # RE-INSTANCIA estratégia com novos parâmetros
                    params = cfg.get('strategy', {})
                    LOG(f"⚙️  Parâmetros Otimizados (RECENTE): RSI<{params.get('rsi_buy')} / EMA{params.get('ema_filter')}")
                except Exception as e:
                    LOG(f'❌ Erro no Tuner: {e}')
            
            # 3. Análise de Sentimento (LLM)
            state = {'candles': candles}
            s = sentiment_agent(state, cfg)
            LOG(f"📊 Sentimento (IA): {s['sentiment']}")
            
            # 4. Obter posição atual (se houver)
            symbol = cfg['trading']['symbol']
            current_pos = get_position_info(symbol, cfg)
            LOG(f"💼 Posição Atual: {current_pos if current_pos else 'Nenhuma'}")

            # 5. Obter decisão da ESTRATÉGIA AVANÇADA (Technical + AI + Position Management)
            decision = strategy_engine.combine_signals(
                df=candles, 
                ai_sentiment=s['sentiment'], 
                current_position=current_pos
            )
            LOG(f"🧠 Decisão Estratégica Final: {decision}")

            # 3. Check existing positions via monitors
            monitors = list_monitors()
            has_position = len(monitors) > 0

            # Painel de status: preço atual + monitores
            current_price = candles['close'].iloc[-1]
            LOG(f"Preço atual {cfg['trading']['symbol']}: ${current_price:,.2f}")

            # Exibir P&L se houver posição aberta
            if current_pos:
                try:
                    pos_side = str(current_pos.get('side', '')).lower()
                    entry_price = float(current_pos.get('entryPrice', 0))
                    contracts = float(current_pos.get('contracts', 0))
                    
                    if entry_price > 0 and contracts > 0:
                        # Calcula P&L
                        if pos_side == 'long':
                            pnl_usdt = (current_price - entry_price) * contracts
                            pnl_pct = ((current_price - entry_price) / entry_price) * 100
                        else:  # short
                            pnl_usdt = (entry_price - current_price) * contracts
                            pnl_pct = ((entry_price - current_price) / entry_price) * 100
                        
                        # Emoji de status
                        emoji = '📈' if pnl_usdt >= 0 else '📉'
                        status = 'LUCRO' if pnl_usdt >= 0 else 'PREJUÍZO'
                        
                        LOG(f"{emoji} P&L: {status} | ${pnl_usdt:+.2f} ({pnl_pct:+.2f}%) | Entry: ${entry_price:,.2f} | Atual: ${current_price:,.2f}")
                except Exception as e:
                    LOG(f"⚠️ Erro ao calcular P&L: {e}")

            # Para cada monitor salvo/existente, coletar status
            for mid, meta in monitors.items():
                try:
                    mstat = monitor_status(mid)
                    pinfo = get_position_info(meta.get('symbol'), cfg)
                    running = 'Running' if mstat.get('running') else 'Stopped'
                    pos_text = 'No position'
                    if pinfo:
                        pos_side = pinfo.get('side')
                        pos_amt = pinfo.get('contracts')
                        entry_p = pinfo.get('entryPrice')
                        pos_text = f"{pos_side} {pos_amt} @ {entry_p}"

                    stop_active = 'native' if meta.get('stop_order_created') else ('local' if not meta.get('stop_order_created') else 'none')
                    trailing_trigger = 'activated' if meta.get('activated_trailing') else 'waiting'

                    LOG(f"Monitor {mid}: {meta.get('symbol')} | {running} | Position: {pos_text} | Stop: {stop_active} | Trailing: {trailing_trigger}")
                except Exception as e:
                    LOG(f'Erro ao coletar status do monitor {mid}: {e}')

            if decision == 'HOLD' or decision == 'NEUTRAL' or decision == 'WAIT':
                LOG('⏸️ Mantendo posição ou aguardando confluência...')
                
            elif decision == 'FLIP_TO_SHORT':
                LOG('🔄 FLIP: Revertendo para SHORT')
                if has_position:
                    for mid in list(monitors.keys()):
                        stop_monitor(mid)
                        LOG(f'Monitor {mid} parado para flip')
                    res_close = close_position(cfg)
                    LOG(f'Long fechado: {res_close}')
                
                res = execute_trade_v2({'final_decision': 'SELL'}, cfg)
                LOG(f'Short aberto: {res}')
                mid = res.get('monitor_id')
                if mid:
                    active_monitors[mid] = res
                    
            elif decision == 'FLIP_TO_LONG':
                LOG('🔄 FLIP: Revertendo para LONG')
                if has_position:
                    for mid in list(monitors.keys()):
                        stop_monitor(mid)
                        LOG(f'Monitor {mid} parado para flip')
                    res_close = close_position(cfg)
                    LOG(f'Short fechado: {res_close}')
                
                res = execute_trade_v2({'final_decision': 'BUY'}, cfg)
                LOG(f'Long aberto: {res}')
                mid = res.get('monitor_id')
                if mid:
                    active_monitors[mid] = res
                    
            elif decision == 'UPDATE_STOP_LOSS':
                LOG('📌 Apertando o Stop Loss (Trailing ativo)')
                # Ordem de update já é tratada pelo monitor local em execution.py
                
            elif decision in ['BUY', 'SELL']:
                if has_position and decision != 'NEUTRAL':
                    LOG(f'⚠️ Já tem posição. Ignorando sinal {decision} por segurança.')
                else:
                    LOG(f'⚡ Abrindo nova posição: {decision}')
                    res = execute_trade_v2({'final_decision': decision}, cfg)
                    LOG(f'Ordem executada: {res}')
                    mid = res.get('monitor_id')
                    if mid:
                        active_monitors[mid] = res
            else:
                LOG(f'❓ Decisão desconhecida: {decision}')

            # Registra o ciclo no log para análise posterior
            pnl_info = None
            if current_pos:
                try:
                    pos_side = str(current_pos.get('side', '')).lower()
                    entry_price = float(current_pos.get('entryPrice', 0))
                    contracts = float(current_pos.get('contracts', 0))
                    
                    if entry_price > 0 and contracts > 0:
                        if pos_side == 'long':
                            pnl_usdt = (current_price - entry_price) * contracts
                            pnl_pct = ((current_price - entry_price) / entry_price) * 100
                        else:
                            pnl_usdt = (entry_price - current_price) * contracts
                            pnl_pct = ((entry_price - current_price) / entry_price) * 100
                        
                        pnl_info = {
                            'side': pos_side,
                            'entry_price': entry_price,
                            'contracts': contracts,
                            'pnl_usdt': pnl_usdt,
                            'pnl_pct': pnl_pct
                        }
                except Exception:
                    pass
            
            log_cycle(cycle, s['sentiment'], decision, current_pos, current_price, cfg, pnl_info)

            time.sleep(int(cfg['trading'].get('sleep_seconds', 60)))

        except KeyboardInterrupt:
            LOG('Bot parado pelo usuário')
            break
        except Exception as e:
            LOG(f'Erro no loop: {e}')
            time.sleep(5)


if __name__ == '__main__':
    main_loop()
