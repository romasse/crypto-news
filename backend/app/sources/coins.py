"""Простой детектор упоминаний монет в тексте.

На старте — словарь синонимов. Позже можно заменить на NER / список с CoinGecko.
"""
from __future__ import annotations

import re

# тикер -> список синонимов (в нижнем регистре), по которым ищем в тексте
COIN_ALIASES: dict[str, list[str]] = {
    "BTC": ["btc", "bitcoin", "биткоин", "биткойн"],
    "ETH": ["eth", "ethereum", "эфир", "эфириум"],
    "SOL": ["sol", "solana", "солана"],
    "XRP": ["xrp", "ripple"],
    "BNB": ["bnb", "binance coin"],
    "DOGE": ["doge", "dogecoin"],
    "ADA": ["ada", "cardano"],
    "USDT": ["usdt", "tether"],
}

# заранее компилируем границы слов, чтобы "eth" не ловился внутри "ethereum"/"method"
_PATTERNS: dict[str, list[re.Pattern]] = {
    coin: [re.compile(rf"\b{re.escape(a)}\b", re.IGNORECASE) for a in aliases]
    for coin, aliases in COIN_ALIASES.items()
}


def detect_coins(*texts: str) -> list[str]:
    """Возвращает отсортированный список тикеров, упомянутых в переданных текстах."""
    blob = " ".join(t for t in texts if t)
    found = [
        coin for coin, patterns in _PATTERNS.items() if any(p.search(blob) for p in patterns)
    ]
    return sorted(found)
