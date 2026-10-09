import os
from pathlib import Path

import aiosqlite


DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(
    os.getenv("DATABASE_PATH", str(DATA_DIR / "bot.sqlite3"))
)


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                blocked INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source TEXT,
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()


async def remember_user(
    user_id: int,
    username: str | None,
    first_name: str | None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name),
        )
        await db.commit()


async def create_job(user_id: int, source: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO jobs (user_id, source, status)
            VALUES (?, ?, ?)
            """,
            (user_id, source, "processing"),
        )
        await db.commit()
        return cursor.lastrowid


async def finish_job(
    job_id: int,
    status: str,
    error: str | None = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE jobs
            SET status = ?, error = ?
            WHERE id = ?
            """,
            (status, error, job_id),
        )
        await db.commit()


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:

        async def count(query: str) -> int:
            cursor = await db.execute(query)
            row = await cursor.fetchone()
            return row[0]

        return {
            "users": await count(
                "SELECT COUNT(*) FROM users"
            ),
            "today": await count(
                """
                SELECT COUNT(*) FROM users
                WHERE date(joined_at) = date('now')
                """
            ),
            "month": await count(
                """
                SELECT COUNT(*) FROM users
                WHERE strftime('%Y-%m', joined_at)
                    = strftime('%Y-%m', 'now')
                """
            ),
            "jobs": await count(
                "SELECT COUNT(*) FROM jobs"
            ),
            "success": await count(
                "SELECT COUNT(*) FROM jobs WHERE status = 'success'"
            ),
            "failed": await count(
                "SELECT COUNT(*) FROM jobs WHERE status = 'failed'"
            ),
        }


async def list_users(limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT user_id, username, first_name, blocked, joined_at
            FROM users
            ORDER BY joined_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return await cursor.fetchall()


async def search_users(term: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT user_id, username, first_name, blocked
            FROM users
            WHERE CAST(user_id AS TEXT) LIKE ?
               OR username LIKE ?
            ORDER BY joined_at DESC
            LIMIT 50
            """,
            (f"%{term}%", f"%{term}%"),
        )
        return await cursor.fetchall()


async def set_user_blocked(user_id: int, blocked: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users
            SET blocked = ?
            WHERE user_id = ?
            """,
            (int(blocked), user_id),
        )
        await db.commit()


async def log_admin_action(
    admin_id: int,
    action: str,
    details: str = "",
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO admin_logs (admin_id, action, details)
            VALUES (?, ?, ?)
            """,
            (admin_id, action, details),
        )
        await db.commit()
