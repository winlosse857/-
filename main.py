import os
import time
import json
import threading
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import telebot
from telebot import types, apihelper

# Mechagram uses a custom Bot API server, not api.telegram.org.
SERVER_URL = "http://177.3.213.27:8081"
apihelper.API_URL = f"{SERVER_URL}/bot{{0}}/{{1}}"
apihelper.FILE_URL = f"{SERVER_URL}/file/bot{{0}}/{{1}}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scheduler-bot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_SETUP_CODE = os.environ["OWNER_SETUP_CODE"]
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "10"))
DATA_FILE = os.getenv("DATA_FILE", "/data/bot_data.json")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)


# Small JSON-backed replacement for the Supabase query calls used below.
# Set DATA_FILE to a path on a Railway Volume (recommended: /data/bot_data.json).
class JsonResult:
    def __init__(self, data):
        self.data = data


class JsonQuery:
    def __init__(self, store, table, operation="select", payload=None):
        self.store, self.table, self.operation, self.payload = store, table, operation, payload
        self.filters, self.sort_key, self.sort_desc, self.max_rows = [], None, False, None

    def select(self, *_args):
        self.operation = "select"
        return self

    def insert(self, payload):
        self.operation, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.operation, self.payload = "update", payload
        return self

    def eq(self, key, value):
        self.filters.append(("eq", key, value))
        return self

    def in_(self, key, values):
        self.filters.append(("in", key, values))
        return self

    def lte(self, key, value):
        self.filters.append(("lte", key, value))
        return self

    def order(self, key, desc=False):
        self.sort_key, self.sort_desc = key, desc
        return self

    def limit(self, count):
        self.max_rows = count
        return self

    def _matches(self, row):
        for op, key, value in self.filters:
            current = row.get(key)
            if op == "eq" and str(current) != str(value):
                return False
            if op == "in" and current not in value:
                return False
            if op == "lte" and (current is None or str(current) > str(value)):
                return False
        return True

    def execute(self):
        with self.store.lock:
            rows = self.store.data.setdefault(self.table, [])
            if self.operation == "insert":
                incoming = self.payload if isinstance(self.payload, list) else [self.payload]
                inserted = []
                for source in incoming:
                    row = dict(source)
                    if self.table == "scheduled_posts" and not row.get("id"):
                        row["id"] = max([int(r.get("id", 0)) for r in rows] + [0]) + 1
                    if self.table == "bot_settings" and any(r.get("id") == row.get("id") for r in rows):
                        continue
                    rows.append(row)
                    inserted.append(dict(row))
                self.store._save()
                return JsonResult(inserted)
            matched = [row for row in rows if self._matches(row)]
            if self.operation == "update":
                changed = []
                for row in matched:
                    row.update(self.payload or {})
                    changed.append(dict(row))
                if changed:
                    self.store._save()
                return JsonResult(changed)
            result = [dict(row) for row in matched]
            if self.sort_key:
                result.sort(key=lambda row: row.get(self.sort_key) or "", reverse=self.sort_desc)
            if self.max_rows is not None:
                result = result[:self.max_rows]
            return JsonResult(result)


class JsonStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.data = {"bot_settings": [], "scheduled_posts": []}
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        try:
            with open(path, "r", encoding="utf-8") as stream:
                loaded = json.load(stream)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except FileNotFoundError:
            self._save()

    def _save(self):
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(self.data, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, self.path)

    def table(self, name):
        return JsonQuery(self, name)

# Conversation state is temporary; scheduled posts and settings are stored in JSON.
db = JsonStore(DATA_FILE)
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
        cleaned = re.sub(r"(?i)\\s*/daily\\b", "", message.text).strip()
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
            bot.reply_to(message, "Не удалось сохранить публикацию. Проверьте логи Railway и доступность файла данных.")


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
                        settings = settings_row() or {}
                        timezone_name = settings.get("timezone", DEFAULT_TIMEZONE)
                        published_utc = datetime.fromisoformat(post["publish_at"].replace("Z", "+00:00"))
                        published_local = published_utc.astimezone(ZoneInfo(timezone_name))
                        next_local = (published_local.replace(tzinfo=None) + timedelta(days=1)).replace(tzinfo=ZoneInfo(timezone_name))
                        next_time = next_local.astimezone(timezone.utc)
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
