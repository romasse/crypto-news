"""Реестр источников: имя -> экземпляр Source. Включается через настройки."""
from __future__ import annotations

from ..config import settings
from .base import Source
from .cryptopanic import CryptoPanicSource
from .investing import InvestingSource
from .mock import MockSource
from .rss import RSSSource

_FACTORIES = {
    "mock": MockSource,
    "rss": RSSSource,
    "cryptopanic": CryptoPanicSource,
    "investing": InvestingSource,
}


def get_enabled_sources() -> list[Source]:
    sources: list[Source] = []
    for name in settings.enabled_sources:
        factory = _FACTORIES.get(name)
        if factory:
            sources.append(factory())
    return sources
