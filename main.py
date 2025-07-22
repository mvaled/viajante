import os
import json
import logging
import datetime
from dotenv import load_dotenv
from telegram import (
    Update,
    Document,
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# --- Estados para ConversationHandler ---
ASK_NAME, ASK_DATE = range(2)

# --- Configuración ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
DATA_FILE = "viajes_data.json"
FILES_DIR = "files"

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

logging.basicConfig(level=logging.INFO)


# --- Funciones para leer y guardar datos ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# --- Comandos ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📥 Añadir viaje", callback_data="menu_addtrip")],
        [InlineKeyboardButton("📋 Ver viajes", callback_data="menu_listtrips")],
        [InlineKeyboardButton("📎 Subir archivo", callback_data="menu_upload")],
        [
            InlineKeyboardButton(
                "🔔 Activar notificaciones", callback_data="menu_notify"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Bienvenido. Elegí una opción:", reply_markup=reply_markup
    )


async def list_trips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data:
        await update.effective_message.reply_text("📭 No tienes viajes guardados.")
        return
    reply = "📅 Tus viajes:\n"
    for name, info in data.items():
        reply += f"• {name}: {info['date']} ({len(info['files'])} archivos adjuntos)\n"
    await update.effective_message.reply_text(reply)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document
    trip_name = update.message.caption
    if not trip_name:
        await update.message.reply_text(
            "❗ Adjuntá el archivo con una leyenda que contenga el nombre del viaje."
        )
        return

    file = await context.bot.get_file(document.file_id)
    safe_name = trip_name.replace(" ", "_")
    file_path = os.path.join(FILES_DIR, f"{safe_name}_{document.file_name}")
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


# --- Conversación para /addtrip ---
async def add_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and len(context.args) >= 2:
        trip_name = context.args[0]
        date_str = context.args[1]
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
            data = load_data()
            data[trip_name] = {"date": date_str, "files": []}
            save_data(data)
            await update.message.reply_text(
                f"✅ Viaje '{trip_name}' guardado para el {date_str}."
            )
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ Fecha inválida. Usa formato YYYY-MM-DD.")
            return ConversationHandler.END
    else:
        await update.message.reply_text("✏️ ¿Cómo se llama el viaje?")
        return ASK_NAME


async def ask_trip_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trip_name"] = update.message.text.strip()
    await update.message.reply_text(
        "📅 ¿Qué fecha tiene el viaje? (formato YYYY-MM-DD)"
    )
    return ASK_DATE


async def ask_trip_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text.strip()
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        trip_name = context.user_data["trip_name"]
        data = load_data()
        data[trip_name] = {"date": date_str, "files": []}
        save_data(data)
        await update.message.reply_text(
            f"✅ Viaje '{trip_name}' guardado para el {date_str}."
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Fecha inválida. Usá el formato YYYY-MM-DD.")
        return ASK_DATE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END


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
    job_queue = context.application.job_queue

    # Eliminar jobs anteriores para este chat para evitar duplicados
    current_jobs = job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()

    job_queue.run_daily(
        daily_check,
        time=datetime.time(hour=9, minute=0),
        chat_id=chat_id,
        name=str(chat_id),
    )
    await update.effective_message.reply_text(
        "🔔 Notificaciones diarias activadas a las 9:00."
    )


# --- Manejo de menú inline ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_addtrip":
        await query.message.reply_text(
            "✍️ Escribí el comando `/addtrip` para añadir un viaje.",
            parse_mode="Markdown",
        )
    elif query.data == "menu_listtrips":
        await list_trips(update, context)
    elif query.data == "menu_upload":
        await query.message.reply_text(
            "📎 Enviá un archivo con el *nombre del viaje* como leyenda.",
            parse_mode="Markdown",
        )
    elif query.data == "menu_notify":
        await start_notifications(update, context)


# --- Comandos para Telegram ---
async def set_commands(app):
    await app.bot.set_my_commands(
        [
            BotCommand("addtrip", "Añadir un nuevo viaje"),
            BotCommand("listtrips", "Listar tus viajes"),
            BotCommand("startnotifications", "Activar recordatorios diarios"),
            BotCommand("cancel", "Cancelar conversación"),
            BotCommand("start", "Mostrar el menú principal"),
        ]
    )


# --- Main ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addtrip", add_trip_start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_trip_name)],
            ASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_trip_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listtrips", list_trips))
    app.add_handler(CommandHandler("startnotifications", start_notifications))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_menu, pattern="^menu_"))
    app.add_handler(conv_handler)

    async def post_init(app):
        await set_commands(app)

    app.post_init = post_init

    print("🚀 Bot corriendo...")
    app.run_polling()


if __name__ == "__main__":
    main()
