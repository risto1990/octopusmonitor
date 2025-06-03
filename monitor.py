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

    # Trova la sezione della tariffa "Octopus Fissa 12M"
    sezione_fissa = soup.find('h2', string='Octopus Fissa 12M')
    if not sezione_fissa:
        raise ValueError("Sezione 'Octopus Fissa 12M' non trovata.")

    # Trova il contenitore dei dettagli della tariffa
    contenitore = sezione_fissa.find_next('div')
    if not contenitore:
        raise ValueError("Contenitore dettagli tariffa non trovato.")

    # Estrai i prezzi di luce e gas
    testo = contenitore.get_text()
    prezzo_luce = None
    prezzo_gas = None

    for linea in testo.splitlines():
        if 'Materia prima Luce' in linea:
            try:
                prezzo_luce = float(linea.split(':')[1].strip().replace('€/kWh', '').replace(',', '.'))
            except:
                pass
        elif 'Materia prima Gas' in linea:
            try:
                prezzo_gas = float(linea.split(':')[1].strip().replace('€/Smc', '').replace(',', '.'))
            except:
                pass

    if prezzo_luce is None or prezzo_gas is None:
        raise ValueError("Prezzi non trovati nella sezione.")

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
