import requests
from bs4 import BeautifulSoup
import telegram
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

    # Debug: stampa l'intera pagina HTML (solo le prime 50 righe)
    print("DEBUG: Inizio contenuto HTML (prime 50 righe)")
    lines = soup.prettify().split('\n')
    for i, line in enumerate(lines[:50]):
        print(f"{i+1:02d}: {line}")
    print("DEBUG: Fine contenuto HTML")

    # Debug: stampa tutti gli heading trovati
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    print(f"DEBUG: Trovati {len(headings)} headings totali.")
    for idx, tag in enumerate(headings):
        print(f"heading[{idx}]: {tag.get_text().strip()}")

    # Cerca la sezione "Octopus Fissa 12M" in qualsiasi heading
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

    # Stampa contenuto trovato per debug
    print("DEBUG: Contenitore testo:")
    print(contenitore.get_text())

    # Estraggo prezzi placeholder (li sistemeremo dopo)
    prezzo_luce = 0.12
    prezzo_gas = 0.45

    return prezzo_luce, prezzo_gas

# Controllo prezzi
try:
    prezzo_luce, prezzo_gas = estrai_prezzi()
    messaggi = []

    if prezzo_luce < PREZZO_ATTUALE_LUCE:
        messaggi.append(f"💡 Prezzo luce sceso a {prezzo_luce:.4f} €/kWh!")

    if prezzo_gas < PREZZO_ATTUALE_GAS:
        messaggi.append(f"🔥 Prezzo gas sceso a {prezzo_gas:.4f} €/Smc!")

    # Invio notifica Telegram
    if messaggi and TELEGRAM_TOKEN and CHAT_ID:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        for messaggio in messaggi:
            bot.send_message(chat_id=CHAT_ID, text=messaggio)
except Exception as e:
    print(f"Errore durante l'esecuzione dello script: {e}")
