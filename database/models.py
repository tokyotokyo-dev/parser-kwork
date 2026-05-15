from __future__ import annotations

import aiosqlite

from config import DB_PATH


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id  TEXT    UNIQUE NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS kwork_stats (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                kwork_name   TEXT    NOT NULL,
                views_count  INTEGER NOT NULL,
                orders_count INTEGER NOT NULL DEFAULT 0,
                recorded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_kwork_stats_name_id "
            "ON kwork_stats(kwork_name, id DESC)"
        )
        await db.commit()
    finally:
        await db.close()


async def is_message_processed(message_id: str) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)
        )
        row = await cursor.fetchone()
        return row is not None
    finally:
        await db.close()


async def mark_message_processed(message_id: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)",
            (message_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def save_kwork_stat(kwork_name: str, views_count: int, orders_count: int) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO kwork_stats (kwork_name, views_count, orders_count) "
            "VALUES (?, ?, ?)",
            (kwork_name, views_count, orders_count),
        )
        await db.commit()
    finally:
        await db.close()


async def get_previous_stats() -> dict[str, tuple[int, int]]:
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT kwork_name, views_count, orders_count
            FROM kwork_stats
            WHERE id IN (
                SELECT MAX(id) FROM kwork_stats GROUP BY kwork_name
            )
            """
        )
        rows = await cursor.fetchall()
        return {
            row["kwork_name"]: (row["views_count"], row["orders_count"])
            for row in rows
        }
    finally:
        await db.close()


async def get_latest_stats() -> list[tuple[str, int, int]]:
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT kwork_name, views_count, orders_count
            FROM kwork_stats
            WHERE id IN (
                SELECT MAX(id) FROM kwork_stats GROUP BY kwork_name
            )
            ORDER BY kwork_name
            """
        )
        rows = await cursor.fetchall()
        return [(r["kwork_name"], r["views_count"], r["orders_count"]) for r in rows]
    finally:
        await db.close()
