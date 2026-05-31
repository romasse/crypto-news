"""Investing.com — крипто-лента (русскоязычная) через публичный RSS.

Страница /analysis/cryptocurrency — Next.js SPA (парсить хрупко), но Investing
отдаёт чистый RSS крипто-новостей. Переиспользуем RSS-движок: меняем только имя
источника и список фидов. Детектор монет понимает русские названия.
"""
from __future__ import annotations

from .rss import RSSSource

# news_301 = «Новости криптовалют» (ru). Отдаёт title/pubDate/link/author.
INVESTING_FEEDS = [
    "https://ru.investing.com/rss/news_301.rss",
]


class InvestingSource(RSSSource):
    name = "investing"

    def __init__(self):
        super().__init__(feeds=INVESTING_FEEDS)
