# monitor.py — MONITOR_VERSION: v2.5
# - Prezzi da octopusenergy.it (tariffa Fissa 12M)
# - Se fetch fallisce: invia avviso agli utenti e termina senza crash
# - Alert se almeno uno sotto soglia, altrimenti aggiornamento quotidiano
# - Confronto vs ULTIMA RUN (last_prices.json) + storico giornaliero

import os
import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Preferisce TELEGRAM_BOT_TOKEN; altrimenti TELEGRAM_TOKEN (compatibilità)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
CHAT_ID_ENV = os.getenv("CHAT_ID")  # fallback opzionale per vecchio formato

SOGLIE_FILE   = "soglie.json"
STORICO_FILE  = "storico_prezzi.json"   # storico per data (YYYY-MM-DD)
LAST_FILE     = "last_prices.json"      # ultima run (anche nello stesso giorno)
OGGI          = datetime.now().strftime("%Y-%m-%d")
HEADERS       = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
}

def _default_payload():
    return {
        "users": {},
        "default": {
            "luce": {"price": 0.25, "unit": "€/kWh"},
            "gas":  {"price": 0.90, "unit": "€/Smc"},
        },
    }

def carica_soglie_raw():
    if not os.path.exists(SOGLIE_FILE):
        print("soglie.json non trovato: uso default in memoria.")
        return _default_payload()
    try:
        with open(SOGLIE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"soglie.json illeggibile ({e}): uso default in memoria.")
        return _default_payload()

def normalizza_soglie(data):
    # Nuovo formato
    if isinstance(data, dict) and "users" in data and "default" in data:
        users = data.get("users") or {}
        default = data.get("default") or _default_payload()["default"]
        return users, default
    # Vecchio formato piatto
    if isinstance(data, dict) and "luce" in data and "gas" in data:
        users = {}
        if CHAT_ID_ENV:
            users[str(int(CHAT_ID_ENV))] = {
                "luce": {"price": float(data["luce"]), "unit": "€/kWh"},
                "gas":  {"price": float(data["gas"]),  "unit": "€/Smc"},
            }
        return users, _default_payload()["default"]
    return {}, _default_payload()["default"]

def estrai_prezzi():
    url = "https://octopusenergy.it/le-nostre-tariffe"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")  # lxml è più robusto

    # Trova la sezione "Octopus Fissa 12M"
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    sezione_fissa = next((tag for tag in headings if "Octopus Fissa 12M" in tag.get_text()), None)
    if not sezione_fissa:
        # fallback: cerca su tutto il testo
        testo_full = soup.get_text(" ", strip=True)
        p_luce = re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/kWh", testo_full, re.I)
        p_gas  = re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/Smc",  testo_full, re.I)
    else:
        contenitore = sezione_fissa.find_next("div")
        testo_blk = (contenitore.get_text(" ", strip=True) if contenitore else "")
        p_luce = re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/kWh", testo_blk, re.I)
        p_gas  = re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/Smc",  testo_blk, re.I)
        if not p_luce or not p_gas:
            # ulteriore fallback su tutta la pagina
            testo_full = soup.get_text(" ", strip=True)
            p_luce = p_luce or re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/kWh", testo_full, re.I)
            p_gas  = p_gas  or re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/Smc",  testo_full, re.I)

    if not p_luce or not p_gas:
        raise ValueError("Prezzi non trovati (probabile cambio HTML/pattern).")

    prezzo_luce = float(p_luce.group(1).replace(",", "."))
    prezzo_gas  = float(p_gas.group(1).replace(",", "."))
    return prezzo_luce, prezzo_gas

def invia_telegram(chat_id: str, text: str):
    token = TELEGRAM_TOKEN
    if not token:
        print("TELEGRAM_TOKEN mancante: salto invio.")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": str(chat_id), "text": text},
            timeout=25,
        )
        if resp.status_code != 200:
            print(f"Invio Telegram non 200 per chat_id={chat_id}: {resp.text}")
    except Exception as e:
        print(f"Invio Telegram fallito per chat_id={chat_id}: {e}")

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
    storico["luce"][OGGI] = d["luce"]
    storico["gas"][OGGI] = d["gas"]
    with open(STORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(storico, f, ensure_ascii=False, indent=2)

def carica_last():
    if os.path.exists(LAST_FILE):
        try:
            with open(LAST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def salva_last(d):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)

def esito_vs_last(prezzo_luce, prezzo_gas, last):
    if not last:
        return "Prima rilevazione: nessun confronto disponibile."
    def one(now, prev, unit):
        if prev is None: return f"n/d {unit}"
        if now == prev: return f"invariato {unit}"
        if prev == 0:   return f"{'↑' if now>prev else '↓'} {now:.4f} {unit}"
        pct = (now - prev) / prev * 100
        arrow = "↑" if pct > 0 else "↓"
        return f"{arrow} {abs(pct):.2f}%"
    luce_esito = one(prezzo_luce, last.get("luce"), "€/kWh")
    gas_esito  = one(prezzo_gas,  last.get("gas"),  "€/Smc")
    return f"Esito vs ultima run → 💡 {luce_esito} · 🔥 {gas_esito}"

def main():
    print(">>> MONITOR_VERSION v2.5 avviato")
    print(f"Env: has TELEGRAM_TOKEN? {'yes' if TELEGRAM_TOKEN else 'no'}; CHAT_ID set? {'yes' if CHAT_ID_ENV else 'no'}")

    raw = carica_soglie_raw()
    users, default_cfg = normalizza_soglie(raw)
    if (not users) and CHAT_ID_ENV:
        users = {
            str(int(CHAT_ID_ENV)): {
                "luce": {"price": default_cfg["luce"]["price"], "unit": "€/kWh"},
                "gas":  {"price": default_cfg["gas"]["price"],  "unit": "€/Smc"},
            }
        }

    # 1) Estrazione prezzi con gestione errore
    try:
        prezzo_luce, prezzo_gas = estrai_prezzi()
        print(f"Prezzi attuali - Luce: {prezzo_luce} €/kWh, Gas: {prezzo_gas} €/Smc")
    except Exception as e:
        print(f"⚠️ Fetch prezzi fallito: {e}")
        # Avvisa tutti gli utenti e termina senza far fallire il job
        if isinstance(users, dict) and users:
            for chat_id in users.keys():
                invia_telegram(
                    chat_id,
                    f"⚠️ Aggiornamento prezzi fallito oggi.\nDettagli: {e}\n"
                    f"Riproverò al prossimo run."
                )
        print("Controllo completato (fallimento fetch).")
        return

    # 2) Confronto vs ultima run + persistenza stato
    last = carica_last()
    esito_line = esito_vs_last(prezzo_luce, prezzo_gas, last)
    salva_last({"luce": prezzo_luce, "gas": prezzo_gas, "ts": datetime.now().isoformat()})
    salva_storico({"luce": prezzo_luce, "gas": prezzo_gas})

    # 3) Notifiche: sempre un messaggio (alert o aggiornamento quotidiano)
    if not isinstance(users, dict) or not users:
        print("Nessun utente configurato -> nessuna notifica.")
    else:
        for chat_id, cfg in users.items():
            try:
                luce_cfg = cfg.get("luce", {})
                gas_cfg  = cfg.get("gas",  {})
                if "price" not in luce_cfg or "price" not in gas_cfg:
                    print(f"Config mancante per chat_id={chat_id}: {cfg}")
                    continue

                luce_thr = float(luce_cfg["price"])
                gas_thr  = float(gas_cfg["price"])

                lines = []
                if prezzo_luce < luce_thr:
                    lines.append(f"💡 Luce: {prezzo_luce:.4f} €/kWh (soglia: {luce_thr:.4f})")
                if prezzo_gas < gas_thr:
                    lines.append(f"🔥 Gas:  {prezzo_gas:.4f} €/Smc (soglia: {gas_thr:.4f})")

                if lines:
                    text = (
                        "📢 Prezzi sotto la tua soglia!\n"
                        + "\n".join(lines)
                        + "\n\n"
                        + esito_line
                    )
                else:
                    text = (
                        "📬 Aggiornamento quotidiano\n"
                        f"💡 Luce: {prezzo_luce:.4f} €/kWh (soglia: {luce_thr:.4f})\n"
                        f"🔥 Gas:  {prezzo_gas:.4f} €/Smc (soglia: {gas_thr:.4f})\n\n"
                        + esito_line
                    )
                invia_telegram(chat_id, text)
            except Exception as e:
                print(f"Errore su chat_id={chat_id}: {e}")

    print("Controllo completato.")

if __name__ == "__main__":
    main()
