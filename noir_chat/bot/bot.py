import os
import secrets
import sqlite3
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

DB_PATH = Path(os.getenv("NOIR_BOT_DB", "noir_bot.sqlite3"))


def connect():
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS identities (telegram_id INTEGER PRIMARY KEY, noir_id TEXT UNIQUE NOT NULL)")
    return db


def get_or_create_identity(telegram_id: int) -> str:
    with connect() as db:
        row = db.execute("SELECT noir_id FROM identities WHERE telegram_id = ?", (telegram_id,)).fetchone()
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
    await update.message.reply_text(
        "Добро пожаловать в NOIR Messenger!\n\n"
        f"Твой внутренний ID: {noir_id}\n\n"
        "Это уникальный идентификатор NOIR, а не телефонный номер: он не принимает SMS и звонки. "
        "Сохрани этот Telegram-аккаунт для подтверждения входа. Интеграция подтверждения входа в приложение будет добавлена следующим этапом."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Команды:\n/start — получить или посмотреть свой ID NOIR\n/help — помощь")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in the environment before starting the bot.")
    connect().close()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
