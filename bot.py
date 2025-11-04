import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re
import os  # Para variables de entorno en Render

# Logging para depurar (verás en logs de Render)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Conexión a Google Sheets (usa creds.json o env vars en Render)
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)  # O usa os.environ['GOOGLE_CREDS']
client = gspread.authorize(creds)
sheet = client.open("Gastos").sheet1  # Ajusta el nombre de tu sheet

async def start(update: Update, context):
    await update.message.reply_text('¡Hola! Envía "Gasto [monto] en [categoría]" para registrar.')

async def resumen(update: Update, context):
    data = sheet.get_all_values()
    total = sum(float(row[1]) for row in data[1:] if row and row[1].isdigit())  # Suma montos
    await update.message.reply_text(f'Total de gastos: {total}')

async def handle_message(update: Update, context):
    logger.info(f"Mensaje recibido: {update.message.text}")  # Log para depurar
    text = update.message.text.lower()
    match = re.match(r'gasto\s*(\d+)\s*en\s*(\w+)', text)
    if match:
        monto = match.group(1)
        categoria = match.group(2)
        fecha = datetime.now().strftime('%Y-%m-%d')
        sheet.append_row([fecha, monto, categoria])
        await update.message.reply_text(f'Registrado: {monto} en {categoria} el {fecha}')
    else:
        await update.message.reply_text('Formato inválido. Ej: "Gasto 300 en luz"')

def main():
    TOKEN = os.environ['BOT_TOKEN']  # Usa env var en Render para seguridad
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('resumen', resumen))
    # Agrega este handler para textos no-comando
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Webhook para Render
    application.run_webhook(listen='0.0.0.0', port=int(os.environ.get('PORT', 8443)), url_path=TOKEN, webhook_url=f'https://tu-bot.onrender.com/{TOKEN}')

if __name__ == '__main__':
    main()
