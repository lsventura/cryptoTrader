import ccxt
import pandas as pd
import numpy as np
import ta
import joblib
import time
import os
import logging
from enum import Enum
from dotenv import load_dotenv

# ==============================================================================
# MÓDULO 0: CONFIGURAÇÃO E SETUP INICIAL
# ==============================================================================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Config:
    SYMBOL = 'ETH/USDT'
    TIMEFRAME = '15m'
    RISK_PER_TRADE = 0.015
    LEVERAGE = 5.0
    
    PROBABILITY_THRESHOLD = 0.65
    ATR_MULTIPLIER = 2.5
    RR_RATIO = 1.7
    BULL_PROB_THRESHOLD = 0.60
    
    MODEL_PATH = 'models/modelo_lgbm.pkl'
    SCALER_PATH = 'models/scaler.pkl'

class Action(Enum):
    HOLD = 0
    GO_LONG = 1
    CLOSE_POSITION = 2

# ==============================================================================
# MÓDULO 1: INTERFACE COM A EXCHANGE
# ==============================================================================

class BinanceTrader:
    def __init__(self, api_key, api_secret):
        try:
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {'defaultType': 'future'},
            })
            self.exchange.set_sandbox_mode(True)
            self.exchange.load_markets()
            logger.info("Conexão com a Binance Futures Testnet estabelecida.")
        except Exception as e:
            logger.critical(f"Falha ao inicializar a conexão com a exchange: {e}")
            raise

    def fetch_ohlcv(self, symbol, timeframe, limit=500):
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Erro ao buscar dados OHLCV: {e}")
            return None

    def get_balance(self, currency='USDT'):
        try:
            balance = self.exchange.fetch_balance()
            return balance['total'][currency]
        except Exception as e:
            logger.error(f"Erro ao buscar saldo: {e}")
            return 0

    def get_open_position(self, symbol):
        try:
            positions = self.exchange.fetch_positions([symbol])
            position = next((p for p in positions if p.get('info', {}).get('symbol') == symbol and float(p.get('info', {}).get('positionAmt', 0)) != 0), None)
            return position
        except Exception as e:
            logger.error(f"Erro ao buscar posições: {e}")
            return None

    def place_market_order(self, symbol, side, amount):
        try:
            logger.info(f"A colocar ordem a mercado: {side} {amount} {symbol}")
            order = self.exchange.create_market_order(symbol, side, amount)
            return order
        except Exception as e:
            logger.error(f"Erro ao colocar ordem a mercado: {e}")
            return None

    def place_protection_orders(self, symbol, entry_price, position_size, atr_value):
        try:
            sl_price = entry_price - (atr_value * Config.ATR_MULTIPLIER)
            tp_price = entry_price + ((entry_price - sl_price) * Config.RR_RATIO)
            
            sl_price = self.exchange.price_to_precision(symbol, sl_price)
            tp_price = self.exchange.price_to_precision(symbol, tp_price)

            logger.info(f"A colocar ordens de proteção: SL={sl_price}, TP={tp_price}")
            
            self.exchange.create_order(symbol, 'STOP_MARKET', 'sell', position_size, params={'stopPrice': sl_price})
            self.exchange.create_order(symbol, 'TAKE_PROFIT_MARKET', 'sell', position_size, params={'stopPrice': tp_price})
            return True
        except Exception as e:
            logger.error(f"Erro ao colocar ordens de proteção: {e}")
            return False

    def cancel_all_open_orders(self, symbol):
        try:
            logger.info(f"A cancelar todas as ordens abertas para {symbol}")
            self.exchange.cancel_all_orders(symbol)
            return True
        except Exception as e:
            logger.error(f"Erro ao cancelar ordens: {e}")
            return False

# ==============================================================================
# MÓDULO 2: O CÉREBRO DA ESTRATÉGIA
# ==============================================================================

class Strategy:
    def __init__(self, model_path, scaler_path):
        try:
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            logger.info("Estratégia inicializada com modelo e scaler.")
        except FileNotFoundError:
            logger.critical("Ficheiros de modelo/scaler não encontrados.")
            raise

    def _engineer_features(self, df: pd.DataFrame):
        df['rsi_14'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        df['adx'] = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14).adx()
        df['atr_14'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
        
        for tf in ['1H', '4H']:
            df_resampled = df.resample(tf).agg({'close': 'last', 'high': 'max', 'low': 'min'})
            ema_fast = ta.trend.EMAIndicator(df_resampled['close'], window=20).ema_indicator()
            ema_slow = ta.trend.EMAIndicator(df_resampled['close'], window=50).ema_indicator()
            df[f'ema_trend_{tf}'] = (ema_fast > ema_slow).astype(int).reindex(df.index, method='ffill')
            
        df_weekly = df.resample('D').agg({'close': 'last'}).resample('W').last()
        weekly_ema_fast = ta.trend.EMAIndicator(df_weekly['close'], window=10).ema_indicator()
        weekly_ema_slow = ta.trend.EMAIndicator(df_weekly['close'], window=21).ema_indicator()
        df_weekly['is_macro_bull'] = (weekly_ema_fast > weekly_ema_slow)
        df['is_macro_bull'] = df_weekly['is_macro_bull'].reindex(df.index, method='ffill')
        df['is_macro_bull'].fillna(False, inplace=True)
        return df

    def get_decision(self, df: pd.DataFrame):
        df_featured = self._engineer_features(df.copy())
        last_candle = df_featured.iloc[[-1]]

        if last_candle.isnull().values.any():
            logger.warning("Dados insuficientes para gerar todas as features. A aguardar.")
            return Action.HOLD, None

        features = [col for col in df_featured.columns if col not in ['open', 'high', 'low', 'close', 'volume', 'target']]
        X_last = last_candle[features]
        
        X_last_scaled = self.scaler.transform(X_last)
        
        probabilities = self.model.predict_proba(X_last_scaled)[0]
        p_baixa, _, p_alta = probabilities[0], probabilities[1], probabilities[2]
        logger.info(f"Previsão: BAIXA={p_baixa:.2f}, ALTA={p_alta:.2f}")

        is_macro_bull = last_candle['is_macro_bull'].iloc[0]
        is_1h_trend_up = last_candle['ema_trend_1H'].iloc[0] == 1
        adx_strong = last_candle['adx'].iloc[0] > 20
        
        if not is_macro_bull:
            return Action.CLOSE_POSITION, last_candle

        if is_macro_bull and is_1h_trend_up and p_alta > Config.BULL_PROB_THRESHOLD:
            logger.info("Condição de entrada 'Caçador' atingida.")
            return Action.GO_LONG, last_candle
            
        if not is_macro_bull and is_1h_trend_up and adx_strong and p_alta > Config.PROBABILITY_THRESHOLD:
            logger.info("Condição de entrada 'Sniper' atingida.")
            return Action.GO_LONG, last_candle

        return Action.HOLD, last_candle

# ==============================================================================
# MÓDULO 3: O ORQUESTRADOR DO BOT
# ==============================================================================

class TradingBot:
    def __init__(self, config: Config, trader: BinanceTrader, strategy: Strategy):
        self.config = config
        self.trader = trader
        self.strategy = strategy

    def _calculate_position_size(self, balance, entry_price, sl_price):
        risk_per_trade_usd = balance * self.config.RISK_PER_TRADE
        sl_distance_usd = entry_price - sl_price
        if sl_distance_usd <= 0: return 0
        
        position_size_asset = risk_per_trade_usd / sl_distance_usd
        final_size = position_size_asset * self.config.LEVERAGE
        
        return self.trader.exchange.amount_to_precision(self.config.SYMBOL, final_size)

    def _run_trade_cycle(self):
        logger.info("--- A iniciar novo ciclo de trading ---")
        
        open_position = self.trader.get_open_position(self.config.SYMBOL)
        market_data = self.trader.fetch_ohlcv(self.config.SYMBOL, self.config.TIMEFRAME)
        
        if market_data is None:
            logger.warning("Não foi possível obter dados de mercado. A saltar este ciclo.")
            return

        decision, last_candle_data = self.strategy.get_decision(market_data)
        logger.info(f"Decisão da Estratégia: {decision.name}")

        if open_position:
            if decision == Action.CLOSE_POSITION:
                logger.info("Sinal para fechar posição recebido.")
                position_size = float(open_position['info']['positionAmt'])
                self.trader.cancel_all_open_orders(self.config.SYMBOL)
                self.trader.place_market_order(self.config.SYMBOL, 'sell', abs(position_size))
        else:
            if decision == Action.GO_LONG:
                logger.info("Sinal para entrar em posição Long recebido.")
                balance = self.trader.get_balance()
                entry_price = last_candle_data['close'].iloc[0]
                atr_value = last_candle_data['atr_14'].iloc[0]
                sl_price = entry_price - (atr_value * self.config.ATR_MULTIPLIER)

                position_size = self._calculate_position_size(balance, entry_price, sl_price)

                if float(position_size) > 0:
                    entry_order = self.trader.place_market_order(self.config.SYMBOL, 'buy', position_size)
                    if entry_order:
                        time.sleep(2) # Pausa para garantir processamento da ordem de entrada
                        # A lógica de proteção para hunter (TSL) vs sniper (TP) precisaria ser mais complexa aqui.
                        # Para simplificar, vamos usar a proteção Sniper (SL/TP) para todas as ordens.
                        self.trader.place_protection_orders(self.config.SYMBOL, entry_price, position_size, atr_value)
                else:
                    logger.warning("Tamanho da posição calculado é zero. Nenhuma ordem colocada.")

    def run(self):
        logger.info("Bot de trading a iniciar.")
        while True:
            try:
                now = pd.to_datetime('now', utc=True)
                next_candle_close = (now + pd.Timedelta(minutes=15)).floor('15min')
                sleep_seconds = max(0, (next_candle_close - now).total_seconds() + 5)
                
                logger.info(f"A aguardar {sleep_seconds:.0f} segundos até ao fecho da próxima vela...")
                time.sleep(sleep_seconds)
                
                self._run_trade_cycle()

            except KeyboardInterrupt:
                logger.info("Bot de trading a desligar manualmente.")
                break
            except Exception as e:
                logger.critical(f"ERRO CRÍTICO no loop principal: {e}", exc_info=True)
                time.sleep(60)

# ==============================================================================
# BLOCO DE EXECUÇÃO PRINCIPAL
# ==============================================================================

if __name__ == '__main__':
    config = Config()
    api_key = os.getenv('BINANCE_TESTNET_API_KEY')
    secret_key = os.getenv('BINANCE_TESTNET_SECRET_KEY')

    if not api_key or not secret_key:
        logger.error("Chaves de API não encontradas. Defina BINANCE_TESTNET_API_KEY e BINANCE_TESTNET_SECRET_KEY no seu ficheiro .env")
    else:
        try:
            trader = BinanceTrader(api_key, secret_key)
            strategy = Strategy(config.MODEL_PATH, config.SCALER_PATH)
            bot = TradingBot(config, trader, strategy)
            bot.run()
        except Exception as e:
            logger.critical(f"Falha ao inicializar o bot: {e}")