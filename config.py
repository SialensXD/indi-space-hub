"""Application configuration loaded from environment variables."""

import os


BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
SITE_ORIGIN = os.environ.get("SITE_ORIGIN", "https://sialensxd.github.io")
SITE_URL = os.environ.get("SITE_URL", "https://sialensxd.github.io/indi-space-hub/")
PORT = int(os.environ.get("PORT", "10000"))

ADMIN_USERNAMES = {
    username.strip().lstrip("@").lower()
    for username in os.environ.get("ADMIN_USERNAMES", "sialens_xd").split(",")
    if username.strip()
}

ALLOWED_GROUPS = {
    int(chat_id.strip())
    for chat_id in os.environ.get("ALLOWED_GROUPS", "-1003994387386").split(",")
    if chat_id.strip()
}

ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID", "7857165309"))


def webhook_url() -> str | None:
    """Return the public webhook URL when the service is configured for webhooks."""
    if not RENDER_EXTERNAL_URL:
        return None
    return f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
