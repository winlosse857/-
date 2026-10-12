# NOIR Telegram identity bot (prototype)

This bot assigns one stable, unique internal NOIR ID to each Telegram account. It is not a phone-number provider: IDs do not receive calls or SMS. The first version stores mappings in a local SQLite database, so deploy it on a persistent host/volume before real use.

## Setup

1. In Telegram, open `@BotFather`, run `/newbot`, and follow its prompts.
2. Keep the bot token private. Do not commit it to GitHub or send it in chat.
3. Install Python 3.11 or newer, then run:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Set the `TELEGRAM_BOT_TOKEN` environment variable to the token from BotFather.
5. Optionally set `NOIR_BOT_DB` to a path on persistent storage.
6. Run `python bot.py`.

## Current limitations

- Prototype only; there is no secure app login handoff yet.
- The SQLite database must persist across restarts and must not be shared by ephemeral instances.
- Before production, connect the bot to the app backend, add short-lived one-time login challenges, rate limiting, and account recovery protections.
