import yaml
import time
import traceback
import os
import sys

# Ajusta path para permitir importar do pacote `src` quando executado a partir da raiz do workspace
proj_root = os.path.abspath(os.path.join(os.getcwd(), 'crypto_agent_v1'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from src.tools.execution import execute_trade_v2, close_position

if __name__ == '__main__':
    try:
        cfg_path = os.path.join(proj_root, 'config', 'config.yaml')
        with open(cfg_path, 'r') as f:
            cfg = yaml.safe_load(f)

        print('Iniciando teste V2 na Testnet com sinal BUY...')
        res = execute_trade_v2({'final_decision': 'BUY'}, cfg)
        print('Resultado:', res)

        # Opcional: aguarda 60s para permitir que o monitor local atue (se criado)
        time.sleep(60)
        print('Tentando fechar posição (close_position)...')
        res_close = close_position(cfg)
        print('Fechar resultado:', res_close)

    except Exception as e:
        print('Erro no script:')
        traceback.print_exc()
