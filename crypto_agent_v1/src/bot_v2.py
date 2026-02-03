import time
import yaml
import os
import json
from datetime import datetime
from pathlib import Path
from src.tools.execution import execute_trade_v2, close_position, list_monitors, start_position_monitor, stop_monitor
from src.tools.market import get_market_data
from src.agents.strategy import sentiment_agent, quant_agent
from src.agents.optimizer import tuner_agent

LOG = lambda m: print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")

MONITORS_FILE = str(Path(__file__).resolve().parents[1] / 'logs' / 'monitors.json')


def reload_config():
    cfg_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    with open(cfg_path, 'r') as f:
        return yaml.safe_load(f)


def main_loop():
    cfg = reload_config()
    cycle = 0
    active_monitors = {}

    LOG('BOT V2 iniciado')

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
                    from src.tools.execution import get_position_info
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

            # 1. get data and agents
            candles = get_market_data(cfg)
            # 2. Auto-otimização (AI Tuner) - roda no primeiro ciclo e a cada 60 ciclos
            if cycle == 1 or cycle % 60 == 0:
                LOG('AI Tuner: Verificando calibração da estratégia...')
                try:
                    tuner_agent({'candles': candles}, os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml'))
                    cfg = reload_config()
                    params = cfg.get('strategy', {})
                    LOG(f"⚙️  Parâmetros Ativos: RSI<{params.get('rsi_buy')} / EMA{params.get('ema_filter')}")
                except Exception as e:
                    LOG(f'Erro no Tuner: {e}')
            state = {'candles': candles}
            q = quant_agent(state, cfg)
            s = sentiment_agent(state, cfg)
            LOG(f"Sentiment={s['sentiment']} | Quant={q['quant_signal']}")

            # 2. Decide confluence
            decision = 'WAIT'
            if s['sentiment'] == 'BULLISH' and q['quant_signal'] == 'LONG':
                decision = 'BUY'
            elif s['sentiment'] == 'BEARISH' and q['quant_signal'] == 'SHORT':
                decision = 'SELL'

            # 3. Check existing positions via monitors
            monitors = list_monitors()
            has_position = len(monitors) > 0

            # Painel de status: preço atual + monitores
            current_price = candles['close'].iloc[-1]
            LOG(f"Preço atual {cfg['trading']['symbol']}: ${current_price:,.2f}")

            # Para cada monitor salvo/existente, coletar status
            for mid, meta in monitors.items():
                try:
                    from src.tools.execution import monitor_status, get_position_info
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

            if decision != 'WAIT':
                LOG(f'Decision final: {decision}')
                # If we have opposite position(s), flip
                if has_position:
                    # Simple policy: close all monitored positions before opening opposite
                    LOG('Posição(s) ativa(s) detectada(s). Fechando antes de abrir nova.')
                    for mid in list(monitors.keys()):
                        stop_monitor(mid)
                        LOG(f'Monitor {mid} stopped')
                    # attempt to close at market
                    res_close = close_position(cfg)
                    LOG(f'close_position result: {res_close}')

                # Open new
                res = execute_trade_v2({'final_decision': decision}, cfg)
                LOG(f'execute_trade_v2 returned: {res}')
                # Register monitor if returned id
                mid = res.get('monitor_id')
                if mid:
                    active_monitors[mid] = res

            else:
                LOG('Aguardando confluência...')

            time.sleep(int(cfg['trading'].get('sleep_seconds', 60)))

        except KeyboardInterrupt:
            LOG('Bot parado pelo usuário')
            break
        except Exception as e:
            LOG(f'Erro no loop: {e}')
            time.sleep(5)


if __name__ == '__main__':
    main_loop()
