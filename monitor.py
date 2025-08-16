# monitor.py
import requests
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime

# ---- Config ----
# Preferisce TELEGRAM_BOT_TOKEN (come nel workflow). Se non c'è, usa TELEGRAM_TOKEN (compatibilità col passato).
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
CHAT_ID_ENV = os.getenv("CHAT_ID")  # usato solo come fallback per vecchio formato
STORICO_FILE = "storico_prezzi.json"
SOGLIE_FILE = "soglie.json"

oggi = datetime.now().strftime("%Y-%m-%d")


# ========== Utilità soglie ==========

def _default_payload():
    return {
        "users": {},
        "default": {
            "luce": {"price": 0.25, "unit": "€/kWh"},
            "gas":  {"price": 0.90, "unit": "€/Smc"},
        },
    }

def carica_soglie_raw():
    """Legge il file soglie così com'è. Se manca o non valido, torna payload di default."""
    if not os.path.exists(SOGLIE_FILE):
        return _default_payload()
    try:
        with open(SOGLIE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default_payload()

def normalizza_soglie(data):
    """
    Supporta due formati:
    1) Nuovo: {"users": {"123": {"luce":{"price":...},"gas":{"price":...}}}, "default": {...}}
    2) Vecchio: {"luce": 0.1232, "gas": 0.453}  -> richiede CHAT_ID nell'env
    Ritorna sempre (users_dict, default_dict)
    """
    # Nuovo formato
    if isinstance(data, dict) and "users" in data and "default" in data:
        users = data.get("users") or {}
        default = data.get("default") or _default_payload()["default"]
        return users, default

    # Vecchio formato piatto
    if isinstance(data, dict) and "luce" in data and "gas" in data:
        # Costruisco users dal CHAT_ID_ENV se presente
        users = {}
        if CHAT_ID_ENV:
            users[str(int(CHAT_ID_ENV))] = {
                "luce": {"price": float(data["luce"]), "unit": "€/kWh"},
                "gas":  {"price": float(data["gas"]),  "unit": "€/Smc"},
            }
        default = _default_payload()["default"]
        return users, default

    # Altrimenti default
    return {}, _default_payload()["default"]


# ========== Estrazione prezzi ==========

def estrai_prezzi():
    """
    Estrae i prezzi luce/gas dalla pagina Octopus (tariffa Fissa 12M).
    Ritorna (prezzo_luce_float, prezzo_gas_float).
    """
    url = "https://octopusenergy.it/le-nostre-tariffe"
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Trova il titolo/sezione "Octopus Fissa 12M"
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    sezione_fissa = next((tag for tag in headings if "Octopus Fissa 12M" in tag.get_text()), None)
    if not sezione_fissa:
        raise ValueError("Sezione 'Octopus Fissa 12M' non trovata nella pagina.")

    # Prende il primo div successivo con testo
    contenitore = sezione_fissa.find_next("div")
    if not contenitore:
        raise ValueError("Contenitore della sezione non trovato.")

    testo = contenitore.get_text(" ", strip=True)

    # Regex robuste per Materia prima
    p_luce = re.search(r"Materia\s+prima:\s*([0-9.,]+)\s*€/kWh", testo, re.IGNORECASE)
    p_gas  = re.search(r"Materia\s+prima:\s*([0-9.,]+)\s*€/Smc", testo, re.IGNORECASE)
    if not p_luce or not p_gas:
        # In alcune versioni della pagina potrebbero cambiare i blocchi; tenta un fallback sull'intera pagina
        full = soup.get_text(" ", strip=True)
        p_luce = p_luce or re.search(r"Materia\s+prima:\s*([0-9.,]+)\s*€/kWh", full, re.IGNORECASE)
        p_gas  = p_gas  or re.search(r"Materia\s+prima:\s*([0-9.,]+)\s*€/Smc",  full, re.IGNORECASE)

    if not p_luce or not p_gas:
        raise ValueError("Prezzi non trovati (pattern cambiato?)")

    prezzo_luce = float(p_luce.group(1).replace(",", "."))
    prezzo_gas  = float(p_gas.group(1).replace(",", "."))
    return prezzo_luce, prezzo_gas


# ========== Telegram & storico ==========

def invia_telegram(chat_id: str, msg: str):
    """Invia un messaggio al chat_id indicato (str o int)."""
    if not TELEGRAM_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": str(chat_id), "text": msg},
            timeout=25,
        )
    except Exception:
        # Non solleva, così il job non fallisce per un singolo invio
        pass

def carica_storico():
    if os.path.exists(STORICO_FILE):
        try:
            with open(STORICO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"luce": {}, "gas": {}}

def salva_storico(d):
    storico = carica_storico()
    storico["luce"][oggi] = d["luce"]
    storico["gas"][oggi] = d["gas"]
    with open(STORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(storico, f, ensure_ascii=False, indent=2)

def riepilogo(storico, tipo):
    dati = storico.get(tipo, {})
    if not dati:
        return f"📊 Riepilogo settimanale {tipo}: nessun dato."
    ultimi = sorted(dati.items())[-7:]
    testo = f"📊 Riepilogo settimanale {tipo}\n"
    for data, val in ultimi:
        testo += f"{data}: {val:.4f} €/{'kWh' if tipo == 'luce' else 'Smc'}\n"
    if len(ultimi) >= 2 and ultimi[0][1] != 0:
        delta = ((ultimi[-1][1] - ultimi[0][1]) / ultimi[0][1]) * 100
        testo += f"📈 Variazione: {delta:+.2f}%"
    return testo


# ========== MAIN ==========

def main():
    try:
        if not TELEGRAM_TOKEN:
            raise RuntimeError("Manca TELEGRAM_BOT_TOKEN (o TELEGRAM_TOKEN) nelle variabili d'ambiente.")

        # 1) carica soglie in qualunque formato e normalizza
        raw = carica_soglie_raw()
        users, default_cfg = normalizza_soglie(raw)

        # Se non ci sono utenti (nuovo formato) ma c'è CHAT_ID_ENV, usiamo il vecchio flusso singolo
        if not users and CHAT_ID_ENV:
            users = {
                str(int(CHAT_ID_ENV)): {
                    "luce": {"price": default_cfg["luce"]["price"], "unit": "€/kWh"},
                    "gas":  {"price": default_cfg["gas"]["price"],  "unit": "€/Smc"},
                }
            }

        # 2) estrai prezzi
        prezzo_luce, prezzo_gas = estrai_prezzi()
        prezzi = {"luce": prezzo_luce, "gas": prezzo_gas}

        # 3) salva storico comune
        salva_storico(prezzi)

        # 4) invia alert per ciascun utente se almeno uno dei due è sotto soglia
        if not isinstance(users, dict) or not users:
            # Nessun utente configurato -> niente invii
            print("Nessun utente configurato in soglie.json -> nessuna notifica.")
        else:
            for chat_id, cfg in users.items():
                try:
                    luce_thr = float(cfg.get("luce", {}).get("price"))
                    gas_thr  = float(cfg.get("gas",  {}).get("price"))
                except Exception:
                    print(f"Voce 'users' non valida per chat_id={chat_id}: {cfg}")
                    continue

                messaggi = []
                if prezzo_luce < luce_thr:
                    messaggi.append(f"💡 Prezzo luce sceso a {prezzo_luce:.4f} €/kWh (soglia: {luce_thr:.4f})")
                if prezzo_gas < gas_thr:
                    messaggi.append(f"🔥 Prezzo gas sceso a {prezzo_gas:.4f} €/Smc (soglia: {gas_thr:.4f})")

                if messaggi:
                    invia_telegram(chat_id, "📢 Prezzi sotto la tua soglia!\n" + "\n".join(messaggi))

        # 5) riepilogo settimanale (lunedì)
        if datetime.now().weekday() == 0:
            storico = carica_storico()
            for chat_id in users.keys() or ([CHAT_ID_ENV] if CHAT_ID_ENV else []):
                invia_telegram(chat_id, riepilogo(storico, "luce"))
                invia_telegram(chat_id, riepilogo(storico, "gas"))

        print("Controllo completato.")

    except Exception as e:
        print(f"❌ Errore: {e}")


if __name__ == "__main__":
    main()
