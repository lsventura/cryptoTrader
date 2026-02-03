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
        usable_balance = free_usdt * percentage
        
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        
        quantity_usd = usable_balance * leverage
        amount = quantity_usd / price
        
        print(f"💰 Saldo: ${free_usdt:.2f} | Entrada: ${quantity_usd:.2f}")
        print(f"⚖️ Qtd: {amount:.4f} {symbol}")

        # 4. Envia Ordem
        side = 'buy' if signal == 'BUY' else 'sell'
        print(f"🚀 Enviando ordem {side.upper()}...")
        order = exchange.create_market_order(symbol, side, amount)
        print(f"✅ Ordem executada: {order['id']}")
        return order
        
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

def update_stop_loss(cfg, side, price):
    """
    Move o Stop Loss para um novo preço.
    """
    exchange = _get_exchange(cfg)
    symbol = cfg['trading']['symbol']
    
    try:
        # 1. Cancela Stops Antigos
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            if order['type'] == 'STOP_MARKET':
                exchange.cancel_order(order['id'], symbol)
                print(f"🗑️ Stop antigo cancelado: {order['id']}")
        
        # 2. Cria Novo Stop
        # Se estamos comprados (LONG), stop é SELL. Se vendidos (SHORT), stop é BUY.
        stop_side = 'sell' if side == 'long' else 'buy'
        
        params = {'stopPrice': price}
        
        # Quantidade: Precisamos saber o tamanho da posição. 
        # Por simplificação, vamos assumir fechar a posição inteira.
        pos_size = fetch_position(cfg)
        if pos_size == 0: return # Sem posição, sem stop
        
        print(f"🛡️ Ajustando Stop Loss ({side}) para ${price}")
        order = exchange.create_order(symbol, 'STOP_MARKET', stop_side, abs(pos_size), None, params)
        print(f"✅ Novo Stop definido: {order['id']}")
        return order
        
    except Exception as e:
        print(f"❌ Erro ao mover Stop: {e}")
        return None
