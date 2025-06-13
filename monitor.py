import requests
from bs4 import BeautifulSoup
import re
import os

# Prezzi di riferimento
PREZZO_ATTUALE_LUCE = 0.1232
PREZZO_ATTUALE_GAS = 0.453

# Token e chat_id di Telegram dalle variabili d'ambiente
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

def estrai_prezzi():
    url = 'https://octopusenergy.it/le-nostre-tariffe'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Trova la sezione "Octopus Fissa 12M"
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    sezione_fissa = None
    for tag in headings:
        if 'Octopus Fissa 12M' in tag.get_text():
            sezione_fissa = tag
            break

    if not sezione_fissa:
        raise ValueError("Sezione 'Octopus Fissa 12M' non trovata.")

    contenitore = sezione_fissa.find_next('div')
    if not contenitore:
        raise ValueError("Contenitore dettagli tariffa non trovato.")

    testo = contenitore.get_text()
    print("DEBUG: Contenitore testo:")
    print(testo)

    # Parsing dei prezzi con regex
    prezzo_luce = re.search(r'Materia prima:([0-9.,]+)\s*€/kWh', testo)
    prezzo_gas = re.search(r'Materia prima:([0-9.,]+)\s*€/Smc', testo)

    if not prezzo_luce or not prezzo_gas:
        raise ValueError("Prezzi non trovati nella sezione.")

    prezzo_luce_val = float(prezzo_luce.group(1).replace(',', '.'))
    prezzo_gas_val = float(prezzo_gas.group(1).replace(',', '.'))

    return prezzo_luce_val, prezzo_gas_val

def invia_messaggio_test():
    print("DEBUG: Invio messaggio di test")
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ TELEGRAM_TOKEN o CHAT_ID mancanti.")
        return
    test_message = "🔔 TEST: Il bot è attivo e funzionante. Questo è un messaggio di prova."
    response = requests.post(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
        data={'chat_id': CHAT_ID, 'text': test_message}
    )
    print(f"DEBUG: Response Telegram: {response.status_code} - {response.text}")

# Controllo prezzi e test invio Telegram
try:
    prezzo_luce, prezzo_gas = estrai_prezzi()
    messaggi = []

    if prezzo_luce < PREZZO_ATTUALE_LUCE:
        messaggi.append(f"💡 Prezzo luce sceso a {prezzo_luce:.4f} €/kWh!")

    if prezzo_gas < PREZZO_ATTUALE_GAS:
        messaggi.append(f"🔥 Prezzo gas sceso a {prezzo_gas:.4f} €/Smc!")

    print(f"DEBUG: Prezzo luce: {prezzo_luce}, Prezzo gas: {prezzo_gas}")
    print(f"DEBUG: TELEGRAM_TOKEN presente: {bool(TELEGRAM_TOKEN)}")
    print(f"DEBUG: CHAT_ID presente: {bool(CHAT_ID)}")
    print(f"DEBUG: Messaggi da inviare: {messaggi}")

    # Invia il messaggio di test indipendentemente dai prezzi
    invia_messaggio_test()

except Exception as e:
    print(f"❌ Errore durante l'esecuzione dello script: {e}")
