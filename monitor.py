import requests
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime, timedelta

# Prezzi soglia (modificabili via GitHub secrets in futuro)
PREZZO_ATTUALE_LUCE = float(os.getenv('PREZZO_LUCE', 0.1232))
PREZZO_ATTUALE_GAS = float(os.getenv('PREZZO_GAS', 0.453))

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
STORICO_FILE = 'storico_prezzi.json'

oggi = datetime.now().strftime('%Y-%m-%d')

def estrai_prezzi():
    url = 'https://octopusenergy.it/le-nostre-tariffe'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    sezione_fissa = next((tag for tag in headings if 'Octopus Fissa 12M' in tag.get_text()), None)

    if not sezione_fissa:
        raise ValueError("Sezione 'Octopus Fissa 12M' non trovata.")
    contenitore = sezione_fissa.find_next('div')
    testo = contenitore.get_text()

    prezzo_luce = re.search(r'Materia prima:([0-9.,]+)\s*€/kWh', testo)
    prezzo_gas = re.search(r'Materia prima:([0-9.,]+)\s*€/Smc', testo)

    if not prezzo_luce or not prezzo_gas:
        raise ValueError("Prezzi non trovati nella sezione.")

    return float(prezzo_luce.group(1).replace(',', '.')), float(prezzo_gas.group(1).replace(',', '.'))

def invia_telegram(msg):
    if TELEGRAM_TOKEN and CHAT_ID:
        res = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            data={'chat_id': CHAT_ID, 'text': msg}
        )
        print(f"DEBUG: Telegram response: {res.status_code} - {res.text}")

def salva_storico(data):
    if os.path.exists(STORICO_FILE):
        with open(STORICO_FILE, 'r') as f:
            storico = json.load(f)
    else:
        storico = {'luce': {}, 'gas': {}}

    storico['luce'][oggi] = data['luce']
    storico['gas'][oggi] = data['gas']

    with open(STORICO_FILE, 'w') as f:
        json.dump(storico, f)

def riepilogo_settimanale(storico, tipo):
    dati = storico[tipo]
    ultimi_7 = sorted(dati.items())[-7:]
    testo = f"📊 Riepilogo settimanale prezzi {tipo}\n"
    for data, prezzo in ultimi_7:
        testo += f"{data}: {prezzo:.4f} €/{'kWh' if tipo == 'luce' else 'Smc'}\n"

    if len(ultimi_7) >= 2:
        inizio = ultimi_7[0][1]
        fine = ultimi_7[-1][1]
        var_pct = ((fine - inizio) / inizio) * 100
        testo += f"🔻 Variazione: {var_pct:+.2f}%"
    return testo

# MAIN
try:
    prezzo_luce, prezzo_gas = estrai_prezzi()
    prezzi = {'luce': prezzo_luce, 'gas': prezzo_gas}
    print(f"DEBUG: Prezzi rilevati - Luce: {prezzo_luce}, Gas: {prezzo_gas}")

    salva_storico(prezzi)
    messaggi = []

    if prezzo_luce < PREZZO_ATTUALE_LUCE:
        messaggi.append(f"💡 Prezzo luce sceso a {prezzo_luce:.4f} €/kWh!")

    if prezzo_gas < PREZZO_ATTUALE_GAS:
        messaggi.append(f"🔥 Prezzo gas sceso a {prezzo_gas:.4f} €/Smc!")

    if messaggi:
        for msg in messaggi:
            invia_telegram(msg)
    elif datetime.now().weekday() == 0:  # Solo lunedì
        with open(STORICO_FILE, 'r') as f:
            storico = json.load(f)
        invia_telegram(riepilogo_settimanale(storico, 'luce'))
        invia_telegram(riepilogo_settimanale(storico, 'gas'))

except Exception as e:
    print(f"❌ Errore durante l'esecuzione: {e}")
