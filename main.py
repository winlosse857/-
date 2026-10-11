# -*- coding: utf-8 -*-
"""
Telegram-бот для отложенной публикации постов в каналы.
Каждый пользователь привязывает свой канал через бота.

Переменные окружения (Railway → Variables):
    BOT_TOKEN   — токен бота (обязательно)
    ADMIN_IDS   — ID через запятую (опционально; если пусто — доступ всем)
"""

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


def db_add_channel(user_id: int, chat_id: int, title: str, username):
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


def db_add_post(user_id: int, channel_id: int, content_type: str,
                text: str, file_id, publish_at: datetime) -> int:
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
    """Отправка с fallback: если HTML не парсится — шлём без разметки."""
    try:
        return send_func(chat_id, *args, **kwargs)
    except apihelper.ApiTelegramException as e:
        desc = (e.description or "").lower()
        if "can't parse entities" in desc or "parse" in desc and "entit" in desc:
            log.warning(f"HTML-парсинг не удался, отправка без разметки: {e}")
            kwargs["parse_mode"] = None
            return send_func(chat_id, *args, **kwargs)
        raise


def verify_bot_in_channel(chat_id):
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
            bot.answer_callback_query(call.id, "Нечего подтверждать")
            return
        d = st["data"]
        post_id = db_add_post(uid, d["channel_id"], d["content_type"],
                              d.get("text", ""), d.get("file_id"),
                              d["publish_at"])
        user_states.pop(uid, None)
        bot.answer_callback_query(call.id, "Запланировано ✅")
        try:
            bot.edit_message_text(
                f"✅ Пост #{post_id} для канала "
                f"<b>{d['channel_title']}</b> запланирован на "
                f"<code>{d['publish_at'].strftime('%d.%m.%Y %H:%M')}</code>",
                chat_id=chat_id, message_id=msg_id, reply_markup=main_menu_kb()
            )
        except Exception:
            pass
        log.info(f"Запланирован пост #{post_id} → канал {d['channel_id']}")
        return

    if action == "rewrite_text":
        st = user_states.get(uid)
        if not st or "content_type" not in st.get("data", {}):
            bot.answer_callback_query(call.id, "Сессия устарела")
            return
        st["state"] = "waiting_content"
        st["data"].pop("content_type", None)
        st["data"].pop("file_id", None)
        st["data"].pop("text", None)
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text("✍️ Отправьте новое содержимое поста.",
                                  chat_id=chat_id, message_id=msg_id,
                                  reply_markup=cancel_kb())
        except Exception:
            pass
        return

    if action == "rewrite_time":
        st = user_states.get(uid)
        if not st or "content_type" not in st.get("data", {}):
            bot.answer_callback_query(call.id, "Сначала отправьте содержимое")
            return
        st["state"] = "waiting_time"
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text("🕒 Выберите время публикации:",
                                  chat_id=chat_id, message_id=msg_id,
                                  reply_markup=time_presets_kb())
        except Exception:
            pass
        return

    if action == "rewrite_channel":
        st = user_states.get(uid)
        if not st:
            bot.answer_callback_query(call.id, "Сессия устарела")
            return
        bot.answer_callback_query(call.id)
        st["state"] = "waiting_channel_choice"
        try:
            bot.edit_message_text("📢 Выберите новый канал:",
                                  chat_id=chat_id, message_id=msg_id,
                                  reply_markup=channels_picker_kb(uid, "pickch"))
        except Exception:
            pass
        return


# ================= ВЫБОР КАНАЛА ДЛЯ ПОСТА =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("pickch:"))
def pick_channel_cb(call):
    if not is_allowed(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    uid = call.from_user.id
    st = user_states.get(uid)
    if not st:
        bot.answer_callback_query(call.id, "Сессия устарела, начните заново")
        return

    chat_id = int(call.data.split(":", 1)[1])
    ch = db_get_channel(uid, chat_id)
    if not ch:
        bot.answer_callback_query(call.id, "Канал не найден")
        return

    st["data"]["channel_id"] = ch[0]
    st["data"]["channel_title"] = ch[1]

    if "content_type" in st["data"]:
        st["state"] = "waiting_time"
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                f"📢 Канал: <b>{ch[1]}</b>\n\n🕒 Выберите время публикации:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=time_presets_kb()
            )
        except Exception:
            pass
    else:
        st["state"] = "waiting_content"
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                f"📢 Канал: <b>{ch[1]}</b>\n\n"
                f"✍️ Отправьте содержимое поста "
                f"(текст или медиа с подписью).",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=cancel_kb()
            )
        except Exception:
            pass


# ================= ВЫБОР ВРЕМЕНИ =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("t:"))
def time_preset_cb(call):
    if not is_allowed(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    uid = call.from_user.id
    st = user_states.get(uid)
    if not st or st["state"] not in ("waiting_time", "waiting_time_manual"):
        bot.answer_callback_query(call.id, "Сессия устарела, начните заново")
        return

    ts = int(call.data.split(":", 1)[1])
    publish_at = datetime.fromtimestamp(ts)
    st["data"]["publish_at"] = publish_at
    st["state"] = "confirming"

    d = st["data"]
    icon = ICONS.get(d.get("content_type"), "📝")
    prev = preview_text(d.get("text", "")) or "(без текста)"
    summary = (
        f"📋 <b>Проверьте пост</b>\n\n"
        f"📢 Канал: <b>{d.get('channel_title', '—')}</b>\n"
        f"{icon} Тип: <b>{d.get('content_type', '—')}</b>\n"
        f"💬 Текст: {prev}\n"
        f"🕒 Время: <code>{publish_at.strftime('%d.%m.%Y %H:%M')}</code>"
    )
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text(summary,
                              chat_id=call.message.chat.id,
                              message_id=call.message.message_id,
                              reply_markup=confirm_kb())
    except Exception:
        pass


# ================= УДАЛЕНИЕ ПОСТА =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("del:"))
def delete_post_cb(call):
    if not is_allowed(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    post_id = int(call.data.split(":")[1])
    ok = db_delete_post(post_id, call.from_user.id)
    if ok:
        bot.answer_callback_query(call.id, "Удалено")
        try:
            bot.edit_message_text(f"🗑 Пост #{post_id} удалён.",
                                  chat_id=call.message.chat.id,
                                  message_id=call.message.message_id)
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "Не удалось удалить")


# ================= УДАЛЕНИЕ КАНАЛА =================
@bot.callback_query_handler(func=lambda c: c.data.startswith("unch:"))
def unbind_channel_cb(call):
    if not is_allowed(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    chat_id = int(call.data.split(":", 1)[1])
    ok = db_delete_channel(call.from_user.id, chat_id)
    bot.answer_callback_query(call.id, "Отвязано" if ok else "Не найдено")
    if ok:
        try:
            bot.edit_message_text("🗑 Канал отвязан.",
                                  chat_id=call.message.chat.id,
                                  message_id=call.message.message_id)
        except Exception:
            pass


# ================= СПИСКИ =================
def show_user_channels(chat_id: int, user_id: int):
    rows = db_get_channels(user_id)
    if not rows:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➕ Привязать канал",
                                          callback_data="menu:bind"))
        kb.add(types.InlineKeyboardButton("◀️ Назад",
                                          callback_data="menu:back"))
        bot.send_message(chat_id, "У вас нет привязанных каналов.",
                         reply_markup=kb)
        return

    bot.send_message(chat_id, f"📢 <b>Ваши каналы ({len(rows)}):</b>")
    for cid, title, username in rows:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🗑 Отвязать",
                                              callback_data=f"unch:{cid}"))
        line = f"📢 <b>{title}</b>"
        if username:
            line += f"\n🔗 {username}"
        line += f"\n🆔 <code>{cid}</code>"
        bot.send_message(chat_id, line, reply_markup=markup)


def show_user_posts(chat_id: int, user_id: int):
    rows = db_get_user_posts(user_id)
    if not rows:
        bot.send_message(chat_id, "У вас нет запланированных постов.",
                         reply_markup=main_menu_kb())
        return

    bot.send_message(chat_id, f"📋 <b>Запланированные посты ({len(rows)}):</b>")
    for post_id, channel_id, ctype, text, file_id, publish_at in rows:
        icon = ICONS.get(ctype, "📝")
        prev = preview_text(text) or "(без текста)"
        ch = db_get_channel(user_id, channel_id)
        ch_title = ch[1] if ch else f"id {channel_id}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🗑 Удалить",
                                              callback_data=f"del:{post_id}"))
        bot.send_message(
            chat_id,
            f"{icon} <b>#{post_id}</b> → 📢 {ch_title}\n"
            f"🕒 <code>{publish_at}</code>\n\n{prev}",
            reply_markup=markup
        )


# ================= ПРИЁМ КОНТЕНТА =================
def _save_content_and_ask_time(message, user_id: int, content_type: str,
                               text: str, file_id):
    st = user_states.get(user_id)
    if not st or st["state"] != "waiting_content":
        return
    st["data"]["content_type"] = content_type
    st["data"]["text"] = text or ""
    st["data"]["file_id"] = file_id
    st["state"] = "waiting_time"

    icon = ICONS.get(content_type, "📝")
    ch_title = st["data"].get("channel_title", "—")
    bot.send_message(
        message.chat.id,
        f"{icon} Содержимое принято (<b>{content_type}</b>).\n"
        f"📢 Канал: <b>{ch_title}</b>\n\n"
        f"🕒 Выберите время публикации:",
        reply_markup=time_presets_kb()
    )


# ================= ПРИВЯЗКА КАНАЛА =================
def _try_bind_channel(message, user_id: int, chat_id: int):
    try:
        chat = bot.get_chat(chat_id)
    except Exception as e:
        bot.send_message(message.chat.id,
                         f"❌ Не удалось получить информацию о канале: {e}")
        return

    if chat.type not in ("channel", "supergroup"):
        bot.send_message(message.chat.id,
                         "❌ Это не канал. Пришлите @username канала "
                         "или перешлите сообщение из канала.")
        return

    ok, err = verify_bot_in_channel(chat.id)
    if not ok:
        bot.send_message(message.chat.id, f"❌ {err}")
        return

    db_add_channel(user_id, chat.id, chat.title or "Без названия",
                   f"@{chat.username}" if chat.username else None)
    user_states.pop(user_id, None)
    bot.send_message(
        message.chat.id,
        f"✅ Канал привязан!\n\n"
        f"📢 <b>{chat.title}</b>\n"
        f"🆔 <code>{chat.id}</code>"
        + (f"\n🔗 @{chat.username}" if chat.username else ""),
        reply_markup=main_menu_kb()
    )
    log.info(f"Пользователь {user_id} привязал канал {chat.id} ({chat.title})")


# ================= ОБРАБОТЧИКИ СООБЩЕНИЙ =================
@bot.message_handler(content_types=["text"])
def on_text(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        bot.send_message(message.chat.id, "⛔ Нет доступа.")
        return
    st = user_states.get(uid)

    # Приоритет: форвард из канала во время ожидания привязки
    if (st and st["state"] == "waiting_channel"
            and message.forward_from_chat
            and message.forward_from_chat.type == "channel"):
        _try_bind_channel(message, uid, message.forward_from_chat.id)
        return

    # 1) Ждём @username канала
    if st and st["state"] == "waiting_channel":
        raw = message.text.strip()
        if not raw.startswith("@") or len(raw) < 2:
            bot.send_message(message.chat.id,
                             "❌ Пришлите @username канала "
                             "(например, <code>@my_channel</code>) "
                             "или перешлите сообщение из канала.",
                             reply_markup=cancel_kb())
            return
        _try_bind_channel(message, uid, raw)
        return

    # 2) Ручной ввод времени
    if st and st["state"] == "waiting_time_manual":
        try:
            publish_at = datetime.strptime(message.text.strip(),
                                           "%d.%m.%Y %H:%M")
        except ValueError:
            bot.send_message(message.chat.id,
                             "❌ Неверный формат. Пример: "
                             "<code>25.12.2025 18:30</code>",
                             reply_markup=cancel_kb())
            return
        if publish_at <= datetime.now():
            bot.send_message(message.chat.id, "❌ Время уже прошло.",
                             reply_markup=cancel_kb())
            return
        st["data"]["publish_at"] = publish_at
        st["state"] = "confirming"
        d = st["data"]
        icon = ICONS.get(d.get("content_type"), "📝")
        prev = preview_text(d.get("text", "")) or "(без текста)"
        bot.send_message(
            message.chat.id,
            f"📋 <b>Проверьте пост</b>\n\n"
            f"📢 Канал: <b>{d.get('channel_title', '—')}</b>\n"
            f"{icon} Тип: <b>{d.get('content_type', '—')}</b>\n"
            f"💬 Текст: {prev}\n"
            f"🕒 Время: <code>{publish_at.strftime('%d.%m.%Y %H:%M')}</code>",
            reply_markup=confirm_kb()
        )
        return

    # 3) Ждём содержимое поста (текст)
    if st and st["state"] == "waiting_content":
        if not message.text.strip():
            return
        _save_content_and_ask_time(message, uid, "text", message.text, None)
        return

    bot.send_message(message.chat.id, "Выберите действие 👇",
                     reply_markup=main_menu_kb())


@bot.message_handler(
    content_types=["photo", "video", "document", "audio",
                   "voice", "sticker", "animation"],
    func=lambda m: (m.forward_from_chat is not None
                    and m.forward_from_chat.type == "channel")
)
def on_forwarded_media(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    st = user_states.get(uid)
    if not st or st["state"] != "waiting_channel":
        return
    _try_bind_channel(message, uid, message.forward_from_chat.id)


def _is_forward(message) -> bool:
    return bool(getattr(message, "forward_from_chat", None)
                or getattr(message, "forward_from", None)
                or getattr(message, "forward_sender_name", None)
                or getattr(message, "forward_origin", None))


@bot.message_handler(content_types=["photo"])
def on_photo(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    if user_states.get(uid, {}).get("state") != "waiting_content":
        return
    if _is_forward(message):
        return
    _save_content_and_ask_time(message, uid, "photo",
                               message.caption, message.photo[-1].file_id)


@bot.message_handler(content_types=["video"])
def on_video(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    if user_states.get(uid, {}).get("state") != "waiting_content":
        return
    if _is_forward(message):
        return
    _save_content_and_ask_time(message, uid, "video",
                               message.caption, message.video.file_id)


@bot.message_handler(content_types=["document"])
def on_document(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    if user_states.get(uid, {}).get("state") != "waiting_content":
        return
    if _is_forward(message):
        return
    _save_content_and_ask_time(message, uid, "document",
                               message.caption, message.document.file_id)


@bot.message_handler(content_types=["audio"])
def on_audio(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    if user_states.get(uid, {}).get("state") != "waiting_content":
        return
    if _is_forward(message):
        return
    _save_content_and_ask_time(message, uid, "audio",
                               message.caption, message.audio.file_id)


@bot.message_handler(content_types=["voice"])
def on_voice(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    if user_states.get(uid, {}).get("state") != "waiting_content":
        return
    if _is_forward(message):
        return
    _save_content_and_ask_time(message, uid, "voice",
                               message.caption, message.voice.file_id)


@bot.message_handler(content_types=["sticker"])
def on_sticker(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    if user_states.get(uid, {}).get("state") != "waiting_content":
        return
    if _is_forward(message):
        return
    _save_content_and_ask_time(message, uid, "sticker", None,
                               message.sticker.file_id)


@bot.message_handler(content_types=["animation"])
def on_animation(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    if user_states.get(uid, {}).get("state") != "waiting_content":
        return
    if _is_forward(message):
        return
    _save_content_and_ask_time(message, uid, "animation",
                               message.caption, message.animation.file_id)


@bot.message_handler(content_types=["video_note"])
def on_video_note(message):
    uid = message.from_user.id
    if not is_allowed(uid):
        return
    if user_states.get(uid, {}).get("state") != "waiting_content":
        return
    if _is_forward(message):
        return
    _save_content_and_ask_time(message, uid, "video_note", None,
                               message.video_note.file_id)


# ================= ЗАПУСК =================
def main():
    db_init()

    worker = threading.Thread(target=schedule_worker, daemon=True)
    worker.start()

    log.info("Бот запущен. Ожидание обновлений...")
    bot.infinity_polling(timeout=30, long_polling_timeout=25)


if __name__ == "__main__":
    main()
