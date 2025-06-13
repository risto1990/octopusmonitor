import requests
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
STORICO_FILE = 'storico_prezzi.json'
SOGLIE_FILE = 'soglie.json'

oggi = datetime.now().strftime('%Y-%m-%d')

def carica_soglie():
    if os.path.exists(SOGLIE_FILE):
        with open(SOGLIE_FILE, 'r') as f:
            return json.load(f)
    else:
        soglie_default = {"luce": 0.1232, "gas": 0.453}
        with open(SOGLIE_FILE, 'w') as f:
            json.dump(soglie_default, f)
        return soglie_default

def estrai_prezzi():
    url = 'https://octopusenergy.it/le-nostre-tariffe'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    sezione_fissa = next((tag for tag in headings if 'Octopus Fissa 12M' in tag.get_text()), None)
    if not sezione_fissa:
        raise ValueError("Sezione non trovata.")
    testo = sezione_fissa.find_next('div').get_text()
    p_luce = re.search(r'Materia prima:([0-9.,]+)\s*€/kWh', testo)
    p_gas = re.search(r'Materia prima:([0-9.,]+)\s*€/Smc', testo)
    return float(p_luce.group(1).replace(',', '.')), float(p_gas.group(1).replace(',', '.'))

def invia_telegram(msg):
    if TELEGRAM_TOKEN and CHAT_ID:
        requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                      data={'chat_id': CHAT_ID, 'text': msg})

def salva_storico(d):
    storico = {'luce': {}, 'gas': {}}
    if os.path.exists(STORICO_FILE):
        with open(STORICO_FILE, 'r') as f:
            storico = json.load(f)
    storico['luce'][oggi] = d['luce']
    storico['gas'][oggi] = d['gas']
    with open(STORICO_FILE, 'w') as f:
        json.dump(storico, f)

def riepilogo(storico, tipo):
    dati = storico[tipo]
    ultimi = sorted(dati.items())[-7:]
    testo = f"📊 Riepilogo settimanale {tipo}\n"
    for data, val in ultimi:
        testo += f"{data}: {val:.4f} €/{'kWh' if tipo == 'luce' else 'Smc'}\n"
    if len(ultimi) >= 2:
        delta = ((ultimi[-1][1] - ultimi[0][1]) / ultimi[0][1]) * 100
        testo += f"📈 Variazione: {delta:+.2f}%"
    return testo

# MAIN
try:
    soglie = carica_soglie()
    prezzo_luce, prezzo_gas = estrai_prezzi()
    prezzi = {"luce": prezzo_luce, "gas": prezzo_gas}
    salva_storico(prezzi)

    messaggi = []
    if prezzo_luce < soglie['luce']:
        messaggi.append(f"💡 Prezzo luce sceso a {prezzo_luce:.4f} €/kWh!")
    if prezzo_gas < soglie['gas']:
        messaggi.append(f"🔥 Prezzo gas sceso a {prezzo_gas:.4f} €/Smc!")

    if messaggi:
        for msg in messaggi:
            invia_telegram(msg)
    elif datetime.now().weekday() == 0:
        with open(STORICO_FILE, 'r') as f:
            storico = json.load(f)
        invia_telegram(riepilogo(storico, "luce"))
        invia_telegram(riepilogo(storico, "gas"))

except Exception as e:
    print(f"❌ Errore: {e}")
