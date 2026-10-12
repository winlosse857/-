import os
import secrets
import sqlite3
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

DB_PATH = Path(os.getenv("NOIR_BOT_DB", "noir_bot.sqlite3"))
OWNER_TELEGRAM_ID = os.getenv("NOIR_OWNER_TELEGRAM_ID", "").strip()
OWNER_NOIR_ID = "NOIR-TELEGRAM"


def connect():
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS identities (telegram_id INTEGER PRIMARY KEY, noir_id TEXT UNIQUE NOT NULL)")
    return db


def get_or_create_identity(telegram_id: int) -> str:
    is_owner = OWNER_TELEGRAM_ID and str(telegram_id) == OWNER_TELEGRAM_ID
    with connect() as db:
        row = db.execute("SELECT noir_id FROM identities WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if is_owner:
            if row and row[0] == OWNER_NOIR_ID:
                return OWNER_NOIR_ID
            reserved = db.execute("SELECT telegram_id FROM identities WHERE noir_id = ?", (OWNER_NOIR_ID,)).fetchone()
            if not reserved:
                if row:
                    db.execute("UPDATE identities SET noir_id = ? WHERE telegram_id = ?", (OWNER_NOIR_ID, telegram_id))
                else:
                    db.execute("INSERT INTO identities (telegram_id, noir_id) VALUES (?, ?)", (telegram_id, OWNER_NOIR_ID))
                return OWNER_NOIR_ID
        if row:
            return row[0]
        while True:
            noir_id = f"NOIR-{secrets.randbelow(900000) + 100000}"
            try:
                db.execute("INSERT INTO identities (telegram_id, noir_id) VALUES (?, ?)", (telegram_id, noir_id))
                return noir_id
            except sqlite3.IntegrityError:
                continue


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.message:
        return
    noir_id = get_or_create_identity(user.id)
    display_id = f"+888 {noir_id}" if noir_id == OWNER_NOIR_ID else noir_id
    owner_note = "\n\nСтатус: владелец Dolbagram" if noir_id == OWNER_NOIR_ID else ""
    await update.message.reply_text(
        "Добро пожаловать в Dolbagram!\n\n"
        f"Твой ID NOIR: {display_id}{owner_note}\n\n"
        "Это виртуальный идентификатор NOIR, а не настоящий телефонный номер: "
        "он не принимает SMS и звонки. Подтверждение входа в приложении через Telegram "
        "будет подключено отдельным этапом."
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user and update.message:
        await update.message.reply_text(f"Твой Telegram user ID: {user.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Команды:\n/start — получить ID NOIR\n/myid — узнать числовой Telegram ID\n/help — помощь"
        )


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in the environment before starting the bot.")
    connect().close()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("help", help_command))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
