# telegram_listener.py
import os
import json
import re
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =======================
# Config base e costanti
# =======================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("octopus-telegram-listener")

SOG_PATH = os.path.join(os.path.dirname(__file__), "soglie.json")

ASK_BOTH, ASK_LUCE, ASK_GAS = range(3)


# =======================
# Funzioni utilità soglie
# =======================

def _default_payload():
    return {
        "users": {},
        "default": {
            "luce": {"price": 0.25, "unit": "€/kWh"},
            "gas":  {"price": 0.90, "unit": "€/Smc"}
        }
    }

def load_thresholds():
    if not os.path.exists(SOG_PATH):
        return _default_payload()
    with open(SOG_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # se corrotto, riparti da default (e non sovrascrivere subito)
            logger.error("soglie.json non valido: uso default in memoria.")
            return _default_payload()

def save_thresholds(data):
    with open(SOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_defaults(chat_id: int):
    data = load_thresholds()
    users = data.get("users", {})
    return users.get(str(chat_id), data["default"])

def set_user_defaults(chat_id: int, luce: Optional[float] = None, gas: Optional[float] = None):
    data = load_thresholds()
    data.setdefault("users", {})
    cur = data["users"].get(str(chat_id), {
        "luce": {"price": data["default"]["luce"]["price"], "unit": "€/kWh"},
        "gas":  {"price": data["default"]["gas"]["price"],  "unit": "€/Smc"}
    })
    if luce is not None:
        cur["luce"]["price"] = float(luce)
        cur["luce"]["unit"] = "€/kWh"
    if gas is not None:
        cur["gas"]["price"] = float(gas)
        cur["gas"]["unit"] = "€/Smc"

    data["users"][str(chat_id)] = cur
    save_thresholds(data)
    return cur


# =======================
# Parsing numeri
# =======================

def _parse_price(s: str) -> Optional[float]:
    """
    Accetta '0.25', '0,25', '0,25 €/kWh', ecc. Ritorna float o None.
    """
    m = re.findall(r"[\d\.,]+", s or "")
    if not m:
        return None
    try:
        return float(m[0].replace(",", "."))
    except ValueError:
        return None


# =======================
# Handlers bot
# =======================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cur = get_user_defaults(chat_id)
    msg = [
        "Ciao! 👋 Questo bot salva i tuoi prezzi **Luce** e **Gas** e li userà nel monitor giornaliero.",
        "",
        "I tuoi valori correnti:",
        f"• Luce: {cur['luce']['price']:.4f} {cur['luce']['unit']}",
        f"• Gas:  {cur['gas']['price']:.4f} {cur['gas']['unit']}",
        "",
        "Comandi utili:",
        "• /configura  – imposta i prezzi (anche in un solo messaggio)",
        "• /miesoglie – mostra i tuoi valori salvati",
        "• /luce 0,25  – imposta solo la luce",
        "• /gas 0,90   – imposta solo il gas",
    ]
    await update.message.reply_text("\n".join(msg))

async def cmd_miesoglie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cur = get_user_defaults(chat_id)
    await update.message.reply_text(
        f"Tuoi valori salvati:\n"
        f"• Luce: {cur['luce']['price']:.4f} {cur['luce']['unit']}\n"
        f"• Gas:  {cur['gas']['price']:.4f} {cur['gas']['unit']}"
    )

# --- configurazione guidata ---

async def cmd_configura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("Imposta LUCE+GAS insieme", callback_data="both")],
        [InlineKeyboardButton("Solo LUCE", callback_data="luce"),
         InlineKeyboardButton("Solo GAS",  callback_data="gas")],
    ]
    await update.message.reply_text(
        "Vuoi impostare i tuoi prezzi?\n"
        "• LUCE+GAS insieme in un solo messaggio (es: 0,25 0,90)\n"
        "• Oppure solo uno dei due",
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "both":
        await q.edit_message_text(
            "Inserisci LUCE e GAS (in quest’ordine) nello stesso messaggio.\n"
            "Esempi validi:\n"
            "• 0,25 0,90\n"
            "• 0.25, 0.90\n"
            "• 0,27€/kWh 0,88€/Smc"
        )
        return ASK_BOTH
    if q.data == "luce":
        await q.edit_message_text("Inserisci il tuo prezzo LUCE (€/kWh), es: 0,25")
        return ASK_LUCE
    if q.data == "gas":
        await q.edit_message_text("Inserisci il tuo prezzo GAS (€/Smc), es: 0,90")
        return ASK_GAS

async def handle_both(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    nums = re.findall(r"[\d\.,]+", (update.message.text or ""))
    if len(nums) < 2:
        await update.message.reply_text("Non ho trovato due numeri. Riprova (es: 0,25 0,90).")
        return ASK_BOTH
    luce = _parse_price(nums[0])
    gas = _parse_price(nums[1])
    if luce is None or gas is None:
        await update.message.reply_text("Formato non valido. Riprova (es: 0,25 0,90).")
        return ASK_BOTH
    cur = set_user_defaults(chat_id, luce=luce, gas=gas)
    await update.message.reply_text(
        f"Salvato ✅\nLuce: {cur['luce']['price']:.4f} €/kWh\nGas:  {cur['gas']['price']:.4f} €/Smc"
    )
    return ConversationHandler.END

async def handle_luce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    luce = _parse_price(update.message.text or "")
    if luce is None:
        await update.message.reply_text("Numero non valido. Esempio: 0,25")
        return ASK_LUCE
    cur = set_user_defaults(chat_id, luce=luce)
    await update.message.reply_text(
        f"Salvato ✅\nLuce: {cur['luce']['price']:.4f} €/kWh\nGas attuale: {cur['gas']['price']:.4f} €/Smc"
    )
    return ConversationHandler.END

async def handle_gas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    gas = _parse_price(update.message.text or "")
    if gas is None:
        await update.message.reply_text("Numero non valido. Esempio: 0,90")
        return ASK_GAS
    cur = set_user_defaults(chat_id, gas=gas)
    await update.message.reply_text(
        f"Salvato ✅\nGas: {cur['gas']['price']:.4f} €/Smc\nLuce attuale: {cur['luce']['price']:.4f} €/kWh"
    )
    return ConversationHandler.END

# --- comandi rapidi /luce e /gas ---

async def cmd_luce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Uso: /luce 0,25")
    v = _parse_price(" ".join(context.args))
    if v is None:
        return await update.message.reply_text("Numero non valido. Esempio: /luce 0,25")
    cur = set_user_defaults(update.effective_chat.id, luce=v)
    await update.message.reply_text(f"Luce salvata: {cur['luce']['price']:.4f} €/kWh")

async def cmd_gas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Uso: /gas 0,90")
    v = _parse_price(" ".join(context.args))
    if v is None:
        return await update.message.reply_text("Numero non valido. Esempio: /gas 0,90")
    cur = set_user_defaults(update.effective_chat.id, gas=v)
    await update.message.reply_text(f"Gas salvato: {cur['gas']['price']:.4f} €/Smc")


# =======================
# Bootstrap applicazione
# =======================

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Imposta la variabile d'ambiente TELEGRAM_BOT_TOKEN con il token del bot.")

    application = Application.builder().token(token).build()

    # comandi base
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("miesoglie", cmd_miesoglie))
    application.add_handler(CommandHandler("configura", cmd_configura))
    application.add_handler(CommandHandler("luce", cmd_luce))
    application.add_handler(CommandHandler("gas", cmd_gas))

    # conversation per l’inserimento guidato
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(on_choice, pattern="^(both|luce|gas)$")],
        states={
            ASK_BOTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_both)],
            ASK_LUCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_luce)],
            ASK_GAS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gas)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    application.add_handler(conv)

    logger.info("Bot in esecuzione (polling).")
    application.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
