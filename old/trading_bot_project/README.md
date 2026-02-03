# Projeto de Trading Bot Quantitativo para Futuros de Criptomoedas

Este projeto contém um sistema completo para desenvolver e operar uma estratégia de trading algorítmico.

## Estrutura

- `/models/`: Diretoria onde o modelo de Machine Learning (`.pkl`) e o scaler (`.pkl`) são guardados após o treino.
- `train_model.py`: **(Fase 1)** Script de pesquisa. Use este script para buscar dados históricos, treinar o modelo, fazer backtests e validar a estratégia. A sua execução gera os ficheiros necessários na pasta `/models/`.
- `bot.py`: **(Fase 2)** Script de produção. Este é o bot de trading que opera ao vivo (ou em ambiente de teste). Ele carrega os ficheiros da pasta `/models/` e executa as ordens na exchange.
- `.env`: Ficheiro para armazenar as chaves de API de forma segura.
- `requirements.txt`: Lista de todas as dependências Python do projeto.

## Guia de Início Rápido

1. **Setup do Ambiente:**
   - Crie um ambiente virtual Python: `python -m venv venv`
   - Ative o ambiente: `source venv/bin/activate` (Linux/Mac) ou `venv\Scripts\activate` (Windows)
   - Instale todas as dependências: `pip install -r requirements.txt`

2. **Configurar Chaves de API:**
   - Renomeie o ficheiro `.env.template` para `.env` (se aplicável).
   - Abra o ficheiro `.env` e insira as suas chaves de API da Binance Futures Testnet.

3. **Treinar o Modelo (Fase 1):**
   - Abra o ficheiro `train_model.py`.
   - Ajuste os parâmetros no bloco `if __name__ == '__main__':` conforme desejado (datas, risco, etc.).
   - Execute o script: `python train_model.py`
   - Verifique se o backtest produziu resultados satisfatórios e se os ficheiros `modelo_lgbm.pkl` e `scaler.pkl` foram criados na pasta `/models/`.

4. **Executar o Bot (Fase 2):**
   - Abra o ficheiro `bot.py`.
   - As configurações são carregadas da classe `Config`, ajuste se necessário.
   - Execute o bot: `python bot.py`
   - O bot irá iniciar o seu loop, conectar-se à Binance Testnet e começar a monitorizar o mercado para oportunidades de trading.