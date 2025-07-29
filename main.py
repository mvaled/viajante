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
ASK_NAME, ASK_DESTINATION, ASK_START_DATE, ASK_END_DATE, ASK_DOCUMENTS = range(5)
ASK_TRIP_ID_TO_EDIT, ASK_FIELD_TO_EDIT, ASK_NEW_VALUE = range(100, 103)
ASK_CONTINUE_EDIT = 103
ASK_AFTER_EDIT_OPTION = 104
INFO_NAME, INFO_LASTNAME, INFO_BIRTHDATE, INFO_CERTIFICATES = range(4)

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

def load_data(user_id=None):
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            if user_id is not None:
                return data.get(str(user_id), {})
            return data
    return {}

def save_data(user_id, data):
    all_data = load_data()  # Load all data
    all_data[str(user_id)] = data  # Update with the specific user's data
    with open(DATA_FILE, "w") as f:
        json.dump(all_data, f, indent=2)

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
        [InlineKeyboardButton("✏️ Editar viaje", callback_data="menu_edittrip")],
        [InlineKeyboardButton("👤 Mi perfil", callback_data="my_profile")],
        [InlineKeyboardButton("📝 Formulario de información", callback_data="infoform")],
        [InlineKeyboardButton("📎 Subir archivo", callback_data="menu_upload")],
        [InlineKeyboardButton("🔔 Activar notificaciones", callback_data="menu_notify")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Bienvenido. Elige una opción:", reply_markup=reply_markup
    )

@restricted
async def list_trips(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data(user_id)  # Ensure to get user-specific data
    if not data:
        await update.effective_message.reply_text("📭 No tienes viajes guardados.")
        return

    reply = "📋 *Lista de viajes guardados:*\n\n"
    for name, info in data.items():
        destination = info.get("destination", "¿Sin destino?")
        start = info.get("start_date", "¿Sin inicio?")
        end = info.get("end_date", "¿Sin fin?")
        num_files = len(info.get("files", []))
        reply += f"• {name}: {start} – {end} • Destino: {destination} ({num_files} archivo(s))\n"

    await update.effective_message.reply_text(reply, parse_mode="Markdown")

@restricted
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    document: Document = update.message.document
    trip_name = update.message.caption if update.message.caption else ""
    
    if not trip_name:
        await update.message.reply_text("❗ Adjunta el archivo con una leyenda que contenga el nombre del viaje.")
        return

    data = load_data(user_id)
    if trip_name not in data:
        await update.message.reply_text("❌ Ese viaje no existe. Usa /addtrip primero.")
        return

    safe_trip = trip_name.replace(" ", "_")
    trip_folder = os.path.join(FILES_DIR, safe_trip)
    os.makedirs(trip_folder, exist_ok=True)

    file_path = os.path.join(trip_folder, document.file_name)
    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

    if "files" not in data[trip_name]:
        data[trip_name]["files"] = []
    data[trip_name]["files"].append(file_path)
    save_data(user_id, data)

    await update.message.reply_text(f"📎 Archivo guardado en '{trip_name}'.")

# --- Conversación para /addtrip ---
@restricted
async def add_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.args and len(context.args) >= 2:
        trip_name = context.args[0]
        date_str = context.args[1]
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
            data = load_data(user_id)
            if trip_name in data:
                await update.message.reply_text("❌ Ese viaje ya existe. Elige otro nombre.")
                return ConversationHandler.END

            data[trip_name] = {
                "start_date": date_str,
                "end_date": date_str,
                "files": [],
            }
            save_data(user_id, data)
            await update.message.reply_text(f"✅ Viaje '{trip_name}' guardado para el {date_str}.")
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ Fecha inválida. Usa formato YYYY-MM-DD.")
            return ConversationHandler.END
    else:
        await update.message.reply_text("✏️ ¿Cómo se llama el viaje?")
        return ASK_NAME

async def ask_trip_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trip_name"] = update.message.text.strip()
    await update.message.reply_text("🌍 ¿Cuál es el *destino* del viaje?")
    return ASK_DESTINATION

async def ask_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    destination = update.message.text.strip()
    context.user_data["destination"] = destination
    await update.message.reply_text("📅 ¿En qué fecha inicia el viaje? (formato YYYY-MM-DD)")
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
        start_date_str = context.user_data.get("start_date")
        if not start_date_str:
            await update.message.reply_text("❗ Debes ingresar la fecha de inicio primero.")
            return ASK_START_DATE

        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()

        if end_date < start_date:
            await update.message.reply_text("❌ La fecha final no puede ser anterior a la fecha de inicio. Intenta de nuevo.")
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
        await update.message.reply_text("❗ Por favor, envía solo archivos como documentos.")
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
    user_id = update.effective_user.id
    if "trip_name" in context.user_data:
        trip_name = context.user_data["trip_name"]
        data = load_data(user_id)
        data[trip_name] = {
            "start_date": context.user_data["start_date"],
            "end_date": context.user_data["end_date"],
            "destination": context.user_data.get("destination", "¿Sin destino?"),
            "files": context.user_data.get("files", []),
        }
        save_data(user_id, data)
        await update.message.reply_text(f"✅ Viaje '{trip_name}' guardado con éxito.")
    else:
        await update.message.reply_text("⚠️ No hay datos suficientes para guardar el viaje.")
    return ConversationHandler.END

@restricted
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

# --- Conversación para editar viaje ---
@restricted
async def edit_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_data(user_id)  # Ensure to get user-specific data
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
    user_id = update.effective_user.id
    new_value = update.message.text.strip()
    trip_index = context.user_data["edit_trip_index"]
    field = context.user_data["edit_field"]
    data = load_data(user_id)  # Ensure to get user-specific data
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
            data.pop(trip_name)
            trip_name = new_value
            trip_info["title"] = trip_name
            data[trip_name] = trip_info
        else:
            pass

        save_data(user_id, data)

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
        await update.message.reply_text(
            "🛠️ ¿Qué campo deseas editar?\n"
            "Escribe una de estas opciones:\n"
            "`título`, `inicio`, `fin`, `documentos`",
            parse_mode="Markdown",
        )
        return ASK_FIELD_TO_EDIT

    elif option == "2":
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
    user_id = update.effective_user.id
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

    data = load_data(user_id)  # Ensure to get user-specific data
    if trip_name not in data:
        await update.message.reply_text("❌ Error: el viaje no existe en datos.")
        return ConversationHandler.END
    if "files" not in data[trip_name]:
        data[trip_name]["files"] = []

    data[trip_name]["files"].append(file_path)
    save_data(user_id, data)

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
    user_id = context.job.data['user_id']  # Use job data to retrieve user ID
    data = load_data(user_id)  # Ensure to get user-specific data
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
    user_id = update.effective_user.id
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
        data={"user_id": user_id},  # Pass user ID with job data
    )
    await update.effective_message.reply_text("🔔 Notificaciones diarias activadas a las 9:00.")

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

async def start_infoform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Vamos a comenzar el formulario.\n\nPor favor, escribe tu *nombre*:", parse_mode="Markdown")
    return INFO_NAME


async def infoform_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Ahora escribe tus *apellidos*:", parse_mode="Markdown")
    return INFO_LASTNAME


async def infoform_lastname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["lastname"] = update.message.text.strip()
    await update.message.reply_text("Introduce tu *fecha de nacimiento* (formato YYYY-MM-DD):", parse_mode="Markdown")
    return INFO_BIRTHDATE


async def infoform_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birthdate_str = update.message.text.strip()
    try:
        datetime.strptime(birthdate_str, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❌ Fecha inválida. Usa el formato YYYY-MM-DD.")
        return INFO_BIRTHDATE

    context.user_data["birthdate"] = birthdate_str
    await update.message.reply_text("¿Tienes certificados que quieras añadir? Si no, escribe 'Ninguno'.")
    return INFO_CERTIFICATES


async def infoform_certificates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    certificates = update.message.text.strip()
    context.user_data["certificates"] = certificates

    user_id = str(update.effective_user.id)
    data = load_data()
    user_profile = data.get(user_id, {})

    user_profile["profile"] = {
        "name": context.user_data["name"],
        "lastname": context.user_data["lastname"],
        "birthdate": context.user_data["birthdate"],
        "certificates": context.user_data["certificates"],
    }

    data[user_id] = user_profile
    save_data(data)

    await update.message.reply_text("✅ Tus datos han sido guardados correctamente.")
    return ConversationHandler.END

async def finish_infoform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "birthdate" not in context.user_data:
        await update.message.reply_text("❌ Aún no has introducido tu fecha de nacimiento. No puedes terminar.")
        return

    user_id = str(update.effective_user.id)
    data = load_data()
    user_profile = data.get(user_id, {})

    user_profile["profile"] = {
        "name": context.user_data.get("name", ""),
        "lastname": context.user_data.get("lastname", ""),
        "birthdate": context.user_data["birthdate"],
        "certificates": context.user_data.get("certificates", "Ninguno"),
    }

    data[user_id] = user_profile
    save_data(data)

    await update.message.reply_text("✅ Formulario terminado y datos guardados.")

async def cancel_infoform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Formulario cancelado.")
    return ConversationHandler.END

async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user_data = data.get(user_id, {})
    profile = user_data.get("profile", {})

    name = profile.get("name", "No definido")
    lastname = profile.get("lastname", "No definido")
    birthdate = profile.get("birthdate", "No definido")
    certificates = profile.get("certificates", "Ninguno")

    trips = user_data.get("trips", [])
    documents = user_data.get("documents", [])

    message = (
        f"👤 *Perfil del usuario*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"📛 Nombre: {name} {lastname}\n"
        f"🎂 Fecha de nacimiento: {birthdate}\n"
        f"📄 Certificados: {certificates}\n\n"
        f"🧳 Viajes guardados: {len(trips)}\n"
        f"📁 Documentos guardados: {len(documents)}"
    )
    await update.message.reply_markdown(message)

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"Tu ID de Telegram es: `{user_id}`", parse_mode="Markdown"
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Excepción: {context.error}")
    if isinstance(update, Update) and (update.message or update.callback_query):
        await update.message.reply_text("⚠️ Ocurrió un error. Por favor, intenta nuevamente.")

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
            ASK_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_destination)],  # NUEVO
            ASK_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start_date)],
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
            ASK_TRIP_ID_TO_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_field_to_edit)],
            ASK_FIELD_TO_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_new_value)],
            ASK_NEW_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_value)],
            ASK_CONTINUE_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, continue_edit)],
            ASK_AFTER_EDIT_OPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, after_edit_option)],
            ASK_DOCUMENTS: [
                MessageHandler(filters.Document.ALL & ~filters.COMMAND, receive_document_edit),
                CommandHandler("finish", finish_adding_documents),
                CommandHandler("cancel", cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    infoform_handler = ConversationHandler(
        entry_points=[CommandHandler("infoform", start_infoform)],
        states={
            INFO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, infoform_name)],
            INFO_LASTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, infoform_lastname)],
            INFO_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, infoform_birthdate)],
            INFO_CERTIFICATES: [MessageHandler(filters.TEXT & ~filters.COMMAND, infoform_certificates)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_infoform),
            CommandHandler("finish", finish_infoform),
        ],
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
    app.add_handler(CommandHandler("infoform", start_infoform))
    app.add_handler(CommandHandler("finish", finish_infoform))
    app.add_handler(CommandHandler("myprofile", my_profile))
    app.add_handler(infoform_handler)

    app.run_polling()

if __name__ == "__main__":
    main()