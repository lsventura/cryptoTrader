import ccxt
import time
import threading
import json
import uuid
from pathlib import Path
from typing import Optional

def _get_exchange(cfg):
    # --- CONFIGURAÇÃO BLINDADA ---
    exchange = ccxt.binanceusdm({
        'apiKey': cfg['exchange']['api_key'],
        'secret': cfg['exchange']['api_secret'],
        'verbose': False, 
        'options': { 'defaultType': 'future', 'adjustForTimeDifference': True }
    })

    if cfg['exchange']['testnet']:
        v1 = 'https://testnet.binancefuture.com/fapi/v1'
        v2 = 'https://testnet.binancefuture.com/fapi/v2'
        
        exchange.urls['api'] = {
            'fapiPublic': v1, 
            'fapiPrivate': v1, 
            'fapiPrivateV2': v2,
            'fapiPrivateV3': v2, # <--- A NOVIDADE: CALA A BOCA DO ERRO V3
            'public': v1, 
            'private': v1, 
            'sapi': v1,
        }
        
        exchange.has['fetchCurrencies'] = False
        exchange.has['fetchDepositAddress'] = False

    return exchange

def execute_trade(signal, cfg):
    exchange = _get_exchange(cfg)
    symbol = cfg['trading']['symbol']
    leverage = cfg['trading'].get('leverage', 1)
    
    try:
        exchange.load_markets()
        
        # 1. Configura Alavancagem
        try:
            exchange.set_leverage(leverage, symbol)
            print(f"⚙️ Alavancagem ajustada para {leverage}x")
        except Exception as e:
            print(f"⚠️ Aviso alavancagem: {e}")

        # 2. Busca Saldo
        # Se fetch_balance falhar na V3, tentamos fetch_balance(params={'type':'future'})
        balance = exchange.fetch_balance()
        free_usdt = balance['USDT']['free']
        
        # 3. Calcula Tamanho (50% da banca para teste)
        percentage = 0.50 
        usable_balance = free_usdt * percentage # type: ignore
        
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        
        quantity_usd = usable_balance * leverage
        amount = quantity_usd / price
        
        print(f"💰 Saldo: ${free_usdt:.2f} | Entrada: ${quantity_usd:.2f}")
        print(f"⚖️ Qtd: {amount:.4f} {symbol}")

        # 4. Valida sinal e notional mínimo antes de enviar ordem
        min_notional = float(cfg['trading'].get('min_notional', 100))

        # Se `signal` for um dicionário, tente extrair a decisão final
        decision = None
        if isinstance(signal, dict):
            for k in ('final_decision', 'decision', 'signal', 'action'):
                if k in signal:
                    decision = signal[k]
                    break
        else:
            decision = signal

        if decision is None:
            msg = "Sinal ausente no payload. Ordem não enviada."
            print(f"⚠️ {msg}")
            return {'error': msg}

        normalized = str(decision).strip().upper()
        if normalized in ('BUY', 'LONG'):
            side = 'buy'
        elif normalized in ('SELL', 'SHORT'):
            side = 'sell'
        else:
            msg = f"Sinal desconhecido: '{decision}'. Ordem não enviada."
            print(f"⚠️ {msg}")
            return {'error': msg}

        notional = amount * price
        if notional < min_notional:
            msg = f"Notional calculado ${notional:.2f} menor que mínimo ${min_notional:.2f}. Ordem abortada."
            print(f"⚠️ {msg}")
            return {'error': msg}

        print(f"🚀 Enviando ordem {side.upper()} | Notional: ${notional:.2f}...")
        try:
            order = exchange.create_market_order(symbol, side, amount)
            print(f"✅ Ordem executada: {order.get('id', 'n/a')}")
            return {
                'order_id': order.get('id'),
                'status': order.get('status'),
                'price': order.get('price', price),
                'notional': notional,
                'raw': order
            }
        except Exception as e:
            msg = f"Erro ao enviar ordem: {e}"
            print(f"❌ {msg}")
            return {'error': msg}
        
    except Exception as e:
        print(f"❌ Erro na execução: {e}")
        return None

def fetch_position(cfg):
    exchange = _get_exchange(cfg)
    symbol = cfg['trading']['symbol']
    try:
        exchange.has['fetchCurrencies'] = False
        positions = exchange.fetch_positions([symbol])
        for pos in positions:
            if pos['symbol'] == symbol:
                return float(pos['contracts']) if pos['contracts'] else 0.0
        return 0.0
    except: return 0.0

def check_exit(cfg): return fetch_position(cfg) != 0


def _normalize_signal(decision) -> Optional[str]:
    if decision is None:
        return None
    text = str(decision).strip().upper()
    if text in ("BUY", "LONG", "COMPRA"):
        return "BUY"
    if text in ("SELL", "SHORT", "VENDA"):
        return "SELL"
    return None


def _cancel_open_orders(exchange, symbol):
    try:
        if hasattr(exchange, 'cancel_all_orders'):
            exchange.cancel_all_orders(symbol)
        else:
            # Fallback: try fetch_orders and cancel individually
            orders = exchange.fetch_open_orders(symbol)
            for o in orders:
                try:
                    exchange.cancel_order(o['id'], symbol)
                except Exception:
                    pass
    except Exception:
        pass


def _calculate_amount(cfg, price):
    """Calcula quantidade baseada em risco configurado (risk_per_trade_pct).
    Se não houver saldo disponível (ou dados insuficientes), retorna None.
    """
    try:
        if price is None or price <= 0:
            print(f"⚠️ Preço inválido para cálculo de amount: {price}")
            return None
        
        ex = _get_exchange(cfg)
        bal = ex.fetch_balance()
        free_usdt = bal.get('USDT', {}).get('free', 0)
        
        if free_usdt <= 0:
            print(f"⚠️ Saldo USDT insuficiente: {free_usdt}")
            return None
            
    except Exception as e:
        print(f"⚠️ Erro ao calcular amount: {e}")
        return None

    try:
        risk_pct = float(cfg.get('trading', {}).get('risk_per_trade_pct', 1.5)) / 100.0
        leverage = float(cfg.get('trading', {}).get('leverage', 1))
        min_notional = float(cfg.get('trading', {}).get('min_notional', 100))
        
        # Notional to use
        notional = free_usdt * risk_pct * leverage
        if notional < min_notional:
            # Ajusta para o mínimo em vez de abortar
            notional = min_notional

        amount = notional / price
        if amount <= 0:
            print(f"⚠️ Amount calculado é inválido: {amount}")
            return None
        return amount
    except Exception as e:
        print(f"⚠️ Erro ao calcular amount (matemática): {e}")
        return None


# Global monitor registry
_MONITORS = {}
_MONITORS_PATH = Path(__file__).resolve().parents[2] / 'logs' / 'monitors.json'
_MONITORS_PATH.parent.mkdir(parents=True, exist_ok=True)


def _persist_monitors():
    try:
        to_save = {k: v['meta'] for k, v in _MONITORS.items()}
        with open(_MONITORS_PATH, 'w') as f:
            json.dump(to_save, f, default=str)
    except Exception:
        pass


def start_position_monitor(symbol, entry_price, amount, side, cfg, stop_loss_pct=0.02, trailing_activation=0.005, callback_rate=1.0, monitor_id=None, extra_meta=None):
    """Start a persistent non-daemon background monitor that enforces stop and trailing stop locally.
    Returns (monitor_id, thread).
    """
    if monitor_id is None:
        monitor_id = str(uuid.uuid4())

    stop_event = threading.Event()

    def _monitor_loop():
        try:
            mon_ex = _get_exchange(cfg)
            mon_symbol = symbol
            side_long = (side == 'buy')
            sl_price = entry_price * (1.0 - stop_loss_pct) if side_long else entry_price * (1.0 + stop_loss_pct)
            activated_trailing = False
            highest = entry_price
            lowest = entry_price

            print(f'🕵️ [monitor {monitor_id}] Iniciando monitor local para {mon_symbol} (side={side})')
            while not stop_event.is_set():
                try:
                    t = mon_ex.fetch_ticker(mon_symbol)
                    last = float(t.get('last') or t.get('close') or 0)
                except Exception:
                    time.sleep(1)
                    continue

                if last <= 0:
                    time.sleep(1)
                    continue

                # Atualiza extremos
                if last > highest:
                    highest = last
                if last < lowest:
                    lowest = last

                # Checa Stop Loss
                if side_long and last <= sl_price:
                    print(f"🛑 [monitor {monitor_id}] Stop local atingido @ {last:.2f}. Fechando posição...")
                    try:
                        mon_ex.create_market_order(mon_symbol, 'sell', amount, None, {'reduceOnly': True})
                    except Exception as e:
                        print(f"❌ [monitor {monitor_id}] Erro ao fechar por stop local: {e}")
                    break
                if (not side_long) and last >= sl_price:
                    print(f"🛑 [monitor {monitor_id}] Stop local (short) atingido @ {last:.2f}. Fechando posição...")
                    try:
                        mon_ex.create_market_order(mon_symbol, 'buy', amount, None, {'reduceOnly': True})
                    except Exception as e:
                        print(f"❌ [monitor {monitor_id}] Erro ao fechar por stop local: {e}")
                    break

                # Checa ativação do trailing
                pnl = (last - entry_price) / entry_price if side_long else (entry_price - last) / entry_price
                if (not activated_trailing) and pnl >= trailing_activation:
                    activated_trailing = True
                    # persist status in meta so external process can read it
                    try:
                        if monitor_id in _MONITORS:
                            _MONITORS[monitor_id]['meta']['activated_trailing'] = True
                            _persist_monitors()
                    except Exception:
                        pass
                    if side_long:
                        trailing_stop_price = highest * (1.0 - (callback_rate / 100.0))
                    else:
                        trailing_stop_price = lowest * (1.0 + (callback_rate / 100.0))
                    print(f"🔔 [monitor {monitor_id}] Trailing ativado. Stop inicial @ {trailing_stop_price:.2f}")

                # Atualiza e checa trailing
                if activated_trailing:
                    if side_long:
                        trailing_stop_price = max(trailing_stop_price, highest * (1.0 - (callback_rate / 100.0)))
                        if last <= trailing_stop_price:
                            print(f"🏁 [monitor {monitor_id}] Trailing stop disparado @ {last:.2f}. Fechando posição...")
                            try:
                                mon_ex.create_market_order(mon_symbol, 'sell', amount, None, {'reduceOnly': True})
                            except Exception as e:
                                print(f"❌ [monitor {monitor_id}] Erro ao fechar por trailing local: {e}")
                            break
                    else:
                        trailing_stop_price = min(trailing_stop_price, lowest * (1.0 + (callback_rate / 100.0)))
                        if last >= trailing_stop_price:
                            print(f"🏁 [monitor {monitor_id}] Trailing stop (short) disparado @ {last:.2f}. Fechando posição...")
                            try:
                                mon_ex.create_market_order(mon_symbol, 'buy', amount, None, {'reduceOnly': True})
                            except Exception as e:
                                print(f"❌ [monitor {monitor_id}] Erro ao fechar por trailing local: {e}")
                            break

                time.sleep(1)

        except Exception as e:
            print(f"❌ [monitor {monitor_id}] Monitor falhou: {e}")
        finally:
            # Remove monitor from registry and persist
            _MONITORS.pop(monitor_id, None)
            _persist_monitors()

    th = threading.Thread(target=_monitor_loop, daemon=False)
    meta = {
        'symbol': symbol,
        'entry_price': entry_price,
        'amount': amount,
        'side': side,
        'started_at': time.time(),
        'activated_trailing': False,
        'stop_order_created': False,
        'trailing_order_created': False
    }
    if extra_meta and isinstance(extra_meta, dict):
        meta.update(extra_meta)

    _MONITORS[monitor_id] = {'thread': th, 'stop_event': stop_event, 'meta': meta}
    _persist_monitors()
    th.start()
    return monitor_id, th


def stop_monitor(monitor_id, join_timeout=5):
    item = _MONITORS.get(monitor_id)
    if not item:
        return False
    try:
        item['stop_event'].set()
        item['thread'].join(timeout=join_timeout)
    except Exception:
        pass
    _MONITORS.pop(monitor_id, None)
    _persist_monitors()
    return True


def list_monitors():
    return {k: v['meta'] for k, v in _MONITORS.items()}


def monitor_status(monitor_id):
    """Return runtime status for a monitor: running (bool) and meta (dict)"""
    item = _MONITORS.get(monitor_id)
    if not item:
        return {'running': False, 'meta': None}
    t = item.get('thread')
    return {'running': bool(t.is_alive()), 'meta': item.get('meta')}


def get_position_info(symbol, cfg):
    """Query exchange positions and return matching position info or None."""
    ex = _get_exchange(cfg)
    try:
        positions = ex.fetch_positions()
    except Exception:
        # fallback to fetch_positions([symbol]) if supported
        try:
            positions = ex.fetch_positions([symbol])
        except Exception:
            return None

    candidates = [symbol, symbol.replace('/', ''), f"{symbol}:USDT", symbol.replace('/', '') + ':USDT']
    for p in positions:
        p_sym = p.get('symbol')
        if not p_sym:
            continue
        if p_sym in candidates or any(c in str(p_sym) for c in candidates):
            return {
                'symbol': p_sym,
                'contracts': p.get('contracts') or p.get('contractSize') or p.get('amount') or 0,
                'entryPrice': p.get('entryPrice') or p.get('entry_price') or p.get('avgPrice'),
                'side': p.get('side') or p.get('positionSide'),
                'raw': p
            }
    return None


def execute_trade_v2(signal_payload, cfg):
    """Abre posição a mercado, envia stop market imediato e prepara trailing stop.

    - signal_payload: string ou dict (pode conter 'final_decision')
    - cfg: configuração carregada
    Retorna dict com chaves 'order_id' ou 'error' e detalhes.
    """
    exchange = _get_exchange(cfg)
    symbol = cfg['trading']['symbol']

    # Extrai decisão
    decision = None
    if isinstance(signal_payload, dict):
        for k in ('final_decision', 'decision', 'signal', 'action'):
            if k in signal_payload:
                decision = signal_payload[k]
                break
    else:
        decision = signal_payload

    normalized = _normalize_signal(decision)
    if normalized is None:
        msg = f"Sinal inválido/indefinido: {decision}"
        print(f"⚠️ {msg}")
        return {'error': msg}

    side = 'buy' if normalized == 'BUY' else 'sell'

    try:
        exchange.load_markets()
        ticker = exchange.fetch_ticker(symbol)
        price = float(ticker.get('last') or ticker.get('close') or 0)

        if price <= 0:
            return {'error': f'Preço inválido para cálculo de quantidade: {price}'}

        amount = _calculate_amount(cfg, price)
        if amount is None or amount <= 0:
            err = f'Impossível calcular quantidade (saldo/risco insuficiente). Amount={amount}'
            print(f"⚠️ {err}")
            return {'error': err}

        notional = float(amount) * float(price)
        min_notional = float(cfg.get('trading', {}).get('min_notional', 100))
        if notional < min_notional:
            # Ajusta a quantidade para atingir o notional mínimo
            amount = min_notional / price
            notional = float(amount) * float(price)
            print(f"📊 Ajustado amount para atingir min_notional: {amount:.6f}")

        print(f"🚀 V2 Ordem Market {side.upper()} {amount:.6f} {symbol} (~${notional:.2f})")

        # 1) Envia ordem Market (entrada) com tentativa de ajuste se notional for rejeitado
        entry = None
        retries = 3
        last_exc = None
        amount = float(amount)  # Garante conversão
        
        for attempt in range(retries):
            try:
                entry = exchange.create_market_order(symbol, side, amount)
                break
            except Exception as e:
                last_exc = e
                err_text = str(e)
                # Se erro for sobre notional mínimo, tenta aumentar quantidade e re-enviar
                if 'notional' in err_text.lower() or '4164' in err_text:
                    min_notional = float(cfg.get('trading', {}).get('min_notional', 100))
                    # Ajusta para 50% acima do mínimo para evitar issues de arredondamento
                    amount = max(float(amount) * 1.25, (min_notional * 1.5) / price)
                    print(f"⚠️ Ajustando quantidade por notional e tentando novamente (attempt {attempt+1})... Novo amount: {amount:.6f}")
                    time.sleep(1)
                    continue
                else:
                    msg = f"Erro ao enviar ordem de entrada: {e}"
                    print(f"❌ {msg}")
                    return {'error': msg}

        if entry is None:
            msg = f"Falha ao enviar ordem de entrada apos {retries} tentativas. Último erro: {last_exc}"
            print(f"❌ {msg}")
            return {'error': msg}

        # 2) Cancelar ordens antigas e preparar stops
        _cancel_open_orders(exchange, symbol)

        # Parâmetros de risco
        rm = cfg.get('risk_management', {})
        stop_loss_pct = float(rm.get('stop_loss_pct', 0.02))
        trailing_activation = float(rm.get('trailing_activation_pct', 0.005))
        callback_rate = float(rm.get('trailing_callback_rate', 1.0))

        # Calcula preço do stop
        if side == 'buy':
            stop_price = price * (1.0 - stop_loss_pct)
            trailing_side = 'sell'
        else:
            stop_price = price * (1.0 + stop_loss_pct)
            trailing_side = 'buy'

        # 3) Envia Stop Market de proteção (reduceOnly)
        try:
            params = {'stopPrice': round(stop_price, 2), 'closePosition': False, 'reduceOnly': True}
            stop_order = exchange.create_order(symbol, 'STOP_MARKET', trailing_side, amount, None, params)
            print(f"🛡️ Stop market criado @ {stop_price:.2f}")
        except Exception as e:
            stop_order = None
            print(f"⚠️ Falha ao criar stop market: {e}")

        # 4) Prepara Trailing Stop nativo (será ativado apenas quando o trade tiver lucro)
        # Tenta criar ordem nativa; se não suportada, caimos para monitor local em background
        trailing_order = None
        try:
            params_trail = {'callbackRate': float(callback_rate), 'reduceOnly': True}
            trailing_order = exchange.create_order(symbol, 'TRAILING_STOP_MARKET', trailing_side, amount, None, params_trail)
            print(f"🎯 Trailing stop pré-criado (callbackRate={callback_rate}%)")
        except Exception as e:
            trailing_order = None
            print(f"⚠️ Falha ao criar trailing stop: {e}")

        # Se qualquer ordem de proteção não foi criada, iniciamos um monitor local de posição
        monitor_id = None
        try:
            if stop_order is None or trailing_order is None:
                entry_price = float(entry.get('price', price))
                amount_for_monitor = float(amount)
                
                if entry_price <= 0 or amount_for_monitor <= 0:
                    print(f"⚠️ Valores inválidos para monitor: entry_price={entry_price}, amount={amount_for_monitor}")
                else:
                    monitor_id, monitor_thread = start_position_monitor(symbol, entry_price, amount_for_monitor, side, cfg,
                                                                        stop_loss_pct=stop_loss_pct,
                                                                        trailing_activation=trailing_activation,
                                                                        callback_rate=callback_rate)
                    print(f"🕵️ Monitor local iniciado (id={monitor_id})")
        except Exception as monitor_err:
            print(f"⚠️ Erro ao iniciar monitor local: {monitor_err}")
            # Continua mesmo se monitor falhar - o trade foi aberto

        return {
            'order_id': entry.get('id'),
            'entry': entry,
            'stop_order': stop_order,
            'trailing_order': trailing_order,
            'notional': notional,
            'monitor_id': monitor_id
        }

    except Exception as e:
        msg = f"Erro V2 execução: {e}"
        print(f"❌ {msg}")
        return {'error': msg}


def close_position(cfg):
    """Fecha posição aberta no símbolo configurado (market reduceOnly), cancela stops pendentes.
    Retorna dict com status ou error.
    """
    exchange = _get_exchange(cfg)
    symbol = cfg['trading']['symbol']

    try:
        # Cancela ordens pendentes
        _cancel_open_orders(exchange, symbol)

        # Busca posição
        # Try several symbol formats to find the position
        candidates = [symbol, symbol.replace('/', ''), f"{symbol}:USDT", symbol.replace('/', '') + ':USDT']
        positions = exchange.fetch_positions()
        pos_amount = 0
        pos_side = None
        for p in positions:
            p_sym = p.get('symbol')
            if not p_sym:
                continue
            if p_sym in candidates or any(c in str(p_sym) for c in candidates):
                contracts = p.get('contracts') or p.get('contractSize') or p.get('amount') or 0
                try:
                    pos_amount = float(contracts)
                except Exception:
                    pos_amount = 0
                pos_side = p.get('side') or p.get('positionSide') or ('long' if pos_amount > 0 else 'short')
                break

        if not pos_amount or pos_amount == 0:
            return {'status': 'no_position'}

        # Determina side para fechar
        close_side = 'sell' if str(pos_side).lower() in ('long', 'buy', 'long_position') else 'buy'

        # Envia market order reduceOnly para fechar (tenta com vários formatos se necessário)
        tried = []
        try:
            params = {'reduceOnly': True}
            res = exchange.create_market_order(symbol, close_side, pos_amount, None, params)
            return {'status': 'closed', 'result': res}
        except Exception as e:
            tried.append((symbol, str(e)))
            # Tenta variações do symbol
            alt_symbols = [symbol.replace('/', ''), symbol + ':USDT', symbol.replace('/', '') + ':USDT']
            for alt in alt_symbols:
                try:
                    res = exchange.create_market_order(alt, close_side, pos_amount, None, {'reduceOnly': True})
                    return {'status': 'closed', 'result': res}
                except Exception as e2:
                    tried.append((alt, str(e2)))
            return {'error': f'Erro ao fechar posição. Tentativas: {tried}'}

    except Exception as e:
        return {'error': f'Erro ao buscar/fechar posição: {e}'}
