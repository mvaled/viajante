import os
import json
import logging
import datetime
from dotenv import load_dotenv
from functools import wraps
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
ASK_NAME, ASK_START_DATE, ASK_END_DATE, ASK_DOCUMENTS = range(4)

# --- Configuración ---
load_dotenv()
ALLOWED_USERS = {
    885850042,  # mvaled
    1615047788,  # elmulas
}
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


def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_USERS:
            await update.effective_message.reply_text(
                "Lo siento, pero no estás autorizado para usar este bot."
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Comandos ---
@restricted
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
        "👋 Bienvenido. Elige una opción:", reply_markup=reply_markup
    )

@restricted
async def list_trips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data:
        await update.effective_message.reply_text("📭 No tienes viajes guardados.")
        return

    reply = "📋 *Lista de viajes guardados:*\n\n"
    for name, info in data.items():
        start = info.get("start_date", "¿Sin inicio?")
        end = info.get("end_date", "¿Sin fin?")
        num_files = len(info.get("files", []))
        reply += f"• {name}: {start} – {end} ({num_files} archivo(s))\n"

    await update.effective_message.reply_text(reply, parse_mode="Markdown")

@restricted
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document
    trip_name = update.message.caption
    if not trip_name:
        await update.message.reply_text(
            "❗ Adjunta el archivo con una leyenda que contenga el nombre del viaje."
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
        await update.message.reply_text("❌ Ese viaje no existe. Usa /addtrip primero.")


# --- Conversación para /addtrip ---
@restricted
async def add_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and len(context.args) >= 2:
        trip_name = context.args[0]
        date_str = context.args[1]
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
            data = load_data()
            data[trip_name] = {"start_date": date_str, "end_date": date_str, "files": []}
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
        "📅 ¿En qué fecha inicia el viaje? (formato YYYY-MM-DD)"
    )
    return ASK_START_DATE

async def ask_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text.strip()
    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        context.user_data["start_date"] = date_str
        await update.message.reply_text("📅 ¿En qué fecha finaliza el viaje? (formato YYYY-MM-DD)")
        return ASK_END_DATE
    except ValueError:
        await update.message.reply_text("❌ Fecha inválida. Usa el formato YYYY-MM-DD.")
        return ASK_START_DATE

async def ask_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    end_date_str = update.message.text.strip()
    try:
        datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
        context.user_data["end_date"] = end_date_str
        await update.message.reply_text(
    "📎 Ahora puedes enviar uno o más documentos del viaje.\n"
    "✅ Cuando termines, escribe /finish para guardar el viaje.\n"
    "❌ Si quieres cancelar sin guardar nada, escribe /cancel."
)
        context.user_data["files"] = []
        return ASK_DOCUMENTS
    except ValueError:
        await update.message.reply_text("❌ Fecha inválida. Usa el formato YYYY-MM-DD.")
        return ASK_END_DATE

@restricted
async def collect_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document
    if not document:
        await update.message.reply_text("❗Por favor, envía solo archivos como documentos.")
        return ASK_DOCUMENTS

    trip_name = context.user_data["trip_name"]
    safe_name = trip_name.replace(" ", "_")
    file_path = os.path.join(FILES_DIR, f"{safe_name}_{document.file_name}")

    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

    context.user_data["files"].append(file_path)
    await update.message.reply_text("✅ Archivo guardado. Puedes enviar más o escribir /finish para terminar, o /cancel para salir sin guardar.")
    return ASK_DOCUMENTS

@restricted
async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "trip_name" in context.user_data:
        trip_name = context.user_data["trip_name"]
        start_date = context.user_data["start_date"]
        end_date = context.user_data["end_date"]
        files = context.user_data.get("files", [])

        data = load_data()
        data[trip_name] = {
            "start_date": start_date,
            "end_date": end_date,
            "files": files,
        }
        save_data(data)
        await update.message.reply_text(f"✅ Viaje '{trip_name}' guardado con éxito.")
    else:
        await update.message.reply_text("⚠️ No hay datos suficientes para guardar el viaje.")
    return ConversationHandler.END

@restricted
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

# --- Notificaciones ---
async def daily_check(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    for trip_name, info in data.items():
        if info["start_date"] == tomorrow:
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=f"🔔 Recordatorio: Mañana es tu viaje '{trip_name}'",
            )

@restricted
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
@restricted
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_addtrip":
        await query.message.reply_text(
            "✍️ Escribe el comando `/addtrip` para añadir un viaje.",
            parse_mode="Markdown",
        )
    elif query.data == "menu_listtrips":
        await list_trips(update, context)
    elif query.data == "menu_upload":
        await query.message.reply_text(
            "📎 Envia un archivo con el *nombre del viaje* como leyenda.",
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
            BotCommand("getid", "Mostrar tu ID de Telegram"),
        ]
    )

@restricted
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Tu ID de Telegram es: `{user_id}`", parse_mode='Markdown')


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Excepción: {context.error}")
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Ocurrió un error. Por favor, intenta nuevamente.")

# --- Main ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
    entry_points=[CommandHandler("addtrip", add_trip_start)],
    states={
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_trip_name)],
        ASK_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start_date)],
        ASK_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end_date)],
        ASK_DOCUMENTS: [MessageHandler(filters.Document.ALL, collect_documents), CommandHandler("finish", finish)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getid", get_id))
    app.add_handler(CommandHandler("listtrips", list_trips))
    app.add_handler(CommandHandler("startnotifications", start_notifications))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_menu, pattern="^menu_"))
    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)

    async def post_init(app):
        await set_commands(app)

    app.post_init = post_init

    print("🚀 Bot corriendo...")
    app.run_polling()


if __name__ == "__main__":
    main()
