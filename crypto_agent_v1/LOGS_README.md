# 📊 Sistema de Logging de Ciclos do Bot

## O que é armazenado?

Cada ciclo do bot agora é registrado em **`logs/cycles.jsonl`** com as seguintes informações:

```json
{
  "timestamp": "2026-02-04T02:04:13.598Z",
  "cycle": 1,
  "sentiment": "BULLISH",
  "decision": "BUY",
  "price": 76338.00,
  "has_position": true,
  "pnl": {
    "usdt": 12.50,
    "pct": 2.34,
    "side": "long",
    "entry_price": 76338.00,
    "contracts": 0.003
  },
  "strategy_params": {
    "rsi_buy": 35,
    "rsi_sell": 65,
    "ema_filter": 20
  }
}
```

## Como analisar os dados?

### 1. **Script de Análise Automática**
```bash
python analyze_cycles.py
```

Isso gera:
- 📈 Resumo geral de ciclos
- 📊 Distribuição de sentimentos e decisões
- 💰 Estatísticas de P&L
- 🔍 Últimos 10 ciclos em detalhe
- 📄 Arquivo CSV exportado em `logs/cycles_export.csv`

### 2. **Análise Manual com Pandas**
```python
import pandas as pd
import json

df = pd.read_json('logs/cycles.jsonl', lines=True)

# Visualizar últimos ciclos
print(df.tail(10))

# Ciclos com posição aberta
df_with_pos = df[df['has_position'] == True]
print(df_with_pos[['cycle', 'sentiment', 'decision', 'pnl']])

# P&L médio
print(df_with_pos['pnl'].apply(lambda x: x['usdt'] if x else 0).mean())
```

### 3. **Análise no Jupyter/Excel**
```bash
# Exportar para análise no Excel
python analyze_cycles.py  # Gera cycles_export.csv

# Abrir no Excel:
# 1. Abra logs/cycles_export.csv
# 2. Crie gráficos de P&L ao longo do tempo
# 3. Analise correlação entre sentimentos e decisões
```

## Estrutura do arquivo JSONL

- **JSONL** = JSON Lines (um objeto JSON por linha)
- **Vantagens:**
  - Fácil de processar incrementalmente
  - Não precisa reescrever tudo a cada ciclo
  - Suportado nativamente por pandas
  - Legível como texto

## Exemplos de análise

### Calcular total de lucro/prejuízo
```python
import pandas as pd
df = pd.read_json('logs/cycles.jsonl', lines=True)
total_pnl = df['pnl'].apply(lambda x: x['usdt'] if x else 0).sum()
print(f"P&L Total: ${total_pnl:.2f}")
```

### Sentimento vs Resultado
```python
# Qual sentimento tem maior taxa de lucro?
df['pnl_usdt'] = df['pnl'].apply(lambda x: x['usdt'] if x else 0)
df.groupby('sentiment')['pnl_usdt'].agg(['count', 'sum', 'mean'])
```

### Decisão vs P&L
```python
# Qual decisão tem melhor resultado?
df.groupby('decision')['pnl_usdt'].agg(['count', 'sum', 'mean'])
```

## Limpeza e Reset

Para começar com um novo log (reset):
```bash
# Deletar arquivo antigo
del logs/cycles.jsonl

# Ou simplesmente deixar rodando, os logs novos serão adicionados
```

---

**Nota:** O arquivo `logs/cycles.jsonl` cresce continuamente. Para análise, use sempre `analyze_cycles.py` ou pandas para carregar.
