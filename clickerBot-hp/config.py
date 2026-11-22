import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if not ENV_PATH.exists():
    ENV_PATH = BASE_DIR.parent / ".env"

load_dotenv(dotenv_path=ENV_PATH)

BOT_TOKEN = os.getenv("BOT_TOKEN")
_database_path = os.getenv("DATABASE_PATH", "clicker.db")
if _database_path == ":memory:":
    DATABASE_PATH = _database_path
else:
    DATABASE_PATH = Path(_database_path)
    if not DATABASE_PATH.is_absolute():
        DATABASE_PATH = BASE_DIR / DATABASE_PATH

CLICK_COOLDOWN = int(os.getenv("CLICK_COOLDOWN", 960))
SUPERCLICK_COOLDOWN = int(os.getenv("SUPERCLICK_COOLDOWN", 960))
SUPERCLICK_CHANCE = float(os.getenv("SUPERCLICK_CHANCE", 50.20))
SOSATEL_COOLDOWN = int(os.getenv("SOSATEL_COOLDOWN", CLICK_COOLDOWN))

INVITE_INTERVAL = int(os.getenv("INVITE_INTERVAL", 2400))
INVITE_TIMEOUT = int(os.getenv("INVITE_TIMEOUT", 400))
INVITE_SUPERCLICK_CHANCE = float(os.getenv("INVITE_SUPERCLICK_CHANCE", 3.30))

INVEST_MIN_HOURS = int(os.getenv("INVEST_MIN_HOURS", 1))
INVEST_MAX_HOURS = int(os.getenv("INVEST_MAX_HOURS", 24))
INVEST_LOSE_CHANCE = float(os.getenv("INVEST_LOSE_CHANCE", 0.20))
INVEST_GROWTH_MIN = float(os.getenv("INVEST_GROWTH_MIN", 1.20))
INVEST_GROWTH_MAX = float(os.getenv("INVEST_GROWTH_MAX", 2.50))
INVEST_WATCH_INTERVAL = int(os.getenv("INVEST_WATCH_INTERVAL", 30))

NORMAL_NAME = os.getenv("NORMAL_NAME", "Клик")
FAST_NAME = os.getenv("FAST_NAME", "Быстрый клик")
SUPER_NAME = os.getenv("SUPER_NAME", "Суперклик")
EXP_NAME = os.getenv("EXP_NAME", "Опыт")
SOSATEL_NAME = os.getenv("SOSATEL_NAME", "Факсёр")

# ─── Техническое обслуживание ────────────────────────────────────────────────
# Кто может пользоваться ботом во время техработ и командой /test.
# Юзернеймы сравниваются без @ и без учёта регистра.
ADMIN_USERNAMES = {
    name.strip().lstrip("@").lower()
    for name in os.getenv("ADMIN_USERNAMES", "")
    .replace(",", " ")
    .split()
    if name.strip()
}

# Числовые id надёжнее юзернеймов: юзернейм можно сменить.
ADMIN_IDS = {
    int(value)
    for value in os.getenv("ADMIN_IDS", "").replace(",", " ").split()
    if value.strip().isdigit()
}

# Файл-флаг: пока лежит на диске — бот в техработах.
MAINTENANCE_FLAG = Path(
    os.getenv("MAINTENANCE_FLAG", str(BASE_DIR / "maintenance.flag"))
)
