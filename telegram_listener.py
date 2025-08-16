import os
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

SOGLIE_FILE = "soglie.json"

def carica_soglie():
    if os.path.exists(SOGLIE_FILE):
        with open(SOGLIE_FILE, "r") as f:
            return json.load(f)
    else:
        soglie_default = {"luce": 0.1232, "gas": 0.453}
        with open(SOGLIE_FILE, "w") as f:
            json.dump(soglie_default, f)
        return soglie_default

def salva_soglie(soglie):
    with open(SOGLIE_FILE, "w") as f:
        json.dump(soglie, f)

# --- HANDLER COMANDI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    soglie = carica_soglie()
    await update.message.reply_text(
        "Ciao! 👋\n"
        "Puoi impostare le tue soglie con:\n"
        " - /setluce <valore>\n"
        " - /setgas <valore>\n"
        " - /soglie per vedere le attuali."
    )

async def soglie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    soglie = carica_soglie()
    await update.message.reply_text(
        f"Soglie correnti:\n💡 Luce: {soglie['luce']} €/kWh\n🔥 Gas: {soglie['gas']} €/Smc"
    )

async def set_luce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    soglie = carica_soglie()
    try:
        nuovo_valore = float(context.args[0])
        soglie["luce"] = nuovo_valore
        salva_soglie(soglie)
        await update.message.reply_text(f"✅ Soglia luce aggiornata a {nuovo_valore} €/kWh")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usa il comando così: /setluce 0.25")

async def set_gas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    soglie = carica_soglie()
    try:
        nuovo_valore = float(context.args[0])
        soglie["gas"] = nuovo_valore
        salva_soglie(soglie)
        await update.message.reply_text(f"✅ Soglia gas aggiornata a {nuovo_valore} €/Smc")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usa il comando così: /setgas 0.90")

# --- MAIN ---
def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("❌ Errore: variabile TELEGRAM_TOKEN non trovata.")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("soglie", soglie))
    app.add_handler(CommandHandler("setluce", set_luce))
    app.add_handler(CommandHandler("setgas", set_gas))

    print("🤖 Bot avviato, in ascolto...")
    app.run_polling()

if __name__ == "__main__":
    main()
