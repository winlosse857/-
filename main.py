import os
import sqlite3
import logging
import threading
import time
from datetime import datetime, timedelta

import telebot
from telebot import types, apihelper

# ============ КОНФИГ ИЗ ОКРУЖЕНИЯ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "Переменная окружения BOT_TOKEN не задана. "
        "Установите её в Railway → Variables."
    )

_admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = [
    int(x.strip()) for x in _admin_ids_raw.split(",")
    if x.strip().isdigit()
]

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts.db")
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# user_states[user_id] = {"state": "...", "data": {...}}
user_states = {}


def is_allowed(user_id: int) -> bool:
    """Если ADMIN_IDS пуст — доступ открыт всем. Иначе — только им."""
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS


# ================= БАЗА ДАННЫХ =================
def db_init():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            username TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, chat_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            content_type TEXT NOT NULL DEFAULT 'text',
            text TEXT DEFAULT '',
            file_id TEXT DEFAULT NULL,
            publish_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# --- Каналы ---
def db_add_channel(user_id: int, chat_id: int, title: str, username: str | None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO channels (user_id, chat_id, title, username, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id, chat_id) DO UPDATE SET
               title = excluded.title,
               username = excluded.username""",
        (user_id, chat_id, title, username,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def db_get_channels(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""SELECT chat_id, title, username FROM channels
                   WHERE user_id=? ORDER BY id""", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def db_get_channel(user_id: int, chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""SELECT chat_id, title, username FROM channels
                   WHERE user_id=? AND chat_id=?""", (user_id, chat_id))
    row = cur.fetchone()
    conn.close()
    return row


def db_delete_channel(user_id: int, chat_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE user_id=? AND chat_id=?",
                (user_id, chat_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


# --- Посты ---
def db_add_post(user_id: int, channel_id: int, content_type: str,
                text: str, file_id: str | None, publish_at: datetime) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO posts
           (user_id, channel_id, content_type, text, file_id,
            publish_at, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (user_id, channel_id, content_type, text or "", file_id,
         publish_at.strftime("%Y-%m-%d %H:%M:%S"),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    post_id = cur.lastrowid
    conn.close()
    return post_id


def db_get_pending_posts():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""SELECT id, user_id, channel_id, content_type, text,
                          file_id, publish_at
                   FROM posts WHERE status='pending' ORDER BY publish_at""")
    rows = cur.fetchall()
    conn.close()
    return rows


def db_get_user_posts(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""SELECT id, channel_id, content_type, text, file_id, publish_at
                   FROM posts WHERE user_id=? AND status='pending'
                   ORDER BY publish_at""", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def db_get_post(post_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""SELECT id, user_id, channel_id, content_type, text,
                          file_id, publish_at, status
                   FROM posts WHERE id=?""", (post_id,))
    row = cur.fetchone()
    conn.close()
    return row


def db_mark_published(post_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE posts SET status='published' WHERE id=?", (post_id,))
    conn.commit()
    conn.close()


def db_delete_post(post_id: int, user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM posts WHERE id=? AND user_id=? AND status='pending'",
                (post_id, user_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


# ================= УТИЛИТЫ =================
ICONS = {
    "text": "📝", "photo": "🖼", "video": "🎬", "document": "📎",
    "audio": "🎵", "voice": "🎤", "sticker": "🌟",
    "animation": "🎞", "video_note": "⭕",
}


def preview_text(text: str, limit: int = 60) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit - 3] + "..."


def send_safe(send_func, chat_id, *args, **kwargs):
    """
    Отправляет сообщение. Если Telegram не смог распарсить HTML —
    отправляет без разметки. Прочие ошибки пробрасывает наверх.
    """
    try:
        return send_func(chat_id, *args, **kwargs)
    except apihelper.ApiTelegramException as e:
        desc = (e.description or "").lower()
        if "can't parse entities" in desc or "parse" in desc and "entit" in desc:
            log.warning(f"HTML-парсинг не удался, отправка без разметки: {e}")
            kwargs["parse_mode"] = None
            return send_func(chat_id, *args, **kwargs)
        raise


def verify_bot_in_channel(chat_id) -> tuple[bool, str]:
    """Проверяет, что бот — админ канала. Возвращает (ok, сообщение_об_ошибке)."""
    try:
        me = bot.get_me()
        member = bot.get_chat_member(chat_id, me.id)
        if member.status in ("administrator", "creator"):
            return True, ""
        return False, ("Я не администратор этого канала. "
                       "Добавьте меня в канал и выдайте право "
                       "«Публикация сообщений».")
    except apihelper.ApiTelegramException as e:
        desc = (e.description or "").lower()
        if "chat not found" in desc or "member not found" in desc:
            return False, ("Я не вижу этот канал. Убедитесь, что добавили "
                           "меня в канал и назначили администратором.")
        return False, f"Ошибка Telegram API: {e.description}"
    except Exception as e:
        return False, f"Ошибка проверки канала: {e}"


# ================= ПУБЛИКАЦИЯ =================
def publish_post(post_id: int):
    row = db_get_post(post_id)
    if not row:
        return
    _, user_id, channel_id, ctype, text, file_id, publish_at, status = row
    if status != "pending":
        return

    try:
        if ctype == "text":
            send_safe(bot.send_message, channel_id, text,
                      disable_web_page_preview=False)
        elif ctype == "photo":
            send_safe(bot.send_photo, channel_id, file_id, caption=text or None)
        elif ctype == "video":
            send_safe(bot.send_video, channel_id, file_id, caption=text or None)
        elif ctype == "document":
            send_safe(bot.send_document, channel_id, file_id, caption=text or None)
        elif ctype == "audio":
            send_safe(bot.send_audio, channel_id, file_id, caption=text or None)
        elif ctype == "voice":
            send_safe(bot.send_voice, channel_id, file_id, caption=text or None)
        elif ctype == "sticker":
            bot.send_sticker(channel_id, file_id)
        elif ctype == "animation":
            send_safe(bot.send_animation, channel_id, file_id, caption=text or None)
        elif ctype == "video_note":
            bot.send_video_note(channel_id, file_id)
        else:
            log.warning(f"Неизвестный тип контента: {ctype}")
            return

        db_mark_published(post_id)
        log.info(f"Пост #{post_id} ({ctype}) → канал {channel_id}")

        try:
            bot.send_message(user_id, f"✅ Пост #{post_id} опубликован.")
        except Exception:
            pass
    except Exception as e:
        log.exception(f"Ошибка публикации поста #{post_id}: {e}")
        try:
            bot.send_message(user_id,
                             f"⚠️ Не удалось опубликовать пост #{post_id}: {e}")
        except Exception:
            pass


# ================= ПЛАНИРОВЩИК =================
def schedule_worker():
    while True:
        try:
            now = datetime.now()
            for (post_id, user_id, channel_id, ctype,
                 text, file_id, publish_at_str) in db_get_pending_posts():
                try:
                    publish_at = datetime.strptime(publish_at_str,
                                                   "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    log.warning(f"Битая дата у поста #{post_id}: {publish_at_str}")
                    continue
                if publish_at <= now:
                    publish_post(post_id)
        except Exception as e:
            log.exception(f"Ошибка в планировщике: {e}")
        time.sleep(10)


# ================= КЛАВИАТУРЫ =================
def main_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📝 Создать пост", callback_data="menu:create"),
        types.InlineKeyboardButton("📢 Мои каналы", callback_data="menu:channels"),
        types.InlineKeyboardButton("➕ Привязать канал", callback_data="menu:bind"),
        types.InlineKeyboardButton("📋 Мои посты", callback_data="menu:list"),
        types.InlineKeyboardButton("ℹ️ Помощь", callback_data="menu:help"),
    )
    return kb


def cancel_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="menu:cancel"))
    return kb


def time_presets_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    now = datetime.now()
    today_18 = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if today_18 <= now:
        today_18 += timedelta(days=1)
    tomorrow_9 = (now + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0)

    kb.add(
        types.InlineKeyboardButton(
            "⏱ Через 10 мин",
            callback_data=f"t:{int((now + timedelta(minutes=10)).timestamp())}"),
        types.InlineKeyboardButton(
            "⏱ Через 1 час",
            callback_data=f"t:{int((now + timedelta(hours=1)).timestamp())}"),
    )
    kb.add(
        types.InlineKeyboardButton(
            "🕕 Сегодня в 18:00",
            callback_data=f"t:{int(today_18.timestamp())}"),
        types.InlineKeyboardButton(
            "🌅 Завтра в 9:00",
            callback_data=f"t:{int(tomorrow_9.timestamp())}"),
    )
    kb.add(types.InlineKeyboardButton("⌨️ Ввести вручную",
                                      callback_data="menu:manual_time"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="menu:cancel"))
    return kb


def confirm_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("✅ Запланировать", callback_data="menu:confirm"),
        types.InlineKeyboardButton("📢 Изменить канал",
                                   callback_data="menu:rewrite_channel"),
        types.InlineKeyboardButton("✏️ Изменить текст",
                                   callback_data="menu:rewrite_text"),
        types.InlineKeyboardButton("🕒 Изменить время",
                                   callback_data="menu:rewrite_time"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="menu:cancel"),
    )
    return kb


def channels_picker_kb(user_id: int, action: str):
    rows = db_get_channels(user_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for chat_id, title, username in rows:
        label = f"📢 {title}" + (f" ({username})" if username else "")
        kb.add(types.InlineKeyboardButton(label,
                                          callback_data=f"{action}:{chat_id}"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="menu:cancel"))
    return kb


# ================= КОМАНДЫ =================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if not is_allowed(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ У вас нет доступа к этому боту.")
        return
    user_states.pop(message.from_user.id, None)
    text = (
        "👋 <b>Бот-планировщик постов</b>\n\n"
        "Я публикую посты в ваши каналы по расписанию.\n\n"
        "<b>Как начать:</b>\n"
        "1. Привяжите канал кнопкой «➕ Привязать канал»\n"
        "2. Создайте пост\n"
        "3. Выберите канал, содержимое и время\n\n"
        "Поддерживается текст, фото, видео, документы, аудио, "
        "голосовые, стикеры, GIF.\n"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "Действие отменено.",
                     reply_markup=main_menu_kb())


@bot.message_handler(commands=["channels"])
def cmd_channels(message):
    if not is_allowed(message.from_user.id):
        return
    show_user_channels(message.chat.id, message.from_user.id)


# ================= ГЛАВНОЕ МЕНЮ =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("menu:"))
def menu_router(call):
    if not is_allowed(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    action = call.data.split(":", 1)[1]
    uid = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if action == "cancel":
        user_states.pop(uid, None)
        bot.answer_callback_query(call.id, "Отменено")
        try:
            bot.edit_message_text("Действие отменено.", chat_id=chat_id,
                                  message_id=msg_id, reply_markup=main_menu_kb())
        except Exception:
            bot.send_message(chat_id, "Действие отменено.",
                             reply_markup=main_menu_kb())
        return

    if action == "back":
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text("Главное меню:", chat_id=chat_id,
                                  message_id=msg_id, reply_markup=main_menu_kb())
        except Exception:
            bot.send_message(chat_id, "Главное меню:",
                             reply_markup=main_menu_kb())
        return

    if action == "help":
        bot.answer_callback_query(call.id)
        bot.send_message(
            chat_id,
            "ℹ️ <b>Как пользоваться</b>\n\n"
            "<b>1. Привязка канала</b>\n"
            "• Нажмите «➕ Привязать канал»\n"
            "• Отправьте <code>@username</code> канала — либо\n"
            "• Перешлите любое сообщение из своего канала "
            "(для приватных каналов)\n"
            "• Бот должен быть <b>администратором</b> канала "
            "с правом «Публикация сообщений».\n\n"
            "<b>2. Создание поста</b>\n"
            "• Нажмите «📝 Создать пост»\n"
            "• Выберите канал из списка\n"
            "• Отправьте содержимое (текст или медиа с подписью)\n"
            "• Выберите время кнопкой или введите вручную:\n"
            "  <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
            "<b>3. Управление</b>\n"
            "• «📋 Мои посты» — список запланированных\n"
            "• «📢 Мои каналы» — привязанные каналы",
            reply_markup=main_menu_kb()
        )
        return

    if action == "channels":
        bot.answer_callback_query(call.id)
        show_user_channels(chat_id, uid)
        return

    if action == "bind":
        bot.answer_callback_query(call.id)
        user_states[uid] = {"state": "waiting_channel", "data": {}}
        try:
            bot.edit_message_text(
                "📡 <b>Привязка канала</b>\n\n"
                "Отправьте одно из:\n\n"
                "• <b>@username</b> публичного канала "
                "(например, <code>@my_channel</code>)\n"
                "• <b>Перешлите</b> любое сообщение из приватного канала\n\n"
                "⚠️ Перед этим добавьте меня в канал как "
                "<b>администратора</b> с правом публикации сообщений.",
                chat_id=chat_id, message_id=msg_id, reply_markup=cancel_kb()
            )
        except Exception:
            bot.send_message(chat_id,
                             "📡 Отправьте @username канала или перешлите "
                             "сообщение из канала.",
                             reply_markup=cancel_kb())
        return

    if action == "list":
        bot.answer_callback_query(call.id)
        show_user_posts(chat_id, uid)
        return

    if action == "create":
        chans = db_get_channels(uid)
        if not chans:
            bot.answer_callback_query(call.id, "Сначала привяжите канал",
                                      show_alert=True)
            return
        bot.answer_callback_query(call.id)
        user_states[uid] = {"state": "waiting_channel_choice", "data": {}}
        try:
            bot.edit_message_text("📢 <b>Выберите канал для публикации:</b>",
                                  chat_id=chat_id, message_id=msg_id,
                                  reply_markup=channels_picker_kb(uid, "pickch"))
        except Exception:
            bot.send_message(chat_id, "📢 Выберите канал для публикации:",
                             reply_markup=channels_picker_kb(uid, "pickch"))
        return

    if action == "manual_time":
        st = user_states.get(uid)
        if not st or st["state"] not in ("waiting_time", "waiting_time_manual"):
            bot.answer_callback_query(call.id, "Сначала отправьте содержимое")
            return
        st["state"] = "waiting_time_manual"
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "🕒 Введите дату и время в формате:\n"
                "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
                "Пример: <code>25.12.2025 18:30</code>",
                chat_id=chat_id, message_id=msg_id, reply_markup=cancel_kb()
            )
        except Exception:
            pass
        return

    if action == "confirm":
        st = user_states.get(uid)
        if not st or st["state"] != "confirming":
   
