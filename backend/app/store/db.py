"""Лёгкое хранилище на sqlite (stdlib). Хранит проанализированные новости.

Дедупликация по NewsItem.id: повторный сбор не плодит дубли и не перезапускает
AI-анализ для уже разобранных событий.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from ..models import AnalyzedItem, Analysis, NewsItem

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyzed_items (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT,
    body          TEXT,
    published_at  TEXT NOT NULL,
    coins         TEXT NOT NULL,   -- JSON-массив тикеров
    analysis      TEXT NOT NULL,   -- JSON Analysis
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_published ON analyzed_items(published_at);
"""


class Store:
    def __init__(self, path: str | None = None):
        self.path = path or settings.db_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        # гарантируем схему на каждом подключении (идемпотентно): если файл БД
        # пропал/пересоздан, запросы не упадут с "no such table".
        conn.executescript(_SCHEMA)
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def has(self, item_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM analyzed_items WHERE id = ?", (item_id,)
            ).fetchone()
            return row is not None

    def upsert(self, item: NewsItem, analysis: Analysis) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO analyzed_items
                   (id, source, title, url, body, published_at, coins, analysis, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    item.id,
                    item.source,
                    item.title,
                    item.url,
                    item.body,
                    item.published_at.isoformat(),
                    json.dumps(item.coins),
                    analysis.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _row_to_analyzed(self, row: sqlite3.Row) -> AnalyzedItem:
        item = NewsItem(
            id=row["id"],
            source=row["source"],
            title=row["title"],
            url=row["url"],
            body=row["body"] or "",
            published_at=datetime.fromisoformat(row["published_at"]),
            coins=json.loads(row["coins"]),
        )
        analysis = Analysis.model_validate_json(row["analysis"])
        return AnalyzedItem(item=item, analysis=analysis)

    def feed(self, coin: str | None = None, limit: int = 100) -> list[AnalyzedItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM analyzed_items ORDER BY published_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items = [self._row_to_analyzed(r) for r in rows]
        if coin:
            coin = coin.upper()
            items = [a for a in items if coin in a.item.coins]
        return items


store = Store()
