import logging
import json
import os
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Carga variables de entorno (Render + local)
load_dotenv()

# === CONFIGURACIÓN (usa variables de entorno en Render) ===
TELEGRAM_TOKEN = "8394538839:AAHnQrA698hno7C5APGgXyI7J_aiT3jJ1s8"  # Tu token de Telegram (deja si ya lo tienes)
SHEET_ID = "1IoZEA-RempS9tiybvUmczTOr_ZwWG1W9_-rH22Rp3ak"  # Tu ID de Google Sheet (deja si ya lo tienes)
GROQ_API_KEY = "GROQ_API_KEY"  # Tu clave de GROQ (deja si ya la tienes)
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS")  # JSON completo como string

# === CONEXIÓN A GOOGLE SHEETS ===
scopes = ["https://www.googleapis.com/auth/spreadsheets"]

if GOOGLE_CREDENTIALS_JSON:
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
else:
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)

client_sheets = gspread.authorize(creds)
sheet = client_sheets.open_by_key(SHEET_ID).worksheet("Hoja 1")  # Cambia si tu pestaña es "Gastos"

# === CLIENTE GROQ (compatible con OpenAI) ===
client_groq = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === EXTRAER GASTO DEL MENSAJE ===
def extraer_gasto(texto: str):
    texto = texto.lower().strip()
    monto = None
    categoria = "varios"

    if "pagué" in texto or "pague" in texto:
        partes = re.split(r'\ben\b', texto, 1)
        if len(partes) > 1:
            monto_str = partes[0].replace("pagué", "").replace("pague", "").strip()
            categoria = partes[1].strip()
        else:
            monto_str = partes[0].replace("pagué", "").replace("pague", "").strip()
    elif "gasto" in texto:
        monto_str = texto.replace("gasto", "").strip()
    else:
        return None

    # Extrae número
    match = re.search(r'\d+', monto_str)
    if not match:
        return None
    monto = int(match.group())

    # Limpia categoría
    categoria = re.sub(r'\d+', '', monto_str).strip() or "varios"

    fecha = datetime.now().strftime("%Y-%m-%d")
    return {"monto": monto, "categoria": categoria.title(), "fecha": fecha}

# === GUARDAR EN GOOGLE SHEETS ===
def guardar_en_sheet(monto, categoria, fecha):
    try:
        sheet.append_row([fecha, monto, categoria])
        logger.info(f"Guardado: {fecha} | ${monto} | {categoria}")
        return True
    except Exception as e:
        logger.error(f"Error al guardar: {e}")
        return False

# === COMANDOS DEL BOT ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Soy *GastosHogarBot* (GRATIS)\n\n"
        "Envía:\n"
        "• `Pagué 500 en luz`\n"
        "• `Gasto 200 cafe`\n\n"
        "Comandos:\n"
        "/resumen → Total del mes\n"
        "/categorias → Lista de categorías\n"
        "/actualizar_resumen → Crea pestaña *Resumen*",
        parse_mode='Markdown'
    )

async def handle_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    if not any(p in texto.lower() for p in ["pagué", "pague", "gasto"]):
        return

    datos = extraer_gasto(texto)
    if not datos:
        await update.message.reply_text("No entendí. Usa: `Pagué 500 en luz`", parse_mode='Markdown')
        return

    if guardar_en_sheet(datos["monto"], datos["categoria"], datos["fecha"]):
        await update.message.reply_text(
            f"*Gasto registrado*\n"
            f"💰 `${datos['monto']}`\n"
            f"📂 {datos['categoria']}\n"
            f"📅 {datos['fecha']}",
            parse_mode='Markdown'
        )

# === /resumen ===
async def cmd_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rows = sheet.get_all_values()
        total = 0
        mes = datetime.now().strftime("%Y-%m")
        for row in rows[1:]:
            if len(row) >= 3 and row[0].startswith(mes):
                try:
                    total += int(row[1])
                except:
                    pass
        await update.message.reply_text(f"*Total este mes:*\n💰 `${total}`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text("Error al leer la hoja")

# === /categorias ===
async def cmd_categorias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rows = sheet.get_all_values()
        cats = {row[2].title() for row in rows[1:] if len(row) >= 3}
        if cats:
            lista = "\n".join(f"• {c}" for c in sorted(cats))
            await update.message.reply_text(f"*Categorías usadas:*\n{lista}", parse_mode='Markdown')
        else:
            await update.message.reply_text("Aún no hay gastos")
    except:
        await update.message.reply_text("No hay datos")

# === /actualizar_resumen ===
async def cmd_actualizar_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rows = sheet.get_all_values()
        totals = {}
        for row in rows[1:]:
            if len(row) >= 3:
                cat = row[2].title()
                try:
                    monto = int(row[1])
                    totals[cat] = totals.get(cat, 0) + monto
                except:
                    pass

        # Crea o usa pestaña "Resumen"
        try:
            hoja_resumen = client_sheets.open_by_key(SHEET_ID).worksheet("Resumen")
        except gspread.exceptions.WorksheetNotFound:
            hoja_resumen = client_sheets.open_by_key(SHEET_ID).add_worksheet("Resumen", 100, 3)

        hoja_resumen.clear()
        hoja_resumen.append_row(["Categoría", "Total"])
        for i, (cat, total) in enumerate(sorted(totals.items()), 2):
            hoja_resumen.update(f"A{i}:B{i}", [[cat, total]])

        await update.message.reply_text(f"Resumen actualizado\n{len(totals)} categorías")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# === INICIAR BOT (polling local / webhook en Render) ===
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", cmd_resumen))
    app.add_handler(CommandHandler("categorias", cmd_categorias))
    app.add_handler(CommandHandler("actualizar_resumen", cmd_actualizar_resumen))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_texto))

    print("Bot GastosHogarBot iniciado (GRATIS + 24/7)")

    # === MODO RENDER (WEBHOOK) ===
    if os.getenv('RENDER'):
        port = int(os.environ.get('PORT', 10000))
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{TELEGRAM_TOKEN}"
        )
    # === MODO LOCAL (POLLING) ===
    else:
        app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
