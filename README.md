# Carter Telegram Bot

Telegram bot running as an aiohttp web service on Render with PostgreSQL hosted by Supabase.

## Local setup

1. Create a virtual environment and install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Set the variables from `.env.example` in the shell or in Render. Do not commit real tokens or database credentials.
3. Start the service:

   ```powershell
   python bot.py
   ```

## Render settings

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `python bot.py`
- Health check path: `/`
- Required variables: `BOT_TOKEN`, `DATABASE_URL`, `RENDER_EXTERNAL_URL`
- Recommended variable: `WEBHOOK_SECRET`

`DATABASE_URL` must be a PostgreSQL URL from Supabase. The application disables prepared-statement caching for compatibility with Supabase transaction poolers.

Set the same `WEBHOOK_SECRET` only in Render. It is used to reject webhook requests that do not contain Telegram's secret header.

## Existing Supabase database

The application does not delete users, inventory, titles, triggers, or logs. On startup it only creates missing tables and adds missing columns. It also does not insert seed roles/items/titles, so existing game data remains authoritative.

Before the first deploy:

1. In Supabase, create a database backup or export the affected tables.
2. Check that these tables exist: `users`, `roles`, `items`, `titles`, `inventory`, `user_titles`, `triggers`, `mod_logs`.
3. Check that `users.user_id` is unique. The bot needs it for `ON CONFLICT (user_id)`.
4. Check that `inventory` has a unique constraint on `(user_id, item_id)`. The shop needs it for `ON CONFLICT (user_id, item_id)`.
5. Check that `user_titles` has a unique constraint on `(user_id, title_id)`.
6. Confirm that your existing `roles.id`, `items.id`, and `titles.id` values match the role IDs and item/title references already used by the bot.
7. Deploy the service. The first startup runs only additive schema changes. Watch Render logs for `Подключение к БД успешно`.
8. Test `/start`, `/role`, `/profile`, `/shop`, `/daily`, `/status` in Telegram.

The destructive `/clear_db` command has been removed. There is no application command that clears the users table.

## Project layout

- `bot.py`: aiogram handlers, application wiring, lifecycle, and database queries still being migrated.
- `config.py`: environment-backed deployment configuration.
- `domain.py`: pure progression and moderation helpers.
- `game_data.py`: static character, skill, and slot balance data.
