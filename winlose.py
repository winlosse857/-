import os
import random
import sqlite3
import time
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============ НАСТРОЙКИ ============
TOKEN = os.environ.get("BOT_TOKEN")
SERVER_URL = os.environ.get("SERVER_URL", "http://177.3.213.27:8081")
DB_PATH = os.environ.get("DB_PATH", "casino.db")

if not TOKEN:
    raise SystemExit("❌ Не задана переменная окружения BOT_TOKEN")

apihelper.API_URL = f"{SERVER_URL}/bot{{0}}/{{1}}"
apihelper.FILE_URL = f"{SERVER_URL}/file/bot{{0}}/{{1}}"

bot = telebot.TeleBot(TOKEN)

# ============ КОНСТАНТЫ ИГР ============
START_BALANCE = 100
DAILY_BONUS_MIN = 50
DAILY_BONUS_MAX = 150
DAILY_COOLDOWN = 24 * 60 * 60

SLOT_BET = 50
DICE_BET = 25
COIN_BET = 10

# ============ БАЗА ДАННЫХ ============
def db_init():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY,
            username     TEXT,
            stars        INTEGER DEFAULT 0,
            last_bonus   INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            total_won    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def db_get_user(user_id, username=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username, stars, last_bonus, games_played, total_won FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO users (user_id, username, stars, last_bonus) VALUES (?, ?, ?, 0)",
            (user_id, username or "", START_BALANCE)
        )
        conn.commit()
        row = (user_id, username or "", START_BALANCE, 0, 0, 0)
    conn.close()
    return {
        "user_id": row[0],
        "username": row[1],
        "stars": row[2],
        "last_bonus": row[3],
        "games_played": row[4],
        "total_won": row[5],
    }


def db_update_stars(user_id, delta):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET stars = stars + ? WHERE user_id = ?", (delta, user_id))
    conn.commit()
    conn.close()


def db_try_bet(user_id, bet):
    """Атомарно списывает ставку. True — если хватило баланса, False — если нет."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET stars = stars - ? WHERE user_id = ? AND stars >= ?",
        (bet, user_id, bet)
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def db_update_after_game(user_id, won_amount):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET games_played = games_played + 1, total_won = total_won + ? WHERE user_id = ?",
        (won_amount, user_id)
    )
    conn.commit()
    conn.close()


def db_set_last_bonus(user_id, ts):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (ts, user_id))
    conn.commit()
    conn.close()


def db_top(limit=10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT username, user_id, stars FROM users ORDER BY stars DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ============ КЛАВИАТУРЫ ============
def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text="🎰 Слоты (50)", callback_data="game_slots"),
        InlineKeyboardButton(text="🎲 Кубик (25)", callback_data="game_dice"),
        InlineKeyboardButton(text="🪙 Монетка (10)", callback_data="game_coin"),
        InlineKeyboardButton(text="⭐ Мой баланс", callback_data="check_balance"),
        InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily_bonus"),
        InlineKeyboardButton(text="🏆 Топ игроков", callback_data="top_players"),
    )
    return kb


def back_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu"))
    return kb


def after_game_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text="🔁 Слоты", callback_data="game_slots"),
        InlineKeyboardButton(text="🎲 Кубик", callback_data="game_dice"),
        InlineKeyboardButton(text="🪙 Монетка", callback_data="game_coin"),
        InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu"),
    )
    return kb


def coin_choice_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text="🦅 Орёл", callback_data="coin_heads"),
        InlineKeyboardButton(text="👑 Решка", callback_data="coin_tails"),
        InlineKeyboardButton(text="⬅️ В меню", callback_data="main_menu"),
    )
    return kb


# ============ КОМАНДЫ ============
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user = db_get_user(message.from_user.id, message.from_user.username)
    text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"🌟 Добро пожаловать в звёздное казино Mechagram!\n\n"
        f"⭐ Твой баланс: <b>{user['stars']}</b> звёзд\n"
        f"🎮 Игр сыграно: {user['games_played']}\n\n"
        f"Выбери игру:"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=main_menu())


@bot.message_handler(commands=['balance'])
def cmd_balance(message):
    user = db_get_user(message.from_user.id, message.from_user.username)
    bot.send_message(
        message.chat.id,
        f"⭐ Твой баланс: <b>{user['stars']}</b> звёзд",
        parse_mode="HTML",
        reply_markup=back_menu()
    )


@bot.message_handler(commands=['top'])
def cmd_top(message):
    send_top(message.chat.id)


@bot.message_handler(commands=['help'])
def cmd_help(message):
    text = (
        "📖 <b>Помощь</b>\n\n"
        "/start — главное меню\n"
        "/balance — мой баланс\n"
        "/top — топ игроков\n"
        "/help — эта справка\n\n"
        "🎰 Слоты — 50 ⭐\n"
        "🎲 Кубик — 25 ⭐\n"
        "🪙 Монетка — 10 ⭐"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=back_menu())


# ============ ХЕЛПЕРЫ ============
def safe_edit(chat_id, message_id, text, reply_markup=None):
    """Пытается отредактировать сообщение, если не выходит — отправляет новое."""
    try:
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except Exception as e:
        # "message is not modified" — не страшно, просто игнорируем
        if "not modified" in str(e):
            return
        # иначе пробуем отправить новое
        try:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            pass


def send_top(chat_id):
    rows = db_top(10)
    if not rows:
        bot.send_message(chat_id, "Пока никто не играл 🤷", reply_markup=back_menu())
        return
    lines = ["🏆 <b>Топ игроков:</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (username, user_id, stars) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"{i+1}."
        name = f"@{username}" if username else f"id{user_id}"
        lines.append(f"{prefix} {name} — <b>{stars}</b> ⭐")
    bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=back_menu())


# ============ CALLBACK ============
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    user = db_get_user(user_id, call.from_user.username)

    # --- Главное меню ---
    if call.data == "main_menu":
        text = f"🏠 Главное меню\n\n⭐ Баланс: <b>{user['stars']}</b> звёзд"
        safe_edit(call.message.chat.id, call.message.message_id, text, main_menu())
        bot.answer_callback_query(call.id)

    # --- Баланс ---
    elif call.data == "check_balance":
        bot.answer_callback_query(
            call.id,
            text=f"⭐ У тебя {user['stars']} звёзд",
            show_alert=True
        )

    # --- Топ ---
    elif call.data == "top_players":
        bot.answer_callback_query(call.id)
        send_top(call.message.chat.id)

    # --- Ежедневный бонус ---
    elif call.data == "daily_bonus":
        now = int(time.time())
        if now - user["last_bonus"] < DAILY_COOLDOWN:
            left = DAILY_COOLDOWN - (now - user["last_bonus"])
            hours = left // 3600
            minutes = (left % 3600) // 60
            bot.answer_callback_query(
                call.id,
                text=f"⏳ Бонус будет доступен через {hours}ч {minutes}м",
                show_alert=True
            )
            return
        bonus = random.randint(DAILY_BONUS_MIN, DAILY_BONUS_MAX)
        db_update_stars(user_id, bonus)
        db_set_last_bonus(user_id, now)
        new_balance = user["stars"] + bonus
        bot.answer_callback_query(call.id, text=f"🎁 +{bonus} звёзд!", show_alert=True)
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"🎁 Ежедневный бонус получен!\n\n"
            f"➕ Начислено: <b>+{bonus}</b> ⭐\n"
            f"⭐ Баланс: <b>{new_balance}</b> звёзд",
            back_menu()
        )

    # --- Слоты ---
    elif call.data == "game_slots":
        bet = SLOT_BET
        if not db_try_bet(user_id, bet):
            bot.answer_callback_query(call.id, text=f"❌ Нужно {bet} ⭐", show_alert=True)
            return

        symbols = ["🍒", "🍋", "7️⃣", "💎", "⭐"]
        spin = [random.choice(symbols) for _ in range(3)]
        result = " | ".join(spin)

        if spin[0] == spin[1] == spin[2]:
            win = bet * 5
            db_update_stars(user_id, win)
            db_update_after_game(user_id, win - bet)
            msg = f"🎰 [ {result} ]\n\n🎉 <b>ДЖЕКПОТ!</b> +{win} ⭐"
        else:
            db_update_after_game(user_id, -bet)
            msg = f"🎰 [ {result} ]\n\n😢 Не повезло. -{bet} ⭐"

        new_user = db_get_user(user_id)
        bot.answer_callback_query(call.id)
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"{msg}\n\n⭐ Баланс: <b>{new_user['stars']}</b>",
            after_game_menu()
        )

    # --- Кубик ---
    elif call.data == "game_dice":
        bet = DICE_BET
        if not db_try_bet(user_id, bet):
            bot.answer_callback_query(call.id, text=f"❌ Нужно {bet} ⭐", show_alert=True)
            return

        player = random.randint(1, 6)
        dealer = random.randint(1, 6)
        msg = f"🎲 Ты: <b>{player}</b>\n🎲 Дилер: <b>{dealer}</b>\n\n"

        if player > dealer:
            win = bet * 2
            db_update_stars(user_id, win)
            db_update_after_game(user_id, win - bet)
            msg += f"🎉 <b>Победа!</b> +{win} ⭐"
        elif player == dealer:
            db_update_stars(user_id, bet)
            db_update_after_game(user_id, 0)
            msg += "🤝 Ничья. Ставка возвращена."
        else:
            db_update_after_game(user_id, -bet)
            msg += f"😢 Проигрыш. -{bet} ⭐"

        new_user = db_get_user(user_id)
        bot.answer_callback_query(call.id)
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"{msg}\n\n⭐ Баланс: <b>{new_user['stars']}</b>",
            after_game_menu()
        )

    # --- Монетка: показываем выбор стороны ---
    elif call.data == "game_coin":
        if user["stars"] < COIN_BET:
            bot.answer_callback_query(call.id, text=f"❌ Нужно {COIN_BET} ⭐", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        safe_edit(
            call.message.chat.id,
            call.message.message_id,
            f"🪙 <b>Монетка</b>\n\nСтавка: {COIN_BET} ⭐\nВыбери сторону:",
            coin_choice_menu()
        )

    # --- Монетка: игрок выбрал Орла ---
    elif call.data == "coin_heads":
        play_coin(call, user_id, "Орёл")

    # --- Монетка: игрок выбрал Решку ---
    elif call.data == "coin_tails":
        play_coin(call, user_id, "Решка")

    # --- Неизвестный callback ---
    else:
        bot.answer_callback_query(call.id, text="Неизвестная команда 🤔")


def play_coin(call, user_id, player_choice):
    bet = COIN_BET
    if not db_try_bet(user_id, bet):
        bot.answer_callback_query(call.id, text=f"❌ Нужно {bet} ⭐", show_alert=True)
        return

    result = random.choice(["Орёл", "Решка"])
    emoji = "🦅" if result == "Орёл" else "👑"

    if player_choice == result:
        win = bet * 2
        db_update_stars(user_id, win)
        db_update_after_game(user_id, win - bet)
        msg = f"🪙 Выпало: {emoji} <b>{result}</b>\n\n🎉 Угадал! +{win} ⭐"
    else:
        db_update_after_game(user_id, -bet)
        msg = f"🪙 Выпало: {emoji} <b>{result}</b>\n\n😢 Мимо. -{bet} ⭐"

    new_user = db_get_user(user_id)
    bot.answer_callback_query(call.id)
    safe_edit(
        call.message.chat.id,
        call.message.message_id,
        f"{msg}\n\n⭐ Баланс: <b>{new_user['stars']}</b>",
        after_game_menu()
    )


# ============ ЗАПУСК ============
if __name__ == "__main__":
    db_init()
    print("🚀 Казино-бот запущено. Ожидаю сообщений...")
    bot.infinity_polling()
