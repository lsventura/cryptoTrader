import ccxt

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
