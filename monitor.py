import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import Bot

STATE_FILE = "last_state.json"
USERS_FILE = "soglie.json"
VERSION = "v2.4"

def carica_utenti():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def salva_utenti(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def carica_stato():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def salva_stato(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def fetch_prezzi():
    url = "https://www.prezzoenergia.it/"
    resp = requests.get(url, timeout=20)
    soup = BeautifulSoup(resp.text, "lxml")

    luce_elem = soup.find("span", {"id": "luce_prezzo"})
    gas_elem = soup.find("span", {"id": "gas_prezzo"})

    luce = float(luce_elem.text.strip().replace(",", "."))
    gas = float(gas_elem.text.strip().replace(",", "."))
    return luce, gas

def invia_telegram(chat_id, text):
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("❌ Errore: manca TELEGRAM_TOKEN")
        return
    try:
        bot = Bot(token=token)
        bot.send_message(chat_id=chat_id, text=text)
        print(f"✔ Notifica inviata a {chat_id}")
    except Exception as e:
        print(f"❌ Errore invio Telegram: {e}")

def main():
    print(f"\n>>> MONITOR_VERSION {VERSION} avviato")

    token = os.getenv("TELEGRAM_TOKEN")
    if token:
        print("Env: has TELEGRAM_TOKEN? yes; CHAT_ID set? yes")
    else:
        print("Env: has TELEGRAM_TOKEN? no")

    # === CARICA STATO PRECEDENTE ===
    last_state = carica_stato()

    # === PREZZI CORRENTI ===
    prezzo_luce, prezzo_gas = fetch_prezzi()
    print(f"Prezzi attuali - Luce: {prezzo_luce:.4f} €/kWh, Gas: {prezzo_gas:.2f} €/Smc")

    # === ESITO VARIAZIONE ===
    if last_state:
        diff_luce = prezzo_luce - last_state["luce"]
        diff_gas = prezzo_gas - last_state["gas"]

        if diff_luce == 0:
            luce_esito = "💡 invariato €/kWh"
        elif diff_luce < 0:
            luce_esito = f"💡 -{abs(diff_luce):.4f} €/kWh"
        else:
            luce_esito = f"💡 +{diff_luce:.4f} €/kWh"

        if diff_gas == 0:
            gas_esito = "🔥 invariato €/Smc"
        elif diff_gas < 0:
            gas_esito = f"🔥 -{abs(diff_gas):.4f} €/Smc"
        else:
            gas_esito = f"🔥 +{diff_gas:.4f} €/Smc"

        esito_line = f"Esito vs ultima run → {luce_esito} · {gas_esito}"
        print(esito_line)
    else:
        esito_line = "Prima rilevazione: nessun confronto disponibile."
        print(esito_line)

    # === NOTIFICHE A TUTTI GLI UTENTI ===
    users = carica_utenti()
    for chat_id, cfg in users.items():
        luce_thr = cfg.get("luce", 9999)
        gas_thr = cfg.get("gas", 9999)

        lines = []
        if prezzo_luce < luce_thr:
            lines.append(f"💡 Luce: {prezzo_luce:.4f} €/kWh (soglia: {luce_thr:.4f})")
        if prezzo_gas < gas_thr:
            lines.append(f"🔥 Gas:  {prezzo_gas:.4f} €/Smc (soglia: {gas_thr:.4f})")

        if lines:
            # ALERT: sotto soglia
            text = (
                "📢 Prezzi sotto la tua soglia!\n"
                + "\n".join(lines)
                + "\n\n"
                + esito_line
            )
        else:
            # DAILY UPDATE: sempre, anche se invariati o saliti
            text = (
                "📬 Aggiornamento quotidiano\n"
                f"💡 Luce: {prezzo_luce:.4f} €/kWh (soglia: {luce_thr:.4f})\n"
                f"🔥 Gas:  {prezzo_gas:.4f} €/Smc (soglia: {gas_thr:.4f})\n\n"
                + esito_line
            )

        invia_telegram(chat_id, text)

    # === SALVA STATO ===
    salva_stato({
        "luce": prezzo_luce,
        "gas": prezzo_gas,
        "timestamp": datetime.now().isoformat()
    })

    print("Controllo completato.")

if __name__ == "__main__":
    main()
