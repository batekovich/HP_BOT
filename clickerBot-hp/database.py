import sqlite3
import time
from typing import Any

from config import DATABASE_PATH


SCORE_COLUMNS = {
    "clicks",
    "superclicks",
    "sosatel_clicks",
}
COOLDOWN_COLUMNS = {
    "last_click",
    "last_superclick",
    "last_sosatel",
}


def connect() -> sqlite3.Connection:
    """Open a configured SQLite connection with safe concurrent writes."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_missing_user_columns(conn: sqlite3.Connection) -> None:
    """Apply small, idempotent migrations for databases from older releases."""
    columns = _table_columns(conn, "users")
    migrations = {
        "sosatel_clicks": (
            "ALTER TABLE users ADD COLUMN sosatel_clicks INTEGER DEFAULT 0"
        ),
        "last_sosatel": "ALTER TABLE users ADD COLUMN last_sosatel REAL DEFAULT 0",
        "last_seen": "ALTER TABLE users ADD COLUMN last_seen REAL DEFAULT 0",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def init_db() -> None:
    conn = connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                clicks INTEGER NOT NULL DEFAULT 0,
                fast_clicks INTEGER NOT NULL DEFAULT 0,
                superclicks INTEGER NOT NULL DEFAULT 0,
                sosatel_clicks INTEGER NOT NULL DEFAULT 0,
                exp INTEGER NOT NULL DEFAULT 0,
                last_click REAL NOT NULL DEFAULT 0,
                last_superclick REAL NOT NULL DEFAULT 0,
                last_sosatel REAL NOT NULL DEFAULT 0,
                last_chat_id INTEGER,
                last_seen REAL NOT NULL DEFAULT 0
            )
            """
        )
        _add_missing_user_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT,
                chat_id INTEGER,
                amount INTEGER NOT NULL CHECK(amount > 0),
                hours INTEGER NOT NULL CHECK(hours > 0),
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_users (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                clicks INTEGER NOT NULL DEFAULT 0,
                superclicks INTEGER NOT NULL DEFAULT 0,
                sosatel_clicks INTEGER NOT NULL DEFAULT 0,
                exp INTEGER NOT NULL DEFAULT 0,
                last_seen REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_starts (
                chat_id INTEGER PRIMARY KEY,
                first_start REAL NOT NULL,
                started_by INTEGER,
                started_by_name TEXT,
                starts_count INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    seed_chat_members()


# ----- users / chats -----

def touch_user(user_id: int, name: str, chat_id: int | None = None) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
            (user_id, name),
        )
        now = time.time()
        if chat_id is None:
            conn.execute(
                "UPDATE users SET name=?, last_seen=? WHERE user_id=?",
                (name, now, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET name=?, last_chat_id=?, last_seen=? WHERE user_id=?",
                (name, chat_id, now, user_id),
            )
        conn.commit()
    finally:
        conn.close()


def add_chat(chat_id: int) -> None:
    conn = connect()
    try:
        conn.execute("INSERT OR IGNORE INTO chats (chat_id) VALUES (?)", (chat_id,))
        conn.commit()
    finally:
        conn.close()


def get_all_chats() -> list[int]:
    conn = connect()
    try:
        return [row[0] for row in conn.execute("SELECT chat_id FROM chats")]
    finally:
        conn.close()


# ----- stats -----

BOT_USER_IDS = (777000, 136817688, 1087968824)


def get_bot_stats(active_days: int = 7) -> dict[str, int]:
    """Цифры для /info: пользователи, чаты, клики, активные за N дней."""
    placeholders = ",".join("?" for _ in BOT_USER_IDS)
    since = time.time() - active_days * 86400
    conn = connect()
    try:
        users = conn.execute(
            f"SELECT COUNT(*) FROM users WHERE user_id NOT IN ({placeholders})",
            BOT_USER_IDS,
        ).fetchone()[0]
        chats = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        clicks, superclicks, sosatel = conn.execute(
            "SELECT COALESCE(SUM(clicks), 0), COALESCE(SUM(superclicks), 0), "
            "COALESCE(SUM(sosatel_clicks), 0) FROM users"
        ).fetchone()
        seen = "MAX(last_seen, last_click, last_superclick, last_sosatel)"
        active = conn.execute(
            f"SELECT COUNT(*) FROM users WHERE {seen} >= ?",
            (since,),
        ).fetchone()[0]
        last_activity = conn.execute(
            f"SELECT COALESCE(MAX({seen}), 0) FROM users"
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "users": users,
        "chats": chats,
        "clicks": clicks,
        "superclicks": superclicks,
        "sosatel": sosatel,
        "active": active,
        "active_days": active_days,
        "last_activity": int(last_activity or 0),
    }


# ----- scores -----

def inc_score(user_id: int, column: str, delta: int = 1) -> None:
    if column not in SCORE_COLUMNS:
        raise ValueError(f"Unknown score column: {column}")
    conn = connect()
    try:
        conn.execute(
            f"UPDATE users SET {column}=MAX(0, {column} + ?), last_seen=? WHERE user_id=?",
            (delta, time.time(), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def inc_click(user_id: int, delta: int = 1) -> None:
    inc_score(user_id, "clicks", delta)


def inc_superclick(user_id: int, delta: int = 1) -> None:
    inc_score(user_id, "superclicks", delta)


def inc_sosatel(user_id: int, delta: int = 1) -> None:
    inc_score(user_id, "sosatel_clicks", delta)


def inc_fast(user_id: int, delta: int = 1) -> None:
    """Retain the old counter API for compatibility with older integrations."""
    # fast_clicks predates the named leaderboards but remains part of profiles.
    conn = connect()
    try:
        conn.execute(
            "UPDATE users SET fast_clicks=MAX(0, fast_clicks + ?) WHERE user_id=?",
            (delta, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def inc_exp(user_id: int, delta: int = 1) -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE users SET exp=MAX(0, exp + ?) WHERE user_id=?",
            (delta, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_counts(user_id: int) -> tuple[int, int, int, int, int]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT clicks, fast_clicks, superclicks, sosatel_clicks, exp "
            "FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
        return row or (0, 0, 0, 0, 0)
    finally:
        conn.close()


def get_user_clicks(user_id: int) -> int:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT clicks FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def update_clicks(user_id: int, delta: int) -> None:
    inc_score(user_id, "clicks", delta)


def get_top(column: str, limit: int = 10) -> list[tuple[str | None, int]]:
    if column not in SCORE_COLUMNS:
        raise ValueError(f"Unknown score column: {column}")
    if limit <= 0:
        return []
    conn = connect()
    try:
        return conn.execute(
            f"SELECT name, {column} FROM users "
            f"ORDER BY {column} DESC, exp DESC, user_id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


# ----- cooldowns -----

def set_cooldown(user_id: int, field: str) -> None:
    if field not in COOLDOWN_COLUMNS:
        raise ValueError(f"Unknown cooldown column: {field}")
    conn = connect()
    try:
        conn.execute(
            f"UPDATE users SET {field}=? WHERE user_id=?",
            (time.time(), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_remaining_cd(user_id: int, field: str, cooldown: int) -> int:
    if field not in COOLDOWN_COLUMNS:
        raise ValueError(f"Unknown cooldown column: {field}")
    conn = connect()
    try:
        row = conn.execute(
            f"SELECT {field} FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    last = row[0] if row and row[0] else 0
    return max(0, int(cooldown - (time.time() - last)))


def can_use(user_id: int, field: str, cooldown: int) -> bool:
    return get_remaining_cd(user_id, field, cooldown) <= 0


def try_use_cooldown(user_id: int, field: str, cooldown: int) -> bool:
    """Atomically reserve a cooldown slot to prevent duplicate scoring."""
    if field not in COOLDOWN_COLUMNS:
        raise ValueError(f"Unknown cooldown column: {field}")
    now = time.time()
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        updated = conn.execute(
            f"UPDATE users SET {field}=? WHERE user_id=? "
            f"AND (? - COALESCE({field}, 0)) >= ?",
            (now, user_id, now, cooldown),
        ).rowcount
        conn.commit()
        return updated == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ----- investments -----

def create_investment(
    user_id: int,
    name: str,
    chat_id: int,
    amount: int,
    hours: int,
) -> bool:
    """Debit clicks and create an investment in one transaction."""
    if amount <= 0 or hours <= 0:
        return False
    now = time.time()
    end_time = now + hours * 3600
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        updated = conn.execute(
            "UPDATE users SET clicks=clicks-? WHERE user_id=? AND clicks>=?",
            (amount, user_id, amount),
        ).rowcount
        if updated != 1:
            conn.rollback()
            return False
        conn.execute(
            """
            INSERT INTO investments
                (user_id, name, chat_id, amount, hours, start_time, end_time, completed)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (user_id, name, chat_id, amount, hours, now, end_time),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_investment(
    user_id: int,
    name: str,
    chat_id: int,
    amount: int,
    hours: int,
) -> None:
    """Backward-compatible insertion helper for older integrations."""
    now = time.time()
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO investments
                (user_id, name, chat_id, amount, hours, start_time, end_time, completed)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (user_id, name, chat_id, amount, hours, now, now + hours * 3600),
        )
        conn.commit()
    finally:
        conn.close()


def get_active_investments(user_id: int) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, amount, end_time FROM investments "
            "WHERE user_id=? AND completed=0 ORDER BY end_time ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [{"id": row[0], "amount": row[1], "end_time": row[2]} for row in rows]


def get_finished_investments() -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, user_id, name, chat_id, amount, hours, start_time, end_time "
            "FROM investments WHERE completed=0 AND end_time<=? ORDER BY end_time ASC",
            (time.time(),),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": row[0],
            "user_id": row[1],
            "name": row[2],
            "chat_id": row[3],
            "amount": row[4],
            "hours": row[5],
            "start_time": row[6],
            "end_time": row[7],
        }
        for row in rows
    ]


def complete_investment(investment_id: int, user_id: int, payout: int = 0) -> bool:
    """Settle an investment once and optionally credit its payout atomically."""
    payout = max(0, payout)
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        completed = conn.execute(
            "UPDATE investments SET completed=1 "
            "WHERE id=? AND user_id=? AND completed=0",
            (investment_id, user_id),
        ).rowcount
        if completed != 1:
            conn.rollback()
            return False
        if payout:
            conn.execute(
                "UPDATE users SET clicks=clicks+? WHERE user_id=?",
                (payout, user_id),
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def pop_finished_investments() -> list[dict[str, Any]]:
    """Compatibility alias; settlement is now performed per investment."""
    return get_finished_investments()


# ----- per-chat scores and chat start history -----

CHAT_SCORE_COLUMNS = {
    "clicks",
    "superclicks",
    "sosatel_clicks",
    "exp",
}


def touch_chat_user(chat_id: int, user_id: int, name: str) -> None:
    """Remember that the user is active in this exact chat."""
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO chat_users (chat_id, user_id, name, last_seen) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET "
            "name=excluded.name, last_seen=excluded.last_seen",
            (chat_id, user_id, name, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def inc_chat_score(
    chat_id: int, user_id: int, column: str, delta: int = 1
) -> None:
    """Add points to a user's score inside one chat only."""
    if column not in CHAT_SCORE_COLUMNS:
        raise ValueError(f"Unknown chat score column: {column}")
    conn = connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO chat_users (chat_id, user_id, name) "
            "VALUES (?, ?, '')",
            (chat_id, user_id),
        )
        conn.execute(
            f"UPDATE chat_users SET {column}={column}+? "
            "WHERE chat_id=? AND user_id=?",
            (delta, chat_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def seed_chat_members() -> None:
    """Remember people who already clicked in a group before chat_users existed."""
    conn = connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO chat_users (chat_id, user_id, name, last_seen) "
            "SELECT last_chat_id, user_id, name, last_seen FROM users "
            "WHERE last_chat_id IS NOT NULL AND last_chat_id < 0"
        )
        conn.commit()
    finally:
        conn.close()


def get_chat_top(
    chat_id: int, column: str, limit: int = 10
) -> list[tuple[int, str | None, int]]:
    """Return (user_id, name, score) for one chat, best first.

    Score is the user's overall score - the same number /profile shows.
    Only people who have been seen in this chat get into the list.
    """
    if column not in CHAT_SCORE_COLUMNS:
        raise ValueError(f"Unknown chat score column: {column}")
    if limit <= 0:
        return []
    conn = connect()
    try:
        return conn.execute(
            f"SELECT u.user_id, u.name, u.{column} AS score "
            f"FROM chat_users c JOIN users u ON u.user_id = c.user_id "
            f"WHERE c.chat_id=? AND u.{column}>0 "
            f"ORDER BY u.{column} DESC, u.exp DESC, u.user_id ASC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    finally:
        conn.close()


def register_chat_start(
    chat_id: int, user_id: int | None = None, name: str | None = None
) -> dict[str, Any]:
    """Mark a chat start; the first call per chat is remembered forever."""
    now = time.time()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT first_start, starts_count FROM chat_starts WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE chat_starts SET starts_count=starts_count+1 "
                "WHERE chat_id=?",
                (chat_id,),
            )
            conn.commit()
            return {
                "is_new": False,
                "first_start": row[0],
                "starts_count": row[1] + 1,
            }
        conn.execute(
            "INSERT INTO chat_starts "
            "(chat_id, first_start, started_by, started_by_name, starts_count) "
            "VALUES (?, ?, ?, ?, 1)",
            (chat_id, now, user_id, name),
        )
        conn.commit()
        return {"is_new": True, "first_start": now, "starts_count": 1}
    finally:
        conn.close()


def get_chat_start(chat_id: int) -> dict[str, Any] | None:
    """Read the stored start info for a chat, if it exists."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT first_start, started_by, started_by_name, starts_count "
            "FROM chat_starts WHERE chat_id=?",
            (chat_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "first_start": row[0],
        "started_by": row[1],
        "started_by_name": row[2],
        "starts_count": row[3],
    }
