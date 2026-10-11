# Telegram Channel Scheduler (Railway + Supabase)

A private Telegram bot that schedules text, photo, video, document, animation, and media-group posts to a Telegram channel. It supports one-time and daily recurring publication.

## 1. Create the Telegram bot
1. In Telegram, open **@BotFather**, run `/newbot`, and copy the token.
2. Add the bot to your target channel as an administrator. Grant permission to post messages.
3. For a private channel, the owner can post `/bindchannel` as a separate channel post after the bot is an admin. For a public channel, use `/bind @channelusername` in the bot's private chat.

## 2. Set up Supabase
1. Create a Supabase project.
2. Open **SQL Editor** and run all of `schema.sql`.
3. In **Project Settings → API**, copy the Project URL and the `service_role` key. Keep the service-role key secret; only put it in Railway variables.

## 3. Deploy to Railway
1. Put these project files in a GitHub repository.
2. In Railway, create a project and deploy the repository as a worker service.
3. Set the following service variables:

- `BOT_TOKEN` — token from BotFather
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` — Supabase `service_role` key
- `OWNER_SETUP_CODE` — a long, random activation code you choose
- `DEFAULT_TIMEZONE` — optional; defaults to `Europe/Moscow`

Railway uses `Procfile` to run `python main.py`. Keep only **one running replica** of this worker to avoid duplicate publication attempts.

## 4. Activate and connect
1. Open the bot's private chat and send `/start YOUR_OWNER_SETUP_CODE`.
2. Add the bot as an administrator to your channel with permission to post.
3. Public channel: send `/bind @channelusername` to the bot.
4. Private channel: publish `/bindchannel` as a separate post in the channel. The bot should notify you in private chat.

## 5. Schedule posts
- Send `/new` or tap **➕ Запланировать**.
- Send the text, photo, video, document, or animation.
- Enter the date/time, e.g. `2026-12-31 18:30`.
- Add `/daily` to the end to repeat daily, e.g. `2026-12-31 18:30 /daily`.
- `/list` shows pending/failed posts; `/cancel ID` cancels a pending post.
- `/timezone Europe/Berlin` changes the timezone used to interpret entered dates.

## Notes and limitations
- Telegram's Bot API does not provide a general API to list all channels owned by a person. This project uses explicit channel binding and checks bot permissions.
- The chat flow supports text, photos, videos, documents, animations, and photo/video albums (up to 10 items).
- Daily recurrence advances by 24 hours in UTC. For time zones that change daylight saving time, a future improvement is to calculate the next occurrence in local wall-clock time.
- Delivery cannot be made exactly-once in the face of network failures: if Telegram accepts a post but the process crashes before Supabase is updated, retrying may duplicate it. Review failed posts before rescheduling.
- If the bot cannot DM you, open its private chat and press Start.
