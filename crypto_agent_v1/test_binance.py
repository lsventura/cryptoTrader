import ccxt
import yaml

with open("config/config.yaml") as f:
    cfg = yaml.safe_load(f)

ex_class = getattr(ccxt, cfg["exchange"]["name"])
exchange = ex_class({
    "apiKey": cfg["exchange"]["api_key"],
    "secret": cfg["exchange"]["api_secret"],
    "enableRateLimit": True,
    "options": {
        "recvWindow": 60000,
    },
})

if cfg["exchange"].get("testnet", False) and hasattr(exchange, "set_sandbox_mode"):
    exchange.set_sandbox_mode(True)

symbol = cfg["trading"]["symbol"]

print("Conectando na Binance...")
print("Server time:", exchange.fetch_time())
print("Ticker:", exchange.fetch_ticker(symbol))
# POR ENQUANTO, NÃO BUSCA BALANCE PRA NÃO CAIR NO INVALIDNONCE
# print("Balance USDT:", exchange.fetch_balance().get("total", {}).get("USDT"))
print("Conexão bem-sucedida!")