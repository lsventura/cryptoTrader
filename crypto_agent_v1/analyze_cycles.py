#!/usr/bin/env python3
"""
Script para analisar logs de ciclos do bot
Fornece estatísticas sobre trades, P&L, sentimentos e decisões
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path

CYCLES_LOG = Path(__file__).parent / 'src' / '..' / 'logs' / 'cycles.jsonl'

def load_cycles():
    """Carrega todos os ciclos do arquivo JSONL"""
    cycles = []
    try:
        with open(CYCLES_LOG, 'r') as f:
            for line in f:
                if line.strip():
                    cycles.append(json.loads(line))
    except FileNotFoundError:
        print(f"❌ Arquivo {CYCLES_LOG} não encontrado")
        return None
    
    return pd.DataFrame(cycles) if cycles else None

def print_summary(df):
    """Exibe resumo geral dos ciclos"""
    print("\n" + "="*80)
    print("📊 RESUMO GERAL DOS CICLOS")
    print("="*80)
    
    print(f"\n📈 Total de ciclos: {len(df)}")
    print(f"⏱️ Período: {df['timestamp'].iloc[0]} até {df['timestamp'].iloc[-1]}")
    
    # Distribuição de sentimentos
    print(f"\n🎯 Distribuição de Sentimentos:")
    print(df['sentiment'].value_counts().to_string())
    
    # Distribuição de decisões
    print(f"\n🔄 Distribuição de Decisões:")
    print(df['decision'].value_counts().to_string())
    
    # Estatísticas de posições
    has_pos = df['has_position'].sum()
    print(f"\n💼 Posições Abertas: {has_pos} ciclos ({has_pos/len(df)*100:.1f}%)")
    
    # P&L quando há posição
    pnl_cycles = df[df['pnl'].notna()]
    if len(pnl_cycles) > 0:
        print(f"\n💰 P&L Stats (apenas ciclos com posição):")
        pnl_usdt = pnl_cycles['pnl'].apply(lambda x: x['usdt'] if x else 0)
        pnl_pct = pnl_cycles['pnl'].apply(lambda x: x['pct'] if x else 0)
        
        print(f"   P&L USDT - Min: ${pnl_usdt.min():.2f}, Max: ${pnl_usdt.max():.2f}, Média: ${pnl_usdt.mean():.2f}")
        print(f"   P&L %   - Min: {pnl_pct.min():.2f}%, Max: {pnl_pct.max():.2f}%, Média: {pnl_pct.mean():.2f}%")
        print(f"   Ciclos em LUCRO: {(pnl_usdt > 0).sum()} ({(pnl_usdt > 0).sum()/len(pnl_cycles)*100:.1f}%)")
        print(f"   Ciclos em PREJUÍZO: {(pnl_usdt < 0).sum()} ({(pnl_usdt < 0).sum()/len(pnl_cycles)*100:.1f}%)")

def print_recent_cycles(df, num=10):
    """Exibe últimos N ciclos em detalhe"""
    print("\n" + "="*80)
    print(f"🔍 ÚLTIMOS {min(num, len(df))} CICLOS")
    print("="*80)
    
    recent = df.tail(num).sort_index(ascending=False)
    
    for idx, row in recent.iterrows():
        timestamp = row['timestamp']
        cycle = row['cycle']
        sentiment = row['sentiment']
        decision = row['decision']
        price = f"${row['price']:,.2f}" if row['price'] else "N/A"
        
        print(f"\n[Ciclo {cycle}] {timestamp}")
        print(f"  Sentimento: {sentiment} | Decisão: {decision}")
        print(f"  Preço: {price}")
        
        if row['has_position'] and row['pnl']:
            pnl = row['pnl']
            status = "📈 LUCRO" if pnl['usdt'] >= 0 else "📉 PREJUÍZO"
            print(f"  {status}: ${pnl['usdt']:+.2f} ({pnl['pct']:+.2f}%)")

def export_csv(df, output_path=None):
    """Exporta dados para CSV"""
    if output_path is None:
        output_path = Path(__file__).parent / 'logs' / 'cycles_export.csv'
    
    # Flatena a coluna 'pnl' (que é dict)
    df_export = df.copy()
    if 'pnl' in df_export.columns:
        pnl_expanded = pd.json_normalize(df_export['pnl'].apply(lambda x: x if x else {}))
        pnl_expanded.columns = ['pnl_' + col for col in pnl_expanded.columns]
        df_export = pd.concat([df_export.drop('pnl', axis=1), pnl_expanded], axis=1)
    
    df_export.to_csv(output_path, index=False)
    print(f"\n✅ Dados exportados para {output_path}")

if __name__ == '__main__':
    print("🤖 Carregando logs de ciclos...")
    df = load_cycles()
    
    if df is None or len(df) == 0:
        print("❌ Nenhum ciclo registrado ainda")
        exit(1)
    
    print_summary(df)
    print_recent_cycles(df, num=10)
    export_csv(df)
    
    print("\n" + "="*80)
    print("✅ Análise concluída!")
    print("="*80)
