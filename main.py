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
ASK_TRIP_ID_TO_EDIT, ASK_FIELD_TO_EDIT, ASK_NEW_VALUE = range(100, 103)
ASK_CONTINUE_EDIT = 103
ASK_AFTER_EDIT_OPTION = 104

# --- Configuración ---
load_dotenv()
ALLOWED_USERS = {
    885850042,  # mvaled
    1615047788,  # elmulas
    811614523,  # Yadenisp
}
TOKEN = os.getenv("TELEGRAM_TOKEN")
DATA_FILE = "viajes_data.json"
FILES_DIR = "files"

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

logging.basicConfig(level=logging.INFO)


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


@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📥 Añadir viaje", callback_data="menu_addtrip")],
        [InlineKeyboardButton("📋 Ver viajes", callback_data="menu_listtrips")],
        [InlineKeyboardButton("✏️ Editar viaje", callback_data="menu_edittrip")],  # ← NUEVO BOTÓN
        [InlineKeyboardButton("📎 Subir archivo", callback_data="menu_upload")],
        [InlineKeyboardButton("🔔 Activar notificaciones", callback_data="menu_notify")],
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

    data = load_data()
    if trip_name not in data:
        await update.message.reply_text("❌ Ese viaje no existe. Usa /addtrip primero.")
        return

    safe_name = trip_name.replace(" ", "_")
    file_path = os.path.join(FILES_DIR, f"{safe_name}_{document.file_name}")

    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

    # Asegurarse de que exista la lista "files"
    if "files" not in data[trip_name]:
        data[trip_name]["files"] = []
    data[trip_name]["files"].append(file_path)
    save_data(data)

    await update.message.reply_text(f"📎 Archivo guardado para el viaje '{trip_name}'.")


# --- Conversación para /addtrip ---
@restricted
async def add_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and len(context.args) >= 2:
        trip_name = context.args[0]
        date_str = context.args[1]
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
            data = load_data()
            data[trip_name] = {
                "start_date": date_str,
                "end_date": date_str,
                "files": [],
            }
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
        await update.message.reply_text(
            "📅 ¿En qué fecha finaliza el viaje? (formato YYYY-MM-DD)"
        )
        return ASK_END_DATE
    except ValueError:
        await update.message.reply_text("❌ Fecha inválida. Usa el formato YYYY-MM-DD.")
        return ASK_START_DATE


async def ask_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    end_date_str = update.message.text.strip()
    try:
        start_date_str = context.user_data.get("start_date")
        if not start_date_str:
            await update.message.reply_text("❗ Debes ingresar la fecha de inicio primero.")
            return ASK_START_DATE

        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()

        if end_date < start_date:
            await update.message.reply_text(
                "❌ La fecha final no puede ser anterior a la fecha de inicio. Intenta de nuevo."
            )
            return ASK_END_DATE

        context.user_data["end_date"] = end_date_str
        context.user_data["files"] = []

        await update.message.reply_text(
            "📎 Ahora puedes enviar uno o más documentos del viaje.\n"
            "✅ Cuando termines, escribe /finish para guardar el viaje.\n"
            "❌ Si quieres cancelar sin guardar nada, escribe /cancel."
        )
        return ASK_DOCUMENTS

    except ValueError:
        await update.message.reply_text("❌ Fecha inválida. Usa el formato YYYY-MM-DD.")
        return ASK_END_DATE


@restricted
async def collect_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document: Document = update.message.document
    if not document:
        await update.message.reply_text(
            "❗Por favor, envía solo archivos como documentos."
        )
        return ASK_DOCUMENTS

    trip_name = context.user_data.get("trip_name")
    if not trip_name:
        await update.message.reply_text("Error interno: nombre de viaje no encontrado.")
        return ConversationHandler.END

    safe_name = trip_name.replace(" ", "_")
    file_path = os.path.join(FILES_DIR, f"{safe_name}_{document.file_name}")

    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

    context.user_data["files"].append(file_path)
    await update.message.reply_text(
        "✅ Archivo guardado. Puedes enviar más o escribir /finish para terminar, o /cancel para salir sin guardar."
    )
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
        await update.message.reply_text(
            "⚠️ No hay datos suficientes para guardar el viaje."
        )
    return ConversationHandler.END


@restricted
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END


# --- Conversación para editar viaje ---
@restricted
async def edit_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data:
        await update.message.reply_text("⚠️ No tienes viajes guardados.")
        return ConversationHandler.END

    context.user_data["trips_list"] = list(data.items())
    text = "📝 Tus viajes guardados:\n"
    for i, (title, info) in enumerate(context.user_data["trips_list"]):
        text += f"{i+1}. {title} ({info.get('start_date', '?')} → {info.get('end_date', '?')})\n"
    text += "\n📌 Escribe el número del viaje que deseas editar:"

    await update.message.reply_text(text)
    return ASK_TRIP_ID_TO_EDIT


async def ask_field_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        trip_index = int(update.message.text.strip()) - 1
        trips_list = context.user_data.get("trips_list", [])

        if trip_index < 0 or trip_index >= len(trips_list):
            raise ValueError

        context.user_data["edit_trip_index"] = trip_index
        await update.message.reply_text(
            "🛠️ ¿Qué campo deseas editar?\n"
            "Escribe una de estas opciones:\n"
            "`título`, `inicio`, `fin`, `documentos`",
            parse_mode="Markdown",
        )
        return ASK_FIELD_TO_EDIT
    except ValueError:
        await update.message.reply_text("❌ Número inválido. Intenta de nuevo.")
        return ASK_TRIP_ID_TO_EDIT


async def ask_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = update.message.text.strip().lower()
    if field not in ["título", "inicio", "fin", "documentos"]:
        await update.message.reply_text(
            "❌ Opción no válida. Escribe: título, inicio, fin o documentos."
        )
        return ASK_FIELD_TO_EDIT

    context.user_data["edit_field"] = field

    if field == "documentos":
        context.user_data["new_files"] = []
        await update.message.reply_text(
            "📎 Envía los nuevos documentos. Escribe /finish para terminar o /cancel para salir."
        )
        return ASK_DOCUMENTS

    field_names = {
        "título": "nuevo título",
        "inicio": "nueva fecha de inicio (YYYY-MM-DD)",
        "fin": "nueva fecha final (YYYY-MM-DD)",
    }
    await update.message.reply_text(f"✏️ Escribe el {field_names[field]}:")
    return ASK_NEW_VALUE


async def save_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_value = update.message.text.strip()
    trip_index = context.user_data["edit_trip_index"]
    field = context.user_data["edit_field"]
    data = load_data()
    trips_list = context.user_data.get("trips_list", [])

    if not trips_list or trip_index >= len(trips_list):
        await update.message.reply_text("❌ Error interno: viaje no encontrado.")
        return ConversationHandler.END

    trip_name, trip_info = trips_list[trip_index]

    try:
        if field == "inicio":
            datetime.datetime.strptime(new_value, "%Y-%m-%d")
            trip_info["start_date"] = new_value
        elif field == "fin":
            datetime.datetime.strptime(new_value, "%Y-%m-%d")
            trip_info["end_date"] = new_value
        elif field == "título":
            # Cambiar la clave en data
            data.pop(trip_name)
            data[new_value] = trip_info
            trip_name = new_value
            context.user_data["trips_list"][trip_index] = (trip_name, trip_info)
        else:
            pass

        if field != "título":
            data[trip_name] = trip_info

        save_data(data)

        # Preguntar qué hacer ahora
        await update.message.reply_text(
            "✅ El viaje fue actualizado correctamente.\n\n"
            "¿Qué deseas hacer ahora?\n"
            "1️⃣ Seguir editando este mismo viaje\n"
            "2️⃣ Seleccionar y editar otro viaje\n"
            "3️⃣ Terminar edición\n\n"
            "Escribe 1, 2 o 3:"
        )
        return ASK_AFTER_EDIT_OPTION

    except ValueError:
        await update.message.reply_text("❌ Fecha inválida. Usa el formato YYYY-MM-DD.")
        return ASK_NEW_VALUE

async def after_edit_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    option = update.message.text.strip()
    trips_list = context.user_data.get("trips_list", [])
    trip_index = context.user_data.get("edit_trip_index")

    if option == "1":
        # Seguir editando mismo viaje: preguntar qué campo editar
        await update.message.reply_text(
            "🛠️ ¿Qué campo deseas editar?\n"
            "Escribe una de estas opciones:\n"
            "`título`, `inicio`, `fin`, `documentos`",
            parse_mode="Markdown",
        )
        return ASK_FIELD_TO_EDIT

    elif option == "2":
        # Seleccionar y editar otro viaje: mostrar lista y pedir número
        if not trips_list:
            await update.message.reply_text("⚠️ No tienes viajes guardados.")
            return ConversationHandler.END

        text = "📝 Tus viajes guardados:\n"
        for i, (title, info) in enumerate(trips_list):
            text += f"{i+1}. {title} ({info.get('start_date', '?')} → {info.get('end_date', '?')})\n"
        text += "\n📌 Escribe el número del viaje que deseas editar:"

        await update.message.reply_text(text)
        return ASK_TRIP_ID_TO_EDIT

    elif option == "3":
        await update.message.reply_text("✅ Edición finalizada.")
        return ConversationHandler.END

    else:
        await update.message.reply_text("❌ Opción no válida. Escribe 1, 2 o 3.")
        return ASK_AFTER_EDIT_OPTION

async def continue_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().lower()
    if answer in ["sí", "si", "s", "yes", "y"]:
        await update.message.reply_text(
            "🛠️ ¿Qué campo deseas editar?\n"
            "Escribe una de estas opciones:\n"
            "`título`, `inicio`, `fin`, `documentos`",
            parse_mode="Markdown",
        )
        return ASK_FIELD_TO_EDIT
    else:
        await update.message.reply_text("✅ Edición finalizada.")
        return ConversationHandler.END

@restricted
async def receive_document_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document:
        await update.message.reply_text("Por favor, envía un archivo válido.")
        return ASK_DOCUMENTS

    trip_index = context.user_data.get("edit_trip_index")
    trips_list = context.user_data.get("trips_list", [])

    if trip_index is None or trip_index >= len(trips_list):
        await update.message.reply_text("Error interno: viaje no encontrado.")
        return ConversationHandler.END

    trip_name, trip_info = trips_list[trip_index]

    safe_name = trip_name.replace(" ", "_")
    file_path = os.path.join(FILES_DIR, f"{safe_name}_{document.file_name}")

    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

    # Actualizar data en disco
    data = load_data()
    if trip_name not in data:
        await update.message.reply_text("❌ Error: el viaje no existe en datos.")
        return ConversationHandler.END
    if "files" not in data[trip_name]:
        data[trip_name]["files"] = []

    data[trip_name]["files"].append(file_path)
    save_data(data)

    await update.message.reply_text(
        "✅ Archivo guardado. Puedes enviar más o escribir /finish para terminar, o /cancel para salir sin guardar."
    )
    return ASK_DOCUMENTS


@restricted
async def finish_adding_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Documentos agregados correctamente.")
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
    elif query.data == "menu_edittrip":
        await query.message.reply_text(
            "✍️ Escribe el comando `/edittrip` para editar viajes.",
            parse_mode="Markdown",
        )
    elif query.data == "menu_upload":
        await query.message.reply_text(
            "📎 Envía un archivo con el *nombre del viaje* como leyenda.",
            parse_mode="Markdown",
        )
    elif query.data == "menu_notify":
        await start_notifications(update, context)


@restricted
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"Tu ID de Telegram es: `{user_id}`", parse_mode="Markdown"
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Excepción: {context.error}")
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "⚠️ Ocurrió un error. Por favor, intenta nuevamente."
        )


async def set_commands(app):
    await app.bot.set_my_commands(
        [
            BotCommand("addtrip", "Añadir un nuevo viaje"),
            BotCommand("listtrips", "Listar tus viajes"),
            BotCommand("edittrip", "Editar un viaje existente"),
            BotCommand("startnotifications", "Activar recordatorios diarios"),
            BotCommand("cancel", "Cancelar conversación"),
            BotCommand("start", "Mostrar el menú principal"),
            BotCommand("getid", "Mostrar tu ID de Telegram"),
        ]
    )


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler_add = ConversationHandler(
        entry_points=[CommandHandler("addtrip", add_trip_start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_trip_name)],
            ASK_START_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start_date)
            ],
            ASK_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end_date)],
            ASK_DOCUMENTS: [
                MessageHandler(filters.Document.ALL & ~filters.COMMAND, collect_documents),
                CommandHandler("finish", finish),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    conv_handler_edit = ConversationHandler(
    entry_points=[CommandHandler("edittrip", edit_trip_start)],
    states={
        ASK_TRIP_ID_TO_EDIT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_field_to_edit)
        ],
        ASK_FIELD_TO_EDIT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_new_value)
        ],
        ASK_NEW_VALUE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_value)
        ],
        ASK_CONTINUE_EDIT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, continue_edit)
        ],
        ASK_AFTER_EDIT_OPTION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, after_edit_option)
        ],
        ASK_DOCUMENTS: [
            MessageHandler(filters.Document.ALL & ~filters.COMMAND, receive_document_edit),
            CommandHandler("finish", finish_adding_documents),
            CommandHandler("cancel", cancel),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listtrips", list_trips))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_document))
    app.add_handler(conv_handler_add)
    app.add_handler(conv_handler_edit)
    app.add_handler(CommandHandler("startnotifications", start_notifications))
    app.add_handler(CommandHandler("getid", get_id))
    app.add_handler(CallbackQueryHandler(handle_menu))
    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()