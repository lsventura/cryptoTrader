import ccxt
import yaml

with open("config/config.yaml") as f:
    cfg = yaml.safe_load(f)

# TENTATIVA 1: O jeito "proibido" (Sandbox Mode)
print("\n--- TESTE 1: set_sandbox_mode(True) ---")
ex1 = ccxt.binance({
    'apiKey': cfg['exchange']['api_key'],
    'secret': cfg['exchange']['api_secret'],
    'options': {'defaultType': 'future'}
})
try:
    ex1.set_sandbox_mode(True)
    print("URLs após sandbox:", ex1.urls['api']['fapiPublic'])
    bal = ex1.fetch_balance({'type': 'future'})
    print("✅ SUCESSO! Saldo:", bal['total']['USDT'])
except Exception as e:
    print("❌ FALHA:", e)

# TENTATIVA 2: O jeito "manual" que estamos tentando
print("\n--- TESTE 2: URL Manual ---")
ex2 = ccxt.binance({
    'apiKey': cfg['exchange']['api_key'],
    'secret': cfg['exchange']['api_secret'],
    'options': {'defaultType': 'future'}
})
ex2.urls['api']['fapiPublic'] = 'https://testnet.binancefuture.com/fapi/v1'
ex2.urls['api']['fapiPrivate'] = 'https://testnet.binancefuture.com/fapi/v1'
try:
    bal = ex2.fetch_balance({'type': 'future'})
    print("✅ SUCESSO! Saldo:", bal['total']['USDT'])
except Exception as e:
    print("❌ FALHA:", e)
