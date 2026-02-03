import pandas as pd
import pandas_ta as ta
import numpy as np

class Strategy:
    def __init__(self, cfg):
        self.cfg = cfg
        # Configurações de sensibilidade
        self.rsi_period = 14
        self.ema_period = 20
        self.atr_period = 14
        
        # Gestão de Risco
        self.trailing_stop_activation = 0.015  # Ativa trailing após 1.5% de lucro
        self.trailing_stop_distance = 0.005    # Mantém stop a 0.5% de distância

    def calculate_indicators(self, df):
        """Calcula os indicadores técnicos matemáticos"""
        df = df.copy()
        
        # RSI
        df['RSI'] = ta.rsi(df['close'], length=self.rsi_period)
        
        # EMA (Média Móvel Exponencial)
        df['EMA'] = ta.ema(df['close'], length=self.ema_period)
        
        # ATR (Volatilidade - crucial para stop loss dinâmico)
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_period)
        
        return df

    def get_technical_signal(self, df):
        """Define o sinal puramente técnico (sem IA)"""
        last_row = df.iloc[-1]
        rsi = last_row['RSI']
        close = last_row['close']
        ema = last_row['EMA']
        
        # Lógica Clássica de Tendência
        if rsi < 35 and close > ema: 
            return "BUY"  # Pullback em tendência de alta
        elif rsi > 65 and close < ema:
            return "SELL" # Pullback em tendência de baixa
            
        # Cruzamento de EMA (Trend Following básico)
        if close > ema and rsi > 50:
            return "BUY"
        if close < ema and rsi < 50:
            return "SELL"
            
        return "NEUTRAL"

    def manage_position(self, current_position, current_price, new_signal):
        """
        A LÓGICA INTELIGENTE QUE VOCÊ PEDIU:
        Decide se segura, inverte ou ajusta stop.
        """
        if not current_position or current_position['amount'] == 0:
            return "OPEN_NEW"

        pos_side = current_position['side'] # 'long' ou 'short'
        entry_price = float(current_position['entryPrice'])
        pnl_percent = (current_price - entry_price) / entry_price if pos_side == 'long' else (entry_price - current_price) / entry_price
        
        # 1. STOP AND REVERSE (Virada de Mão)
        # Se estamos comprados e o sinal virou VENDA forte
        if pos_side == 'long' and new_signal == 'SELL':
            return "FLIP_TO_SHORT" # Fecha Long, Abre Short
            
        # Se estamos vendidos e o sinal virou COMPRA forte
        if pos_side == 'short' and new_signal == 'BUY':
            return "FLIP_TO_LONG" # Fecha Short, Abre Long

        # 2. TRAILING STOP (Garantir Lucro)
        # Se o sinal continua o mesmo, mas estamos lucrando bem
        if (pos_side == 'long' and new_signal == 'BUY') or (pos_side == 'short' and new_signal == 'SELL'):
            
            # Se lucro > 1.5%, recomenda apertar o stop
            if pnl_percent > self.trailing_stop_activation:
                return "UPDATE_STOP_LOSS" 
                
            return "HOLD" # Continua no trade, deixa o lucro correr

        return "HOLD"

    def combine_signals(self, df, ai_sentiment, current_position=None):
        """
        O Cérebro Central: Junta Técnica + IA + Posição Atual
        """
        df = self.calculate_indicators(df)
        tech_signal = self.get_technical_signal(df)
        current_price = df.iloc[-1]['close']
        
        final_decision = "NEUTRAL"
        
        # --- Lógica de Confluência (IA + Técnica) ---
        if tech_signal == "BUY" and ai_sentiment in ["BULLISH", "NEUTRAL"]:
            final_signal = "BUY"
        elif tech_signal == "SELL" and ai_sentiment in ["BEARISH", "NEUTRAL"]:
            final_signal = "SELL"
        else:
            # Se IA diz Alta e Gráfico diz Baixa, ficamos neutros (segurança)
            final_signal = "NEUTRAL"

        # --- Se não temos posição, seguimos o sinal puro ---
        if current_position is None or current_position == 0:
            return final_signal

        # --- Se JÁ TEMOS posição, usamos a gestão inteligente ---
        action = self.manage_position(current_position, current_price, final_signal)
        
        print(f"🧠 Decisão Estratégica: Sinal={final_signal} | Ação={action}")
        
        if action == "FLIP_TO_SHORT":
            return "SELL" # Vai gerar venda (fechar long + abrir short)
        elif action == "FLIP_TO_LONG":
            return "BUY"
        elif action == "UPDATE_STOP_LOSS":
            # Aqui retornaríamos um comando especial, mas por simplificação
            # retornamos HOLD pois a gestão de stop seria feita no execution
            # Para o bot atual, HOLD significa "não faça nada no market order"
            return "HOLD" 
        elif action == "HOLD":
            return "NEUTRAL" # Neutral impede novas ordens a mercado
            
        return final_signal
import pandas as pd
import pandas_ta as ta
import numpy as np

class Strategy:
    def __init__(self, cfg):
        self.cfg = cfg
        # Configurações de sensibilidade
        self.rsi_period = 14
        self.ema_period = 20
        self.atr_period = 14
        
        # Gestão de Risco
        self.trailing_stop_activation = 0.015  # Ativa trailing após 1.5% de lucro
        self.trailing_stop_distance = 0.005    # Mantém stop a 0.5% de distância

    def calculate_indicators(self, df):
        """Calcula os indicadores técnicos matemáticos"""
        df = df.copy()
        
        # RSI
        df['RSI'] = ta.rsi(df['close'], length=self.rsi_period)
        
        # EMA (Média Móvel Exponencial)
        df['EMA'] = ta.ema(df['close'], length=self.ema_period)
        
        # ATR (Volatilidade - crucial para stop loss dinâmico)
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_period)
        
        return df

    def get_technical_signal(self, df):
        """Define o sinal puramente técnico (sem IA)"""
        last_row = df.iloc[-1]
        rsi = last_row['RSI']
        close = last_row['close']
        ema = last_row['EMA']
        
        # Lógica Clássica de Tendência
        if rsi < 35 and close > ema: 
            return "BUY"  # Pullback em tendência de alta
        elif rsi > 65 and close < ema:
            return "SELL" # Pullback em tendência de baixa
            
        # Cruzamento de EMA (Trend Following básico)
        if close > ema and rsi > 50:
            return "BUY"
        if close < ema and rsi < 50:
            return "SELL"
            
        return "NEUTRAL"

    def manage_position(self, current_position, current_price, new_signal):
        """
        A LÓGICA INTELIGENTE QUE VOCÊ PEDIU:
        Decide se segura, inverte ou ajusta stop.
        """
        if not current_position or current_position['amount'] == 0:
            return "OPEN_NEW"

        pos_side = current_position['side'] # 'long' ou 'short'
        entry_price = float(current_position['entryPrice'])
        pnl_percent = (current_price - entry_price) / entry_price if pos_side == 'long' else (entry_price - current_price) / entry_price
        
        # 1. STOP AND REVERSE (Virada de Mão)
        # Se estamos comprados e o sinal virou VENDA forte
        if pos_side == 'long' and new_signal == 'SELL':
            return "FLIP_TO_SHORT" # Fecha Long, Abre Short
            
        # Se estamos vendidos e o sinal virou COMPRA forte
        if pos_side == 'short' and new_signal == 'BUY':
            return "FLIP_TO_LONG" # Fecha Short, Abre Long

        # 2. TRAILING STOP (Garantir Lucro)
        # Se o sinal continua o mesmo, mas estamos lucrando bem
        if (pos_side == 'long' and new_signal == 'BUY') or (pos_side == 'short' and new_signal == 'SELL'):
            
            # Se lucro > 1.5%, recomenda apertar o stop
            if pnl_percent > self.trailing_stop_activation:
                return "UPDATE_STOP_LOSS" 
                
            return "HOLD" # Continua no trade, deixa o lucro correr

        return "HOLD"

    def combine_signals(self, df, ai_sentiment, current_position=None):
        """
        O Cérebro Central: Junta Técnica + IA + Posição Atual
        """
        df = self.calculate_indicators(df)
        tech_signal = self.get_technical_signal(df)
        current_price = df.iloc[-1]['close']
        
        final_decision = "NEUTRAL"
        
        # --- Lógica de Confluência (IA + Técnica) ---
        if tech_signal == "BUY" and ai_sentiment in ["BULLISH", "NEUTRAL"]:
            final_signal = "BUY"
        elif tech_signal == "SELL" and ai_sentiment in ["BEARISH", "NEUTRAL"]:
            final_signal = "SELL"
        else:
            # Se IA diz Alta e Gráfico diz Baixa, ficamos neutros (segurança)
            final_signal = "NEUTRAL"

        # --- Se não temos posição, seguimos o sinal puro ---
        if current_position is None or current_position == 0:
            return final_signal

        # --- Se JÁ TEMOS posição, usamos a gestão inteligente ---
        action = self.manage_position(current_position, current_price, final_signal)
        
        print(f"🧠 Decisão Estratégica: Sinal={final_signal} | Ação={action}")
        
        if action == "FLIP_TO_SHORT":
            return "SELL" # Vai gerar venda (fechar long + abrir short)
        elif action == "FLIP_TO_LONG":
            return "BUY"
        elif action == "UPDATE_STOP_LOSS":
            # Aqui retornaríamos um comando especial, mas por simplificação
            # retornamos HOLD pois a gestão de stop seria feita no execution
            # Para o bot atual, HOLD significa "não faça nada no market order"
            return "HOLD" 
        elif action == "HOLD":
            return "NEUTRAL" # Neutral impede novas ordens a mercado
            
        return final_signal
