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

    # Debug: stampa l'intera pagina HTML
    print("DEBUG: Inizio contenuto HTML")
    print(soup.prettify())
    print("DEBUG: Fine contenuto HTML")

    # Debug: stampa tutti gli h2 trovati
    h2_tags = soup.find_all('h2')
    print("DEBUG: Trovati h2:", len(h2_tags))
    for idx, h2 in enumerate(h2_tags):
        print(f"h2[{idx}]: {h2.get_text()}")

    # Prova a trovare la sezione "Octopus Fissa 12M"
    sezione_fissa = None
    for h2 in h2_tags:
        if 'Octopus Fissa 12M' in h2.get_text():
            sezione_fissa = h2
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
