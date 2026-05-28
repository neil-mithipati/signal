import aiosqlite
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# DATABASE_PATH env var lets Railway (or any host) point to a persistent volume
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(Path(__file__).parent.parent / "signal.db")))
CACHE_TTL_HOURS = 72


def _now() -> datetime:
    """Returns current UTC time. Extracted so tests can monkeypatch it."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                source TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product, source)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wishlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT NOT NULL,
                verdict TEXT NOT NULL,
                review_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS completed_reviews (
                short_id     TEXT PRIMARY KEY,
                slug         TEXT NOT NULL,
                review_id    TEXT NOT NULL UNIQUE,
                product_name TEXT NOT NULL,
                source_data  TEXT NOT NULL,
                verdict_data TEXT NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def get_cached(product: str, source: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT result_json, created_at FROM cache WHERE product = ? AND source = ?",
            (product.lower().strip(), source),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            created_at = datetime.fromisoformat(row["created_at"])
            if _now() - created_at > timedelta(hours=CACHE_TTL_HOURS):
                return None
            return json.loads(row["result_json"])


async def set_cached(product: str, source: str, result: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO cache (product, source, result_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(product, source) DO UPDATE SET
                result_json = excluded.result_json,
                created_at = excluded.created_at
            """,
            (product.lower().strip(), source, json.dumps(result), _now().isoformat()),
        )
        await db.commit()


async def get_wishlist() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, product_name, verdict, review_id, created_at FROM wishlist ORDER BY id DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def add_to_wishlist(product_name: str, verdict: str, review_id: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO wishlist (product_name, verdict, review_id) VALUES (?, ?, ?)",
            (product_name, verdict, review_id),
        )
        await db.commit()
        item_id = cursor.lastrowid
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, product_name, verdict, review_id, created_at FROM wishlist WHERE id = ?",
            (item_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row)


async def save_completed_review(
    short_id: str,
    slug: str,
    review_id: str,
    product_name: str,
    source_data: dict,
    verdict_data: dict,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO completed_reviews
                (short_id, slug, review_id, product_name, source_data, verdict_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (short_id, slug, review_id, product_name, json.dumps(source_data), json.dumps(verdict_data), _now().isoformat()),
        )
        await db.commit()


async def get_review_by_short_id(short_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT short_id, slug, review_id, product_name, source_data, verdict_data FROM completed_reviews WHERE short_id = ?",
            (short_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "short_id": row["short_id"],
                "slug": row["slug"],
                "review_id": row["review_id"],
                "product_name": row["product_name"],
                "source_data": json.loads(row["source_data"]),
                "verdict_data": json.loads(row["verdict_data"]),
            }


async def remove_from_wishlist(item_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM wishlist WHERE id = ?", (item_id,))
        await db.commit()
        return cursor.rowcount > 0
