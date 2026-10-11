import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
import telebot
from telebot import apihelper, types

# Mechagram uses its own Bot API server.
SERVER_URL = os.getenv("SERVER_URL", "http://177.3.213.27:8081").rstrip("/")
apihelper.API_URL = f"{SERVER_URL}/bot{{0}}/{{1}}"
apihelper.FILE_URL = f"{SERVER_URL}/file/bot{{0}}/{{1}}"

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
if not SUPABASE_KEY:
    raise RuntimeError("Set SUPABASE_SERVICE_ROLE_KEY in Railway variables.")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")
POLL_SECONDS = max(2, int(os.getenv("POLL_SECONDS", "10")))
DATA_FILE = os.getenv("DATA_FILE", "/data/bot_data.json")
SCHEDULER_SECONDS = max(2, int(os.getenv("SCHEDULER_SECONDS", "5")))

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mechagram")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=True)

class Store:
    """Small, explicit PostgREST adapter. All database access stays server-side."""
    def __init__(self, url, key):
        self.base = url + "/rest/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def request(self, method, path, *, params=None, body=None, prefer=None):
        headers = {}
        if prefer:
            headers["Prefer"] = prefer
        response = self.session.request(
            method, self.base + "/" + path, params=params, json=body,
            headers=headers, timeout=25
        )
        if not response.ok:
            raise RuntimeError(f"Supabase {method} {path} failed ({response.status_code}): {response.text[:500]}")
        if not response.text:
            return []
        try:
            return response.json()
        except ValueError:
            return []

    def select(self, table, params=None):
        return self.request("GET", table, params=params or {"select": "*"})

    def insert(self, table, body, *, upsert=False):
        prefer = "return=representation"
        if upsert:
            prefer += ",resolution=merge-duplicates"
        return self.request("POST", table, params={"on_conflict": "chat_id"} if upsert else None,
                            body=body, prefer=prefer)

    def update(self, table, filters, body):
        params = {"select": "*"}
        params.update(filters)
        return self.request("PATCH", table, params=params, body=body, prefer="return=representation")

    def rpc(self, name, body=None):
        return self.request("POST", "rpc/" + name, body=body or {})

db = Store(SUPABASE_URL, SUPABASE_KEY)
sessions = {}
sessions_lock = threading.RLock()
album_buffers = {}
album_lock = threading.Lock()

def now_utc():
    return datetime.now(timezone.utc)

def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()

def parse_local_datetime(value, tz_name):
    dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)

def local_time(value, tz_name):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%d.%m.%Y %H:%M")

def get_user(user_id):
    rows = db.select("mechagram_users", {"select": "*", "telegram_id": f"eq.{int(user_id)}", "limit": "1"})
    return rows[0] if rows else None

def ensure_user(user_id):
    user = get_user(user_id)
    if user:
        return user
    rows = db.insert("mechagram_users", {"telegram_id": int(user_id), "timezone": DEFAULT_TIMEZONE})
    return rows[0] if rows else get_user(user_id)

def user_timezone(user_id):
    user = get_user(user_id)
    return (user or {}).get("timezone") or DEFAULT_TIMEZONE

def set_session(user_id, **data):
    with sessions_lock:
        sessions[int(user_id)] = {**sessions.get(int(user_id), {}), **data}

def get_session(user_id):
    with sessions_lock:
        return dict(sessions.get(int(user_id), {}))

def clear_session(user_id):
    with sessions_lock:
        sessions.pop(int(user_id), None)

def user_channels(user_id):
    return db.select("mechagram_channels", {
        "select": "*", "owner_telegram_id": f"eq.{int(user_id)}", "order": "created_at.asc", "limit": "100"
    })

def get_channel_for_user(channel_row_id, user_id):
    rows = db.select("mechagram_channels", {
        "select": "*", "id": f"eq.{int(channel_row_id)}",
        "owner_telegram_id": f"eq.{int(user_id)}", "limit": "1"
    })
    return rows[0] if rows else None

def bind_channel(user_id, chat_id, title, username=None):
    ensure_user(user_id)
    existing = db.select("mechagram_channels", {
        "select": "*", "chat_id": f"eq.{int(chat_id)}", "limit": "1"
    })
    payload = {
        "owner_telegram_id": int(user_id), "chat_id": int(chat_id),
        "title": title or "Канал", "username": username
    }
    if existing:
        rows = db.update("mechagram_channels", {"id": f"eq.{existing[0]['id']}"}, payload)
    else:
        rows = db.insert("mechagram_channels", payload)
    return rows[0] if rows else None

def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Запланировать", "📋 Мои публикации")
    kb.row("📣 Мои каналы", "⚙️ Настройки")
    return kb

def require_private(message):
    if not getattr(message, "from_user", None):
        return False
    if getattr(message.chat, "type", "private") != "private":
        return False
    ensure_user(message.from_user.id)
    return True

def require_admin_of_channel(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return getattr(member, "status", "") in ("administrator", "creator")
    except Exception:
        return False

def require_bot_admin(chat_id):
    try:
        me = bot.get_me()
        member = bot.get_chat_member(chat_id, me.id)
        return getattr(member, "status", "") in ("administrator", "creator")
    except Exception:
        return False

def channel_picker(user_id, action="new"):
    channels = user_channels(user_id)
    if not channels:
        bot.send_message(user_id, "Сначала подключите канал: добавьте бота администратором канала. Я привяжу его автоматически.")
        return
    kb = types.InlineKeyboardMarkup()
    for ch in channels:
        kb.add(types.InlineKeyboardButton(
            text=(ch.get("title") or str(ch["chat_id"]))[:60],
            callback_data=f"{action}:ch:{ch['id']}"
        ))
    bot.send_message(user_id, "Выберите канал для публикации:", reply_markup=kb)

def begin_new_post(user_id, channel):
    set_session(user_id, step="content", channel_id=channel["id"], content="", media=[], edit_post_id=None)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("❌ Отмена")
    bot.send_message(
        user_id,
        f"Канал: {channel['title']}\nПришлите текст, фото или видео. Подпись к фото/видео поддерживается; альбомы фото и видео тоже можно отправлять.\nПосле контента укажете время публикации.",
        reply_markup=kb
    )

def prompt_datetime(user_id, message):
    tz_name = user_timezone(user_id)
    bot.reply_to(
        message,
        f"Когда публиковать? Часовой пояс: {tz_name}\nФормат: ГГГГ-ММ-ДД ЧЧ:ММ\nПример: 2026-12-31 18:30\nДля повтора добавьте /daily или /weekly после времени. Для разовой публикации ничего добавлять не нужно."
    )

@bot.message_handler(commands=["start", "help"])
def start(message):
    if not require_private(message):
        return
    channels = user_channels(message.from_user.id)
    channel_text = "\n".join(f"• {c['title']} (ID {c['id']})" for c in channels) or "пока не подключены"
    bot.reply_to(
        message,
        "Привет! Я Mechagram — планировщик публикаций для нескольких каналов.\n\n"
        f"Ваши каналы:\n{channel_text}\n\n"
        "/new — создать публикацию\n/list — список публикаций\n"
        "/channels — подключённые каналы\n/timezone Europe/Berlin — часовой пояс\n"
        "/edit ID — изменить публикацию\n/cancel ID — отменить публикацию\n\n"
        "Добавьте меня администратором канала — он подключится автоматически.",
        reply_markup=main_keyboard()
    )

@bot.my_chat_member_handler()
def on_bot_membership(update):
    try:
        chat = update.chat
        actor = getattr(update, "from_user", None)
        member = getattr(update, "new_chat_member", None)
        status = getattr(member, "status", "")
        if getattr(chat, "type", None) != "channel" or status not in ("administrator", "creator") or not actor:
            return
        bind_channel(actor.id, chat.id, getattr(chat, "title", "Канал"), getattr(chat, "username", None))
        try:
            bot.send_message(actor.id, f"Канал «{getattr(chat, 'title', 'Канал')}» подключён. Отправьте /new, чтобы запланировать публикацию.")
        except Exception:
            log.info("Could not DM channel-adder %s; they may need to send /start first", actor.id)
        log.info("Channel %s bound to user %s", chat.id, actor.id)
    except Exception:
        log.exception("Failed to process channel membership update")

@bot.message_handler(commands=["bind"])
def bind_command(message):
    if not require_private(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        bot.reply_to(message, "Использование: /bind @channel_username")
        return
    try:
        chat = bot.get_chat(parts[1].strip())
        if getattr(chat, "type", "") != "channel":
            bot.reply_to(message, "Это не канал.")
            return
        if not require_admin_of_channel(chat.id, message.from_user.id):
            bot.reply_to(message, "Не удалось подтвердить, что вы администратор канала.")
            return
        if not require_bot_admin(chat.id):
            bot.reply_to(message, "Сначала добавьте бота администратором канала.")
            return
        bind_channel(message.from_user.id, chat.id, getattr(chat, "title", parts[1]), getattr(chat, "username", None))
        bot.reply_to(message, f"Канал «{getattr(chat, 'title', parts[1])}» подключён.", reply_markup=main_keyboard())
    except Exception:
        log.exception("Manual channel binding failed")
        bot.reply_to(message, "Не удалось подключить канал. Проверьте @username и права бота.")

@bot.message_handler(commands=["channels"])
@bot.message_handler(func=lambda m: m.text == "📣 Мои каналы")
def channels_command(message):
    if not require_private(message):
        return
    channels = user_channels(message.from_user.id)
    if not channels:
        bot.reply_to(message, "Каналов пока нет. Добавьте бота администратором в канал или используйте /bind @username.")
        return
    lines = ["Ваши каналы:"]
    for ch in channels:
        username = f" · @{ch['username']}" if ch.get("username") else ""
        lines.append(f"• {ch['title']}{username} · ID {ch['id']}")
    bot.reply_to(message, "\n".join(lines), reply_markup=main_keyboard())

@bot.message_handler(commands=["timezone"])
def timezone_command(message):
    if not require_private(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        bot.reply_to(message, "Пример: /timezone Europe/Berlin")
        return
    try:
        ZoneInfo(parts[1].strip())
        rows = db.update("mechagram_users", {"telegram_id": f"eq.{message.from_user.id}"}, {"timezone": parts[1].strip(), "updated_at": iso(now_utc())})
        if rows:
            bot.reply_to(message, f"Часовой пояс установлен: {parts[1].strip()}")
        else:
            bot.reply_to(message, "Не удалось сохранить часовой пояс. Отправьте /start и повторите.")
    except Exception:
        bot.reply_to(message, "Неизвестный часовой пояс. Пример: Europe/Moscow или Europe/Berlin.")

@bot.message_handler(commands=["new"])
@bot.message_handler(func=lambda m: m.text == "➕ Запланировать")
def new_command(message):
    if not require_private(message):
        return
    clear_session(message.from_user.id)
    channel_picker(message.from_user.id, "new")

@bot.message_handler(func=lambda m: m.text == "❌ Отмена")
def cancel_flow(message):
    if not require_private(message):
        return
    clear_session(message.from_user.id)
    bot.reply_to(message, "Действие отменено.", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        data = call.data or ""
        user_id = call.from_user.id
        ensure_user(user_id)
        if data.startswith("new:ch:") or data.startswith("edit:ch:"):
            action, _, channel_id = data.split(":", 2)
            channel = get_channel_for_user(channel_id, user_id)
            if not channel:
                bot.answer_callback_query(call.id, "Канал не найден или нет доступа.", show_alert=True)
                return
            bot.answer_callback_query(call.id, "Канал выбран.")
            if action == "new":
                begin_new_post(user_id, channel)
            else:
                session = get_session(user_id)
                post = session.get("edit_post")
                if not post:
                    bot.send_message(user_id, "Сессия редактирования истекла. Повторите /edit ID.")
                    return
                set_session(user_id, step="content", channel_id=channel["id"], content="", media=[], edit_post_id=post["id"])
                bot.send_message(user_id, "Пришлите новый текст, фото или видео для публикации. Затем укажите новое время.")
            return
        if data.startswith("post:"):
            _, action, post_id = data.split(":", 2)
            rows = db.select("mechagram_posts", {
                "select": "*", "id": f"eq.{int(post_id)}",
                "owner_telegram_id": f"eq.{user_id}", "limit": "1"
            })
            if not rows:
                bot.answer_callback_query(call.id, "Публикация не найдена.", show_alert=True)
                return
            post = rows[0]
            if action == "cancel":
                changed = db.update("mechagram_posts", {
                    "id": f"eq.{post['id']}", "owner_telegram_id": f"eq.{user_id}",
                    "status": "eq.pending"
                }, {"status": "cancelled", "updated_at": iso(now_utc())})
                bot.answer_callback_query(call.id, "Публикация отменена." if changed else "Уже отправлена или отменена.", show_alert=not bool(changed))
            elif action == "edit":
                if post["status"] != "pending":
                    bot.answer_callback_query(call.id, "Редактировать можно только ожидающие публикации.", show_alert=True)
                    return
                set_session(user_id, step="choose_edit_channel", edit_post=post)
                bot.answer_callback_query(call.id, "Выберите канал.")
                channel_picker(user_id, "edit")
            return
        bot.answer_callback_query(call.id, "Неизвестное действие.", show_alert=True)
    except Exception:
        log.exception("Callback failed")
        try:
            bot.answer_callback_query(call.id, "Не удалось выполнить действие.", show_alert=True)
        except Exception:
            pass

@bot.message_handler(commands=["list"])
@bot.message_handler(func=lambda m: m.text == "📋 Мои публикации")
def list_command(message):
    if not require_private(message):
        return
    posts = db.select("mechagram_posts", {
        "select": "*,mechagram_channels(title)",
        "owner_telegram_id": f"eq.{message.from_user.id}",
        "status": "in.(pending,failed)", "order": "scheduled_at.asc", "limit": "30"
    })
    if not posts:
        bot.reply_to(message, "Запланированных публикаций нет.", reply_markup=main_keyboard())
        return
    tz_name = user_timezone(message.from_user.id)
    for post in posts:
        channel = post.get("mechagram_channels") or {}
        title = channel.get("title", "Канал")
        text = post.get("text_content") or {"photo": "📷 Фото", "video": "🎬 Видео", "album": "🖼 Альбом"}.get(post.get("content_type"), "Текст")
        body = (f"Публикация #{post['id']}\nКанал: {title}\n"
                f"Время: {local_time(post['scheduled_at'], tz_name)}\n"
                f"Повтор: {post.get('recurrence', 'once')}\nСтатус: {post['status']}\n"
                f"Содержание: {text[:300]}")
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("✏️ Изменить", callback_data=f"post:edit:{post['id']}"),
            types.InlineKeyboardButton("❌ Отменить", callback_data=f"post:cancel:{post['id']}")
        )
        bot.send_message(message.chat.id, body, reply_markup=kb)
    bot.send_message(message.chat.id, "Конец списка.", reply_markup=main_keyboard())

@bot.message_handler(commands=["cancel"])
def cancel_post_command(message):
    if not require_private(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(message, "Использование: /cancel ID")
        return
    changed = db.update("mechagram_posts", {
        "id": f"eq.{int(parts[1])}", "owner_telegram_id": f"eq.{message.from_user.id}",
        "status": "eq.pending"
    }, {"status": "cancelled", "updated_at": iso(now_utc())})
    bot.reply_to(message, "Публикация отменена." if changed else "Ожидающая публикация с таким ID не найдена.", reply_markup=main_keyboard())

@bot.message_handler(commands=["edit"])
def edit_post_command(message):
    if not require_private(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(message, "Использование: /edit ID")
        return
    rows = db.select("mechagram_posts", {
        "select": "*", "id": f"eq.{int(parts[1])}",
        "owner_telegram_id": f"eq.{message.from_user.id}", "status": "eq.pending", "limit": "1"
    })
    if not rows:
        bot.reply_to(message, "Ожидающая публикация не найдена.")
        return
    set_session(message.from_user.id, step="choose_edit_channel", edit_post=rows[0])
    channel_picker(message.from_user.id, "edit")

@bot.message_handler(func=lambda m: m.text == "⚙️ Настройки")
def settings_command(message):
    if not require_private(message):
        return
    bot.reply_to(message, f"Часовой пояс: {user_timezone(message.from_user.id)}\nИзменить: /timezone Europe/Berlin\nДобавить канал: добавьте бота администратором в канал или /bind @username", reply_markup=main_keyboard())

def save_content_from_message(message, session):
    media = list(session.get("media") or [])
    caption = session.get("content") or ""
    if message.media_group_id:
        key = (message.from_user.id, str(message.media_group_id))
        with album_lock:
            entry = album_buffers.setdefault(key, {"messages": [], "timer": None, "session": session})
            entry["messages"].append(message)
            if entry["timer"]:
                entry["timer"].cancel()
            entry["timer"] = threading.Timer(1.4, flush_album, args=(key,))
            entry["timer"].daemon = True
            entry["timer"].start()
        return
    if message.text is not None:
        caption = message.text
    elif message.photo:
        media = [{"type": "photo", "file_id": message.photo[-1].file_id}]
        caption = message.caption or ""
    elif message.video:
        media = [{"type": "video", "file_id": message.video.file_id}]
        caption = message.caption or ""
    else:
        return
    set_session(message.from_user.id, step="datetime", content=caption, media=media)
    prompt_datetime(message.from_user.id, message)

def flush_album(key):
    with album_lock:
        entry = album_buffers.pop(key, None)
    if not entry:
        return
    messages = sorted(entry["messages"], key=lambda m: m.message_id)
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
        return
    user_id = messages[0].from_user.id
    set_session(user_id, step="datetime", content=caption, media=media[:10])
    bot.send_message(user_id, f"Когда публиковать? Часовой пояс: {user_timezone(user_id)}\nФормат: ГГГГ-ММ-ДД ЧЧ:ММ\nДобавьте /daily или /weekly для повтора.")

@bot.message_handler(content_types=["text", "photo", "video"])
def content_handler(message):
    if not require_private(message):
        return
    text = message.text or ""
    if text.startswith("/"):
        return
    if text == "❌ Отмена":
        return
    session = get_session(message.from_user.id)
    if not session:
        return
    if session.get("step") == "content":
        save_content_from_message(message, session)
        return
    if session.get("step") != "datetime" or not message.text:
        return
    raw = message.text.strip()
    recurrence = "daily" if re.search(r"(?i)\s*/daily\b", raw) else ("weekly" if re.search(r"(?i)\s*/weekly\b", raw) else "once")
    cleaned = re.sub(r"(?i)\s*/(?:daily|weekly)\b", "", raw).strip()
    try:
        scheduled_at = parse_local_datetime(cleaned, user_timezone(message.from_user.id))
        if scheduled_at <= now_utc():
            bot.reply_to(message, "Это время уже прошло. Введите будущую дату и время.")
            return
        channel = get_channel_for_user(session["channel_id"], message.from_user.id)
        if not channel:
            clear_session(message.from_user.id)
            bot.reply_to(message, "Канал не найден. Начните заново с /new.")
            return
        edit_id = session.get("edit_post_id")
        content_type = "album" if len(session.get("media") or []) > 1 else ((session.get("media") or [{}])[0].get("type", "text"))
        payload = {
            "owner_telegram_id": message.from_user.id, "channel_id": channel["id"],
            "content_type": content_type, "text_content": session.get("content") or "",
            "media": session.get("media") or [], "scheduled_at": iso(scheduled_at),
            "recurrence": recurrence, "status": "pending", "error_message": None,
            "updated_at": iso(now_utc())
        }
        if edit_id:
            changed = db.update("mechagram_posts", {
                "id": f"eq.{int(edit_id)}", "owner_telegram_id": f"eq.{message.from_user.id}",
                "status": "eq.pending"
            }, {k: v for k, v in payload.items() if k != "owner_telegram_id"})
            if not changed:
                bot.reply_to(message, "Публикация уже не ожидает отправки, изменения не сохранены.")
            else:
                bot.reply_to(message, f"Публикация #{edit_id} обновлена.", reply_markup=main_keyboard())
        else:
            rows = db.insert("mechagram_posts", payload)
            bot.reply_to(message, f"Публикация #{rows[0]['id']} запланирована." if rows else "Публикация сохранена.", reply_markup=main_keyboard())
        clear_session(message.from_user.id)
    except ValueError:
        bot.reply_to(message, "Не понял дату. Формат: 2026-12-31 18:30, необязательно с /daily или /weekly.")
    except Exception:
        log.exception("Could not save scheduled post")
        bot.reply_to(message, "Не удалось сохранить публикацию. Проверьте подключение к базе и повторите.")

def publish_post(post):
    channel = db.select("mechagram_channels", {"select": "*", "id": f"eq.{post['channel_id']}", "limit": "1"})
    if not channel:
        raise RuntimeError("Канал удалён или больше не подключён.")
    chat_id = int(channel[0]["chat_id"])
    content = post.get("text_content") or ""
    media = post.get("media") or []
    if not media:
        bot.send_message(chat_id, content)
    elif len(media) == 1 and media[0]["type"] == "photo":
        kwargs = {"chat_id": chat_id, "photo": media[0]["file_id"]}
        if content:
            kwargs["caption"] = content
        bot.send_photo(**kwargs)
    elif len(media) == 1 and media[0]["type"] == "video":
        kwargs = {"chat_id": chat_id, "video": media[0]["file_id"]}
        if content:
            kwargs["caption"] = content
        bot.send_video(**kwargs)
    else:
        group = []
        for index, item in enumerate(media[:10]):
            caption = content if index == 0 else None
            if item["type"] == "photo":
                group.append(types.InputMediaPhoto(media=item["file_id"], caption=caption))
            elif item["type"] == "video":
                group.append(types.InputMediaVideo(media=item["file_id"], caption=caption))
        if group:
            bot.send_media_group(chat_id, group)
        else:
            bot.send_message(chat_id, content)

def scheduler_loop():
    log.info("Scheduler started; polling every %s seconds", SCHEDULER_SECONDS)
    while True:
        try:
            # Recover jobs abandoned by a process restart, without touching recent claims.
            stale = (now_utc() - timedelta(minutes=10)).isoformat()
            db.update("mechagram_posts", {
                "status": "eq.sending", "updated_at": f"lt.{stale}"
            }, {"status": "pending", "updated_at": iso(now_utc())})
            posts = db.rpc("mechagram_claim_due_posts")
            for post in posts or []:
                try:
                    publish_post(post)
                    recurrence = post.get("recurrence", "once")
                    if recurrence in ("daily", "weekly"):
                        tz_name = user_timezone(post["owner_telegram_id"])
                        local_dt = datetime.fromisoformat(post["scheduled_at"].replace("Z", "+00:00")).astimezone(ZoneInfo(tz_name))
                        next_local = local_dt + timedelta(days=1 if recurrence == "daily" else 7)
                        db.update("mechagram_posts", {"id": f"eq.{post['id']}", "status": "eq.sending"}, {
                            "status": "pending", "scheduled_at": iso(next_local), "sent_at": iso(now_utc()),
                            "error_message": None, "updated_at": iso(now_utc())
                        })
                    else:
                        db.update("mechagram_posts", {"id": f"eq.{post['id']}", "status": "eq.sending"}, {
                            "status": "sent", "sent_at": iso(now_utc()), "error_message": None,
                            "updated_at": iso(now_utc())
                        })
                    log.info("Published scheduled post id=%s", post["id"])
                except Exception as exc:
                    log.exception("Publishing post id=%s failed", post.get("id"))
                    db.update("mechagram_posts", {"id": f"eq.{post['id']}", "status": "eq.sending"}, {
                        "status": "failed", "error_message": str(exc)[:1000], "updated_at": iso(now_utc())
                    })
                    try:
                        bot.send_message(int(post["owner_telegram_id"]), f"Не удалось опубликовать #{post['id']}: {str(exc)[:300]}\nИсправьте проблему и создайте публикацию заново.")
                    except Exception:
                        pass
        except Exception:
            log.exception("Scheduler iteration failed")
        time.sleep(SCHEDULER_SECONDS)


def import_legacy_json():
    """One-time, idempotent import from the persistent JSON volume used by the old bot."""
    if not os.path.isfile(DATA_FILE):
        log.info("No legacy JSON file at %s; skipping import", DATA_FILE)
        return
    marker = db.select("mechagram_imports", {
        "select": "source", "source": "eq.legacy_json_v1", "limit": "1"
    })
    if marker:
        log.info("Legacy JSON import already completed")
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as stream:
            legacy = json.load(stream)
    except Exception:
        log.exception("Could not read legacy JSON; startup will continue without importing it")
        return
    imported_users, imported_channels, imported_posts = set(), 0, 0
    settings_rows = legacy.get("bot_settings") or []
    settings = settings_rows[0] if settings_rows else {}
    owner = settings.get("owner_telegram_id")
    timezone_name = settings.get("timezone") or DEFAULT_TIMEZONE
    channel_by_chat = {}
    if owner:
        owner = int(owner)
        ensure_user(owner)
        db.update("mechagram_users", {"telegram_id": "eq." + str(owner)}, {"timezone": timezone_name})
        imported_users.add(owner)
        if settings.get("channel_id"):
            ch = bind_channel(owner, int(settings["channel_id"]),
                              settings.get("channel_title") or "Импортированный канал",
                              settings.get("channel_username"))
            if ch:
                channel_by_chat[str(settings["channel_id"])] = ch
                imported_channels += 1
    for old in legacy.get("scheduled_posts") or []:
        try:
            old_id = int(old.get("id"))
            old_owner = int(old["owner_telegram_id"])
            raw_chat_id = old.get("channel_id") or settings.get("channel_id")
            if not raw_chat_id or old_id < 1:
                continue
            chat_id = int(raw_chat_id)
            ensure_user(old_owner)
            imported_users.add(old_owner)
            ch = channel_by_chat.get(str(chat_id))
            if not ch:
                found = db.select("mechagram_channels", {
                    "select": "*", "chat_id": "eq." + str(chat_id),
                    "owner_telegram_id": "eq." + str(old_owner), "limit": "1"
                })
                ch = found[0] if found else bind_channel(old_owner, chat_id, "Импортированный канал")
                if ch:
                    channel_by_chat[str(chat_id)] = ch
                    imported_channels += 1
            if not ch:
                continue
            already = db.select("mechagram_posts", {
                "select": "id", "legacy_post_id": "eq." + str(old_id), "limit": "1"
            })
            if already:
                continue
            media = old.get("media") or []
            content = old.get("content") or ""
            media_types = {item.get("type") for item in media}
            content_type = "album" if len(media) > 1 else (next(iter(media_types)) if media_types else "text")
            if content_type not in ("text", "photo", "video", "album"):
                content_type = "text"
            status = old.get("status", "pending")
            if status not in ("pending", "sent", "cancelled", "failed"):
                status = "pending"
            recurrence = old.get("recurrence", "once")
            if recurrence not in ("once", "daily", "weekly"):
                recurrence = "once"
            scheduled_at = old.get("publish_at") or old.get("scheduled_at")
            if not scheduled_at:
                continue
            db.insert("mechagram_posts", {
                "legacy_post_id": old_id, "owner_telegram_id": old_owner,
                "channel_id": ch["id"], "content_type": content_type,
                "text_content": content, "media": media, "scheduled_at": scheduled_at,
                "recurrence": recurrence, "status": status,
                "error_message": old.get("error_message"), "sent_at": old.get("sent_at")
            })
            imported_posts += 1
        except Exception:
            log.exception("Skipping legacy post id=%s during import", old.get("id"))
    db.insert("mechagram_imports", {
        "source": "legacy_json_v1",
        "details": {"users_seen": len(imported_users), "channels_seen": imported_channels, "posts_imported": imported_posts}
    })
    log.info("Legacy import finished: users=%s channels=%s posts=%s",
             len(imported_users), imported_channels, imported_posts)

def main():
    # Fail fast if credentials, API access, and the schema are available.
    db.select("mechagram_users", {"select": "telegram_id", "limit": "1"})
    db.select("mechagram_imports", {"select": "source", "limit": "1"})
    import_legacy_json()
    me = bot.get_me()
    log.info("Mechagram Bot API connected as @%s", getattr(me, "username", None) or "unknown")
    threading.Thread(target=scheduler_loop, name="scheduler", daemon=True).start()
    log.info("Mechagram starting; custom API=%s; Supabase=%s", SERVER_URL, SUPABASE_URL)
    bot.infinity_polling(
        timeout=30, long_polling_timeout=25, skip_pending=False,
        allowed_updates=["message", "channel_post", "my_chat_member", "callback_query"]
    )

if __name__ == "__main__":
    main()
