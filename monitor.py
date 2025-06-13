import requests
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
STORICO_FILE = 'storico_prezzi.json'

# Per test forzato
oggi = "2025-06-16"  # lunedì
PREZZO_ATTUALE_LUCE = 0.1232
PREZZO_ATTUALE_GAS = 0.453

def invia_telegram(msg):
    if TELEGRAM_TOKEN and CHAT_ID:
        res = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            data={'chat_id': CHAT_ID, 'text': msg}
        )
        print(f"DEBUG: Telegram response: {res.status_code} - {res.text}")

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

# Crea dati fittizi per test
def genera_storico_fake():
    base_date = datetime.strptime(oggi, '%Y-%m-%d') - timedelta(days=6)
    storico = {'luce': {}, 'gas': {}}
    for i in range(7):
        data = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
        storico['luce'][data] = 0.1250 - i * 0.0003  # leggera discesa
        storico['gas'][data] = 0.4550 - i * 0.0005
    with open(STORICO_FILE, 'w') as f:
        json.dump(storico, f)
    return storico

# MAIN test
try:
    storico = genera_storico_fake()
    invia_telegram(riepilogo_settimanale(storico, 'luce'))
    invia_telegram(riepilogo_settimanale(storico, 'gas'))
except Exception as e:
    print(f"Errore nel test: {e}")
