# monitor.py  — MONITOR_VERSION: v2.2 (alert se uno sotto soglia + esito vs ultimo)
import requests
from bs4 import BeautifulSoup
import re
import os
import json
from datetime import datetime

# Preferisce TELEGRAM_BOT_TOKEN; altrimenti TELEGRAM_TOKEN (compatibilità)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
CHAT_ID_ENV = os.getenv("CHAT_ID")  # fallback opzionale per vecchio formato
STORICO_FILE = "storico_prezzi.json"
SOGLIE_FILE = "soglie.json"

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
    """
    Supporta:
    - Nuovo formato con users/default
    - Vecchio formato piatto {luce: float, gas: float} (richiede CHAT_ID)
    Ritorna (users_dict, default_dict)
    """
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

def _last_value_before(storico_dict: dict, today_key: str):
    # ritorna (data, valore) della rilevazione precedente, o (None, None)
    keys = sorted(k for k in storico_dict.keys() if k < today_key)
    if not keys:
        return None, None
    last_key = keys[-1]
    return last_key, storico_dict[last_key]

def build_esito_vs_ultimo(storico, prezzo_luce, prezzo_gas, tol=1e-6):
    # calcola lo stato vs ultima rilevazione (invariato / ↑ / ↓ + %)
    _, last_luce = _last_value_before(storico.get("luce", {}), oggi)
    _, last_gas  = _last_value_before(storico.get("gas",  {}), oggi)

    def one(val_now, val_prev, unit):
        if val_prev is None:
            return f"n/d {unit}"
        if abs(val_now - val_prev) <= tol:
            return f"invariato {unit}"
        if val_prev == 0:
            # niente percentuale se precedente=0
            arrow = "↑" if val_now > val_prev else "↓"
            return f"{arrow} {val_now:.4f} {unit}"
        delta_pct = (val_now - val_prev) / val_prev * 100
        arrow = "↑" if delta_pct > 0 else "↓"
        return f"{arrow} {abs(delta_pct):.2f}%"

    luce_esito = one(prezzo_luce, last_luce, "€/kWh")
    gas_esito  = one(prezzo_gas,  last_gas,  "€/Smc")
    # Stringa riassuntiva
    return f"Esito vs ultima rilevazione → 💡 {luce_esito} · 🔥 {gas_esito}"


# ---------------- MAIN ----------------

def main():
    print(">>> MONITOR_VERSION v2.2 avviato")
    print(f"Env: has TELEGRAM_TOKEN? {'yes' if TELEGRAM_TOKEN else 'no'}; CHAT_ID set? {'yes' if CHAT_ID_ENV else 'no'}")

    try:
        raw = carica_soglie_raw()
        users, default_cfg = normalizza_soglie(raw)

        # Se non ci sono users ma hai CHAT_ID_ENV, crea un utente fallback
        if (not users) and CHAT_ID_ENV:
            users = {
                str(int(CHAT_ID_ENV)): {
                    "luce": {"price": default_cfg["luce"]["price"], "unit": "€/kWh"},
                    "gas":  {"price": default_cfg["gas"]["price"],  "unit": "€/Smc"},
                }
            }

        prezzo_luce, prezzo_gas = estrai_prezzi()
        print(f"Prezzi attuali - Luce: {prezzo_luce} €/kWh, Gas: {prezzo_gas} €/Smc")

        # Salva nello storico PRIMA del confronto (così oggi è registrato)
        salva_storico({"luce": prezzo_luce, "gas": prezzo_gas})
        storico = carica_storico()
        esito_line = build_esito_vs_ultimo(storico, prezzo_luce, prezzo_gas)

        # Notifiche: inviamo se ALMENO UNO sotto soglia. Aggiungiamo l'esito come riga finale.
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
                        # niente alert → logghiamo comunque l'esito per trasparenza
                        print(esito_line)

                except Exception as e:
                    print(f"Errore su chat_id={chat_id}: {e}")

        # Riepilogo settimanale (lunedì) – invariato rispetto a prima
        if datetime.now().weekday() == 0:
            # nel riepilogo settimanale lasciamo la logica esistente
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

            targets = list(users.keys()) if users else ([CHAT_ID_ENV] if CHAT_ID_ENV else [])
            for cid in targets:
                invia_telegram(cid, riepilogo(storico, "luce"))
                invia_telegram(cid, riepilogo(storico, "gas"))

        print("Controllo completato.")

    except Exception as e:
        print(f"❌ Errore: {e}")


if __name__ == "__main__":
    main()
