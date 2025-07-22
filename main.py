import os
import json
import logging
import datetime
import asyncio
from dotenv import load_dotenv
from telegram import (
    Update,
    BotCommand,
    Document,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# --- Configuración ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
DATA_FILE = "viajes_data.json"
FILES_DIR = "files"

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

logging.basicConfig(level=logging.INFO)


# --- Funciones de almacenamiento ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# --- Comandos del bot ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["/addtrip", "/listtrips"], ["/startnotifications"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Hola, ¿qué querés hacer?", reply_markup=reply_markup
    )

    # Botones inline también (opcional)
    inline_kb = [
        [InlineKeyboardButton("Añadir viaje", callback_data="addtrip")],
        [InlineKeyboardButton("Ver viajes", callback_data="listtrips")],
    ]
    await update.message.reply_text(
        "O usá los botones:", reply_markup=InlineKeyboardMarkup(inline_kb)
    )


async def add_trip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = context.args
        if len(parts) < 2:
            await update.message.reply_text("Uso: /addtrip <nombre_viaje> <YYYY-MM-DD>")
            return

        trip_name = parts[0]
        date_str = parts[1]
        datetime.datetime.strptime(date_str, "%Y-%m-%d")  # Validación

        data = load_data()
        data[trip_name] = {"date": date_str, "files": []}
        save_data(data)
        await update.message.reply_text(
            f"✅ Viaje '{trip_name}' guardado para el {date_str}."
        )

    except ValueError:
        await update.message.reply_text("⚠️ Fecha inválida. Usa el formato YYYY-MM-DD.")


async def list_trips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data:
        await update.message.reply_text("📭 No tienes viajes guardados.")
        return

    reply = "📅 Tus viajes:\n"
    for name, info in data.items():
        reply += f"• {name}: {info['date']} ({len(info['files'])} archivos adjuntos)\n"
    await update.message.reply_text(reply)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document
    trip_name = update.message.caption  # Usa la leyenda como nombre del viaje

    if not trip_name:
        await update.message.reply_text(
            "❗ Adjuntá el archivo con una leyenda que contenga el nombre del viaje."
        )
        return

    file = await context.bot.get_file(document.file_id)
    file_path = os.path.join(FILES_DIR, f"{trip_name}_{document.file_name}")
    await file.download_to_drive(file_path)

    data = load_data()
    if trip_name in data:
        data[trip_name]["files"].append(file_path)
        save_data(data)
        await update.message.reply_text(
            f"📎 Archivo guardado para el viaje '{trip_name}'."
        )
    else:
        await update.message.reply_text("❌ Ese viaje no existe. Usá /addtrip primero.")


# --- Notificaciones ---
async def daily_check(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    for trip_name, info in data.items():
        if info["date"] == tomorrow:
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=f"🔔 Recordatorio: Mañana es tu viaje '{trip_name}'",
            )


async def start_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.job_queue.run_daily(
        daily_check, time=datetime.time(hour=9), chat_id=chat_id
    )
    await update.message.reply_text("🔔 Notificaciones diarias activadas a las 9:00.")


# --- Botones inline ---
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "addtrip":
        await query.edit_message_text(
            "✍️ Usá el comando:\n`/addtrip <nombre> <YYYY-MM-DD>`", parse_mode="Markdown"
        )
    elif query.data == "listtrips":
        await list_trips(update, context)


# --- Configurar menú de comandos ---
async def set_commands(app):
    await app.bot.set_my_commands(
        [
            BotCommand("addtrip", "Añadir un nuevo viaje"),
            BotCommand("listtrips", "Listar tus viajes"),
            BotCommand("startnotifications", "Activar recordatorios diarios"),
            BotCommand("start", "Mostrar el menú"),
        ]
    )


# --- Main ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addtrip", add_trip))
    app.add_handler(CommandHandler("listtrips", list_trips))
    app.add_handler(CommandHandler("startnotifications", start_notifications))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_button))

    # Set menú comandos
    async def post_init(app):
        await set_commands(app)

    app.post_init = post_init

    print("🚀 Bot corriendo...")
    app.run_polling()


if __name__ == "__main__":
    main()
