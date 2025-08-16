# monitor.py  — MONITOR_VERSION: v2.3
# - Alert se ALMENO uno sotto soglia
# - Esito vs ULTIMA RUN (anche nello stesso giorno) + storico per data

import requests
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime

# Preferisce TELEGRAM_BOT_TOKEN; altrimenti TELEGRAM_TOKEN (compatibilità)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
CHAT_ID_ENV = os.getenv("CHAT_ID")  # fallback opzionale per vecchio formato
STORICO_FILE = "storico_prezzi.json"   # per data (YYYY-MM-DD)
LAST_FILE    = "last_prices.json"      # ultima run (anche stesso giorno)
SOGLIE_FILE  = "soglie.json"

oggi = datetime.now().strftime("%Y-%m-%d")


# ---------------- Soglie ----------------

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
            data = json.load(f)
            return data
    except Exception as e:
        print(f"soglie.json illeggibile ({e}): uso default in memoria.")
        return _default_payload()

def normalizza_soglie(data):
    if isinstance(data, dict) and "users" in data and "default" in data:
        users = data.get("users") or {}
        default = data.get("default") or _default_payload()["default"]
        return users, default
    if isinstance(data, dict) and "luce" in data and "gas" in data:
        users = {}
        if CHAT_ID_ENV:
            users[str(int(CHAT_ID_ENV))] = {
                "luce": {"price": float(data["luce"]), "unit": "€/kWh"},
                "gas":  {"price": float(data["gas"]),  "unit": "€/Smc"},
            }
        return users, _default_payload()["default"]
    return {}, _default_payload()["default"]


# ---------------- Estrazione prezzi ----------------

def estrai_prezzi():
    url = "https://octopusenergy.it/le-nostre-tariffe"
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    sezione_fissa = next((tag for tag in headings if "Octopus Fissa 12M" in tag.get_text()), None)
    if not sezione_fissa:
        raise ValueError("Sezione 'Octopus Fissa 12M' non trovata.")

    contenitore = sezione_fissa.find_next("div")
    if not contenitore:
        raise ValueError("Contenitore della sezione non trovato.")

    testo = contenitore.get_text(" ", strip=True)

    p_luce = re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/kWh", testo, re.IGNORECASE)
    p_gas  = re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/Smc",  testo, re.IGNORECASE)

    if not p_luce or not p_gas:
        full = soup.get_text(" ", strip=True)
        p_luce = p_luce or re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/kWh", full, re.IGNORECASE)
        p_gas  = p_gas  or re.search(r"Materia\s*prima:\s*([0-9.,]+)\s*€/Smc",  full, re.IGNORECASE)

    if not p_luce or not p_gas:
        raise ValueError("Prezzi non trovati (pattern cambiato?).")

    prezzo_luce = float(p_luce.group(1).replace(",", "."))
    prezzo_gas  = float(p_gas.group(1).replace(",", "."))
    return prezzo_luce, prezzo_gas


# ---------------- Telegram & Storico ----------------

def invia_telegram(chat_id: str, msg: str):
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN mancante: salto invio.")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": str(chat_id), "text": msg},
            timeout=25,
        )
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
    storico["luce"][oggi] = d["luce"]
    storico["gas"][oggi] = d["gas"]
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


# ---------------- MAIN ----------------

def main():
    print(">>> MONITOR_VERSION v2.3 avviato")
    print(f"Env: has TELEGRAM_TOKEN? {'yes' if TELEGRAM_TOKEN else 'no'}; CHAT_ID set? {'yes' if CHAT_ID_ENV else 'no'}")

    try:
        raw = carica_soglie_raw()
        users, default_cfg = normalizza_soglie(raw)

        if (not users) and CHAT_ID_ENV:
            users = {
                str(int(CHAT_ID_ENV)): {
                    "luce": {"price": default_cfg["luce"]["price"], "unit": "€/kWh"},
                    "gas":  {"price": default_cfg["gas"]["price"],  "unit": "€/Smc"},
                }
            }

        prezzo_luce, prezzo_gas = estrai_prezzi()
        print(f"Prezzi attuali - Luce: {prezzo_luce} €/kWh, Gas: {prezzo_gas} €/Smc")

        # 1) Carica ultima run e costruisci esito
        last = carica_last()
        esito_line = esito_vs_last(prezzo_luce, prezzo_gas, last)

        # 2) Aggiorna subito LAST per le run successive
        salva_last({"luce": prezzo_luce, "gas": prezzo_gas, "ts": datetime.now().isoformat()})

        # 3) Aggiorna anche lo storico per data (una sola voce al giorno)
        salva_storico({"luce": prezzo_luce, "gas": prezzo_gas})

        # 4) Notifiche: inviamo se ALMENO UNO sotto soglia. Aggiungiamo l'esito come riga finale.
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
                        text = "📢 Prezzi sotto la tua soglia!\n" + "\n".join(lines) + f"\n\n{esito_line}"
                        invia_telegram(chat_id, text)
                    else:
                        print(esito_line)

                except Exception as e:
                    print(f"Errore su chat_id={chat_id}: {e}")

        # 5) Riepilogo settimanale (lunedì) — invariato
        if datetime.now().weekday() == 0:
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

            storico = carica_storico()
            targets = list(users.keys()) if users else ([CHAT_ID_ENV] if CHAT_ID_ENV else [])
            for cid in targets:
                invia_telegram(cid, riepilogo(storico, "luce"))
                invia_telegram(cid, riepilogo(storico, "gas"))

        print("Controllo completato.")

    except Exception as e:
        print(f"❌ Errore: {e}")


if __name__ == "__main__":
    main()
