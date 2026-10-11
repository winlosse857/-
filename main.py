import os
import time
import json
import threading
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import telebot
from telebot import types
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scheduler-bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
OWNER_SETUP_CODE = os.environ["OWNER_SETUP_CODE"]
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "10"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
db: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Simple per-user conversation state; durable scheduled posts are stored in Supabase.
sessions = {}
session_lock = threading.Lock()
album_buffers = {}
album_lock = threading.Lock()


def utcnow():
    return datetime.now(timezone.utc)


def settings_row():
    result = db.table("bot_settings").select("*").limit(1).execute()
    return result.data[0] if result.data else None


def owner_id():
    row = settings_row()
    return int(row["owner_telegram_id"]) if row and row.get("owner_telegram_id") else None


def is_owner(user_id):
    return owner_id() == int(user_id)


def set_session(user_id, **values):
    with session_lock:
        sessions.setdefault(user_id, {}).update(values)


def get_session(user_id):
    with session_lock:
        return dict(sessions.get(user_id, {}))


def clear_session(user_id):
    with session_lock:
        sessions.pop(user_id, None)


def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Запланировать", "📋 Мои публикации")
    kb.row("📣 Подключить канал", "⚙️ Настройки")
    return kb


def require_owner(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "Доступ закрыт. Сначала активируйте бота командой /start КОД_АКТИВАЦИИ.")
        return False
    return True


def parse_local_datetime(value, timezone_name):
    # Accepted: YYYY-MM-DD HH:MM
    dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc)


def human_time(value, timezone_name):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(timezone_name)).strftime("%d.%m.%Y %H:%M")


def save_channel(channel_id, title, username=None):
    row = settings_row()
    if not row:
        raise RuntimeError("Бот ещё не активирован.")
    db.table("bot_settings").update({
        "channel_id": str(channel_id),
        "channel_title": title,
        "channel_username": username,
    }).eq("id", row["id"]).execute()


def verify_bot_admin(chat_id):
    me = bot.get_me()
    member = bot.get_chat_member(chat_id, me.id)
    status = getattr(member, "status", "")
    return status in ("administrator", "creator")


def verify_user_admin(chat_id, user_id):
    member = bot.get_chat_member(chat_id, user_id)
    return getattr(member, "status", "") in ("administrator", "creator")


def current_channel():
    row = settings_row()
    if row and row.get("channel_id"):
        return row
    return None


@bot.message_handler(commands=["start"])
def start(message):
    parts = (message.text or "").split(maxsplit=1)
    current_owner = owner_id()
    if current_owner is None:
        if len(parts) != 2 or parts[1].strip() != OWNER_SETUP_CODE:
            bot.reply_to(message, "Для первой активации отправьте: /start КОД_АКТИВАЦИИ\nКод задаётся в переменной OWNER_SETUP_CODE на Railway.")
            return
        # A unique row with a fixed singleton id ensures one initial owner.
        try:
            db.table("bot_settings").insert({
                "id": 1,
                "owner_telegram_id": message.from_user.id,
                "timezone": DEFAULT_TIMEZONE
            }).execute()
        except Exception:
            # Another activation may have won the race; never overwrite its owner.
            pass
        if not is_owner(message.from_user.id):
            bot.reply_to(message, "Активация уже выполнена другим пользователем. Обратитесь к владельцу.")
            return
        bot.reply_to(message, "Бот активирован. Вы — владелец.\nДобавьте бота администратором канала, затем подключите канал кнопкой «📣 Подключить канал» или командой /bind @username.", reply_markup=main_keyboard())
        return
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "Этот бот приватный и доступен только владельцу.")
        return
    bot.reply_to(message, "Привет! Я планировщик публикаций.\n\n/bind @channel — подключить канал\n/new — создать публикацию\n/list — список запланированных\n/timezone Europe/Moscow — часовой пояс", reply_markup=main_keyboard())


@bot.message_handler(commands=["bind"])
def bind(message):
    if not require_owner(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Укажите публичный @username канала: /bind @my_channel\nДля приватного канала опубликуйте в нём сообщение с командой /bindchannel после добавления бота администратором.")
        return
    target = parts[1].strip()
    try:
        chat = bot.get_chat(target)
        if chat.type != "channel":
            bot.reply_to(message, "Это не канал Telegram.")
            return
        if not verify_user_admin(chat.id, message.from_user.id):
            bot.reply_to(message, "Ваш аккаунт не распознан как администратор этого канала.")
            return
        if not verify_bot_admin(chat.id):
            bot.reply_to(message, "Сначала добавьте бота администратором канала и повторите команду.")
            return
        save_channel(chat.id, getattr(chat, "title", str(target)), getattr(chat, "username", None))
        bot.reply_to(message, f"Канал подключён: {getattr(chat, 'title', target)}", reply_markup=main_keyboard())
    except Exception as exc:
        log.exception("Channel bind failed")
        bot.reply_to(message, f"Не удалось подключить канал. Проверьте @username и права бота.\nТехническая ошибка: {str(exc)[:250]}")


@bot.channel_post_handler(commands=["bindchannel"])
def bind_from_channel(message):
    row = settings_row()
    if not row:
        return
    # This command is useful for private channels. The owner must first activate the bot.
    try:
        if not verify_bot_admin(message.chat.id):
            return
        save_channel(message.chat.id, getattr(message.chat, "title", "Канал"), getattr(message.chat, "username", None))
        bot.send_message(int(row["owner_telegram_id"]), f"Канал подключён из сообщения в канале: {message.chat.title} ({message.chat.id}).")
    except Exception:
        log.exception("Channel-post binding failed")


@bot.message_handler(commands=["timezone"])
def timezone_cmd(message):
    if not require_owner(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        bot.reply_to(message, "Пример: /timezone Europe/Moscow")
        return
    try:
        ZoneInfo(parts[1].strip())
        row = settings_row()
        db.table("bot_settings").update({"timezone": parts[1].strip()}).eq("id", row["id"]).execute()
        bot.reply_to(message, f"Часовой пояс установлен: {parts[1].strip()}")
    except Exception:
        bot.reply_to(message, "Неизвестный часовой пояс. Используйте, например, Europe/Moscow или Europe/Berlin.")


@bot.message_handler(commands=["new"])
def new_post(message):
    if not require_owner(message):
        return
    if not current_channel():
        bot.reply_to(message, "Сначала подключите канал: /bind @username")
        return
    set_session(message.from_user.id, step="content", media=[])
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("❌ Отмена")
    bot.reply_to(message, "Пришлите текст, фото или видео для публикации. Для альбома отправьте несколько фото/видео одним альбомом. Подпись к медиа поддерживается.", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "➕ Запланировать")
def new_post_button(message):
    new_post(message)


@bot.message_handler(func=lambda m: m.text == "❌ Отмена")
def cancel(message):
    clear_session(message.from_user.id)
    bot.reply_to(message, "Действие отменено.", reply_markup=main_keyboard())


@bot.message_handler(commands=["list"])
@bot.message_handler(func=lambda m: m.text == "📋 Мои публикации")
def list_posts(message):
    if not require_owner(message):
        return
    row = settings_row()
    result = db.table("scheduled_posts").select("*").eq("owner_telegram_id", message.from_user.id).in_("status", ["pending", "failed"]).order("publish_at").limit(20).execute()
    posts = result.data or []
    if not posts:
        bot.reply_to(message, "Запланированных публикаций нет.", reply_markup=main_keyboard())
        return
    lines = ["Ваши публикации:"]
    for p in posts:
        lines.append(f"#{p['id']} · {human_time(p['publish_at'], row['timezone'])} · {p['status']} · {p['content'][:55].replace(chr(10), ' ')}")
    lines.append("\nОтменить: /cancel ID")
    bot.reply_to(message, "\n".join(lines), reply_markup=main_keyboard())


@bot.message_handler(commands=["cancel"])
def cancel_post(message):
    if not require_owner(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(message, "Использование: /cancel ID")
        return
    result = db.table("scheduled_posts").update({"status": "cancelled"}).eq("id", int(parts[1])).eq("owner_telegram_id", message.from_user.id).eq("status", "pending").execute()
    bot.reply_to(message, "Публикация отменена." if result.data else "Не найдено ожидающей публикации с таким ID.")


@bot.message_handler(func=lambda m: m.text == "📣 Подключить канал")
def connect_help(message):
    if not require_owner(message):
        return
    bot.reply_to(message, "Публичный канал: отправьте /bind @username в личном чате с ботом.\nПриватный канал: добавьте бота администратором и опубликуйте в канале отдельное сообщение /bindchannel. Бот сообщит вам, когда канал подключён.")


@bot.message_handler(func=lambda m: m.text == "⚙️ Настройки")
def settings(message):
    if not require_owner(message):
        return
    row = settings_row()
    channel = row.get("channel_title") or "не подключён"
    bot.reply_to(message, f"Канал: {channel}\nЧасовой пояс: {row['timezone']}\n\nИзменить часовой пояс: /timezone Europe/Berlin")


def finish_content(message, content, media):
    user_id = message.from_user.id
    set_session(user_id, step="datetime", content=content, media=media)
    row = settings_row()
    bot.reply_to(message, f"Когда публиковать? Введите дату и время в часовом поясе {row['timezone']}.\nФормат: ГГГГ-ММ-ДД ЧЧ:ММ\nНапример: 2026-12-31 18:30\n\nДля ежедневной публикации добавьте /daily после даты: 2026-12-31 18:30 /daily")


@bot.message_handler(content_types=["text", "photo", "video", "document", "animation"])
def handle_content(message):
    if message.from_user is None or not is_owner(message.from_user.id):
        return
    if message.text and message.text.startswith("/"):
        return
    session = get_session(message.from_user.id)
    if not session:
        return
    if session.get("step") == "content":
        if message.media_group_id:
            group_key = (message.from_user.id, str(message.media_group_id))
            with album_lock:
                entry = album_buffers.setdefault(group_key, {"messages": [], "timer": None})
                entry["messages"].append(message)
                if entry["timer"]:
                    entry["timer"].cancel()
                entry["timer"] = threading.Timer(1.5, flush_album, args=(group_key,))
                entry["timer"].daemon = True
                entry["timer"].start()
            return
        if message.text:
            finish_content(message, message.text, [])
        elif message.photo:
            media = [{"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption or ""}]
            finish_content(message, message.caption or "[Фото]", media)
        elif message.video:
            media = [{"type": "video", "file_id": message.video.file_id, "caption": message.caption or ""}]
            finish_content(message, message.caption or "[Видео]", media)
        elif message.document:
            media = [{"type": "document", "file_id": message.document.file_id, "caption": message.caption or ""}]
            finish_content(message, message.caption or "[Файл]", media)
        elif message.animation:
            media = [{"type": "animation", "file_id": message.animation.file_id, "caption": message.caption or ""}]
            finish_content(message, message.caption or "[Анимация]", media)
    elif session.get("step") == "datetime" and message.text:
        row = settings_row()
        daily = "/daily" in message.text.lower()
        cleaned = message.text.replace("/daily", "").replace("/DAILY", "").strip()
        try:
            publish_at = parse_local_datetime(cleaned, row["timezone"])
            if publish_at <= utcnow():
                bot.reply_to(message, "Это время уже прошло. Введите будущую дату и время.")
                return
            db.table("scheduled_posts").insert({
                "owner_telegram_id": message.from_user.id,
                "channel_id": str(row["channel_id"]),
                "content": session["content"],
                "media": session.get("media", []),
                "publish_at": publish_at.isoformat(),
                "recurrence": "daily" if daily else "once",
                "status": "pending"
            }).execute()
            clear_session(message.from_user.id)
            bot.reply_to(message, "Публикация запланирована" + (" ежедневно." if daily else "."), reply_markup=main_keyboard())
        except ValueError:
            bot.reply_to(message, "Не понял дату. Формат: 2026-12-31 18:30 (и необязательно /daily).")
        except Exception:
            log.exception("Could not schedule post")
            bot.reply_to(message, "Не удалось сохранить публикацию. Проверьте настройки Supabase и логи Railway.")


def flush_album(group_key):
    with album_lock:
        entry = album_buffers.pop(group_key, None)
    if not entry or not entry["messages"]:
        return
    messages = sorted(entry["messages"], key=lambda m: m.message_id)
    first = messages[0]
    media = []
    caption = ""
    for msg in messages:
        if msg.caption and not caption:
            caption = msg.caption
        if msg.photo:
            media.append({"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""})
        elif msg.video:
            media.append({"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""})
    if not media:
        bot.reply_to(first, "Не удалось распознать элементы альбома. Попробуйте отправить фото/видео ещё раз.")
        return
    finish_content(first, caption or "[Альбом]", media[:10])


def publish_post(post):
    channel_id = post["channel_id"]
    media = post.get("media") or []
    if len(media) == 1:
        item = media[0]
        caption = item.get("caption") or post["content"]
        if item["type"] == "photo":
            bot.send_photo(channel_id, item["file_id"], caption=caption)
        elif item["type"] == "video":
            bot.send_video(channel_id, item["file_id"], caption=caption)
        elif item["type"] == "document":
            bot.send_document(channel_id, item["file_id"], caption=caption)
        elif item["type"] == "animation":
            bot.send_animation(channel_id, item["file_id"], caption=caption)
        else:
            bot.send_message(channel_id, post["content"])
    elif len(media) > 1:
        group = []
        for i, item in enumerate(media[:10]):
            caption = item.get("caption", "") if i == 0 else None
            if item["type"] == "photo":
                group.append(types.InputMediaPhoto(item["file_id"], caption=caption))
            elif item["type"] == "video":
                group.append(types.InputMediaVideo(item["file_id"], caption=caption))
        if group:
            bot.send_media_group(channel_id, group)
        else:
            bot.send_message(channel_id, post["content"])
    else:
        bot.send_message(channel_id, post["content"])


def scheduler_loop():
    while True:
        try:
            due = db.table("scheduled_posts").select("*").eq("status", "pending").lte("publish_at", utcnow().isoformat()).order("publish_at").limit(10).execute().data or []
            for post in due:
                # Conditional update is a best-effort claim. Run a single Railway replica to avoid duplicate delivery.
                claim = db.table("scheduled_posts").update({"status": "publishing"}).eq("id", post["id"]).eq("status", "pending").execute()
                if not claim.data:
                    continue
                try:
                    publish_post(post)
                    if post.get("recurrence") == "daily":
                        next_time = datetime.fromisoformat(post["publish_at"].replace("Z", "+00:00")) + timedelta(days=1)
                        db.table("scheduled_posts").update({
                            "status": "pending", "publish_at": next_time.isoformat(),
                            "published_at": utcnow().isoformat(), "error": None
                        }).eq("id", post["id"]).execute()
                    else:
                        db.table("scheduled_posts").update({
                            "status": "published", "published_at": utcnow().isoformat(), "error": None
                        }).eq("id", post["id"]).execute()
                    bot.send_message(int(post["owner_telegram_id"]), f"Публикация #{post['id']} отправлена в канал.")
                except Exception as exc:
                    log.exception("Publishing post %s failed", post["id"])
                    db.table("scheduled_posts").update({"status": "failed", "error": str(exc)[:1000]}).eq("id", post["id"]).execute()
                    try:
                        bot.send_message(int(post["owner_telegram_id"]), f"Не удалось опубликовать #{post['id']}: {str(exc)[:300]}\nПроверьте права бота и статус публикации командой /list.")
                    except Exception:
                        pass
        except Exception:
            log.exception("Scheduler iteration failed")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    threading.Thread(target=scheduler_loop, daemon=True).start()
    log.info("Bot polling started")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
