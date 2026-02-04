# Engenharia de Software Sênior - Refactor V2

## 🎯 Objetivo
Resolver dois problemas críticos no bot de trading:
1. **Otimizador Viciado (Overfitting)**: Crash de 24h atrás influenciando parâmetros de hoje
2. **Cérebro Desconectado**: Lógica simples ignorando estratégia avançada

---

## ✅ Mudanças Implementadas

### 1. `src/agents/optimizer.py` - Curar o "Trauma"

**Problema**: O otimizador olhava todo o histórico igualmente, fazendo com que crashes antigos dominassem a decisão.

**Solução**: **Peso Recente + Janela Deslizante**

```python
# Antes: Considerava TODO o histórico
total_pnl = pnl_long + pnl_short

# Depois: Foca nos últimos 72 candles + peso 2x para últimas 24 candles
window_size = min(72, len(df))  # 18h de histórico em 15m
df_recent['weight'] = 1.0
df_recent.iloc[-24:, weight_col] = 2.0  # Últimas 6h = 2x peso

total_pnl_weighted = (pnl_long * weight) + (pnl_short * weight)
```

**Impacto**:
- ✅ Se crash foi há 36h: será ignorado (fora dos 72 candles)
- ✅ Se mercado está calmo agora (últimas 6h): parâmetros ajustados para mercado calmo (RSI ~50)
- ✅ Evita RSI ultra-conservador (30) baseado em evento extremo passado

---

### 2. `src/bot_v2.py` - Conectar o Cérebro Avançado

**Problema**: Bot usava `quant_agent` simples; tinha `super_strategy.py` com lógica sofisticada mas era ignorada.

**Solução**: **Integração Completa com Strategy Engine**

#### A) Imports & Instanciação
```python
# Importa a classe Strategy avançada
from src.agents.super_strategy import Strategy

# Instancia UMA VEZ no init do loop (eficiente)
strategy_engine = Strategy(cfg)

# Recarrega estratégia quando tuner otimiza config
if cycle % 60 == 0:
    tuner_agent(...)
    cfg = reload_config()
    strategy_engine = Strategy(cfg)  # RE-INSTANCIA com novos params
```

#### B) Fluxo de Decisão Aprimorado
```python
# Antes: Lógica simples
if sentiment == "BULLISH" and quant_signal == "LONG":
    decision = "BUY"

# Depois: Estratégia avançada
decision = strategy_engine.combine_signals(
    df=candles, 
    ai_sentiment=s['sentiment'], 
    current_position=get_position_info(symbol, cfg)
)
# Retorna: "BUY", "SELL", "HOLD", "FLIP_TO_SHORT", "FLIP_TO_LONG", "UPDATE_STOP_LOSS"
```

#### C) Tratamento de Decisões Complexas
```python
if decision == 'FLIP_TO_SHORT':
    close_position(cfg)  # Fecha LONG
    execute_trade_v2({'final_decision': 'SELL'}, cfg)  # Abre SHORT

elif decision == 'FLIP_TO_LONG':
    close_position(cfg)  # Fecha SHORT
    execute_trade_v2({'final_decision': 'BUY'}, cfg)  # Abre LONG

elif decision == 'UPDATE_STOP_LOSS':
    # Monitor local já lida com trailing quando ativo

elif decision == 'HOLD':
    # Mantém posição, sem tocar
```

---

## 📊 Super Strategy (Conectada)

### Fluxo Decisório
```
1. calculate_indicators()
   ├─ RSI
   ├─ EMA
   └─ ATR

2. get_technical_signal()
   └─ RSI < 35 & Close > EMA → "BUY"
   └─ RSI > 65 & Close < EMA → "SELL"
   └─ Cruzamento EMA → Trend Following

3. manage_position() [LÓGICA INTELIGENTE]
   ├─ FLIP_TO_SHORT: Long aberto + nova sinal SELL
   ├─ FLIP_TO_LONG: Short aberto + nova sinal BUY
   ├─ UPDATE_STOP_LOSS: Lucro > 1.5% → apertar stop
   └─ HOLD: Manter posição atual

4. combine_signals()
   ├─ Mescla: Técnica + IA + Posição Atual
   ├─ Confluência segura (evita conflito técnica/IA)
   └─ Retorna decisão final
```

---

## 🔄 Fluxo do Tuner com Strategy

```
Ciclo 1 / Ciclo 60:
  ├─ tuner_agent() otimiza config.yaml
  │  └─ Foco nos últimos 72 candles
  │  └─ Peso recente (2x) para últimas 24 candles
  │
  ├─ reload_config()
  │  └─ Lê novos params (RSI, EMA, stop_loss_pct, etc.)
  │
  └─ strategy_engine = Strategy(cfg)
     └─ RE-INSTANCIA com novos parâmetros
     └─ Próximas decisões usam config otimizada
```

---

## 🛡️ Validações de Segurança

### 1. Posição Atual
```python
current_pos = get_position_info(symbol, cfg)
# Passa para estratégia via manage_position()
# Garante que FLIP só ocorre se posição existe
```

### 2. Duplicação de Ordem
```python
if has_position and decision not in ['FLIP_TO_SHORT', 'FLIP_TO_LONG']:
    LOG('⚠️ Ignorando novo sinal - já tem posição')
```

### 3. Monitor Local Ativo
```python
# Se FLIP: para monitor antigo → abre novo
for mid in list(monitors.keys()):
    stop_monitor(mid)  # Cancela trailing do anterior
execute_trade_v2({'final_decision': decision})  # Novo monitor
```

---

## 📈 Resultados Esperados

### Cenário: Crash ontem, mercado calmo hoje

**Antes**:
- Tuner olha crash + mercado calmo igualmente
- Sugere RSI < 30 (ultra-conservador)
- Bot não entra em nenhum trade

**Depois**:
- Tuner ignora crash (fora dos 72 candles)
- Foca nos últimos 18h (mercado calmo)
- Sugere RSI ~ 50 (neutro/apropriado)
- Bot entra em trades conforme confluência

### Cenário: Tem Long em tendência alta

**Antes**:
- Se RSI salta para 80, bot aguarda só confluência simples
- Sem decisão de apertar o stop

**Depois**:
- Strategy detecta posição LONG + lucro > 1.5%
- Retorna "UPDATE_STOP_LOSS"
- Monitor local aperta trailing stop

---

## 🚀 Como Testar

1. **Syntax Check**:
   ```bash
   cd crypto_agent_v1
   python -m py_compile src/agents/optimizer.py src/bot_v2.py
   ```

2. **Start Bot**:
   ```bash
   set PYTHONPATH=%CD%
   python -u -m src.bot_v2
   ```

3. **Monitorar Output**:
   - Ciclo 1: Log "[AI Tuner: Verificando calibração (foco em candles recentes)]"
   - Cada ciclo: "[🧠 Decisão Estratégica Final: BUY/SELL/FLIP_TO_SHORT/...]"

---

## 📝 Resumo Arquitetural

| Arquivo | Mudança | Impacto |
|---------|---------|--------|
| `optimizer.py` | Peso recente + janela 72 candles | Evita overfitting em eventos passados |
| `bot_v2.py` | Integra `Strategy` + trata FLIP/UPDATE | Decisões sofisticadas + posição inteligente |
| `super_strategy.py` | ✅ Já pronto (não alterado) | Lógica técnica + gerenciamento de posição |
| `config.yaml` | ✅ Parâmetros existem | Tuner modifica; strategy relê automaticamente |

---

**Validação**: Código compilado ✅ | Imports resolvidos ✅ | Fluxo de reinst. strategy ✅

