import os
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

SOGLIE_FILE = 'soglie.json'

def salva_soglia(tipo, valore):
    if os.path.exists(SOGLIE_FILE):
        with open(SOGLIE_FILE, 'r') as f:
            soglie = json.load(f)
    else:
        soglie = {"luce": 0.1232, "gas": 0.453}
    soglie[tipo] = valore
    with open(SOGLIE_FILE, 'w') as f:
        json.dump(soglie, f)

async def prezzo_luce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valore = float(context.args[0])
        salva_soglia("luce", valore)
        await update.message.reply_text(f"✅ Soglia luce aggiornata a {valore} €/kWh")
    except:
        await update.message.reply_text("❌ Usa: /prezzo_luce 0.1234")

async def prezzo_gas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        valore = float(context.args[0])
        salva_soglia("gas", valore)
        await update.message.reply_text(f"✅ Soglia gas aggiornata a {valore} €/Smc")
    except:
        await update.message.reply_text("❌ Usa: /prezzo_gas 0.453")

if __name__ == '__main__':
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("prezzo_luce", prezzo_luce))
    app.add_handler(CommandHandler("prezzo_gas", prezzo_gas))
    print("🔄 Bot in ascolto... Premi Ctrl+C per interrompere.")
    app.run_polling()
