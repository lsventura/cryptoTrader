from seleniumwire import webdriver  # Importante: seleniumwire, não só selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import json

# Substitua pelo caminho do seu chromedriver se necessário
driver = webdriver.Chrome()

try:
    # Abra o site oficial da Smiles
    driver.get("https://www.smiles.com.br/passagens")

    # Aguarde a página carregar e preencha o formulário de busca
    time.sleep(3)

    # Exemplo: Preencher origem/destino/datas
    # Esses seletores podem mudar, ajuste conforme o site!
    driver.find_element(By.NAME, "airport-origin").send_keys("GRU")
    time.sleep(1)
    driver.find_element(By.NAME, "airport-destination").send_keys("RIO")
    time.sleep(1)
    driver.find_element(By.NAME, "date-depart").send_keys("15/12/2025")
    time.sleep(1)
    driver.find_element(By.NAME, "date-return").send_keys("20/12/2025")
    time.sleep(1)
    driver.find_element(By.CSS_SELECTOR, ".search-flight-button").click()

    # Dê um tempo para todos os requests acontecerem
    time.sleep(10)

    # Pega todos os requests feitos pela página
    requests_json = []
    for request in driver.requests:
        if request.response:
            entry = {
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "payload": request.body.decode('utf-8', errors='ignore') if request.body else None,
                "status_code": request.response.status_code,
                "response_headers": dict(request.response.headers),
            }
            requests_json.append(entry)

    # Salva todos os requests em um arquivo para análise posterior
    with open("requests_smiles.json", "w", encoding="utf-8") as f:
        json.dump(requests_json, f, ensure_ascii=False, indent=2)

    print("✅ Requests salvos em 'requests_smiles.json'. Envie esse arquivo para criar o app!")
finally:
    driver.quit()
