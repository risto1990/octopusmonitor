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

# Funzione per estrarre i prezzi dalla pagina (da completare!)
def estrai_prezzi():
    url = 'https://octopusenergy.it/le-nostre-tariffe'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Qui va scritto il parsing dei prezzi reali:
    prezzo_luce = 0.12  # Placeholder
    prezzo_gas = 0.45   # Placeholder

    return prezzo_luce, prezzo_gas

# Controllo prezzi
prezzo_luce, prezzo_gas = estrai_prezzi()
messaggi = []

if prezzo_luce < PREZZO_ATTUALE_LUCE:
    messaggi.append(f"💡 Prezzo luce sceso a {prezzo_luce} €/kWh!")

if prezzo_gas < PREZZO_ATTUALE_GAS:
    messaggi.append(f"🔥 Prezzo gas sceso a {prezzo_gas} €/Smc!")

# Invio notifica Telegram
if messaggi and TELEGRAM_TOKEN and CHAT_ID:
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    for messaggio in messaggi:
        bot.send_message(chat_id=CHAT_ID, text=messaggio)
