"""Детектор упоминаний монет в тексте.

Базовый слой — курируемые синонимы для мейджоров (точные, включая русские названия).
Поверх него — динамический слой из вселенной топ-400 (CoinGecko): матчим по полному
имени монеты (например, «Chainlink», «Polkadot») и по кэштегу ($LINK). Имена надёжны;
тикеры матчим только через $-кэштег, чтобы не ловить шум вроде "OP"/"GAS"/"ID".
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

_PATTERNS: dict[str, list[re.Pattern]] = {
    coin: [re.compile(rf"\b{re.escape(a)}\b", re.IGNORECASE) for a in aliases]
    for coin, aliases in COIN_ALIASES.items()
}

# --- Динамический слой из вселенной топ-400 -----------------------------------

_DYN_NAME_PATTERNS: dict[str, re.Pattern] = {}  # SYMBOL -> regex по имени
_DYN_SYMBOLS: set[str] = set()                   # для матча кэштегов $SYM


def set_universe(coins: list[dict]) -> None:
    """Регистрирует имена/тикеры топ-400 для детекта. Вызывается перед сбором."""
    names: dict[str, re.Pattern] = {}
    symbols: set[str] = set()
    for c in coins:
        sym = (c.get("symbol") or "").upper()
        name = (c.get("name") or "").strip()
        if sym:
            symbols.add(sym)
        # имя матчим целиком по границам слов, если оно достаточно длинное и не
        # состоит только из общих слов (минимизируем ложные срабатывания)
        if name and len(name) >= 4 and sym not in COIN_ALIASES:
            names[sym] = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
    global _DYN_NAME_PATTERNS, _DYN_SYMBOLS
    _DYN_NAME_PATTERNS = names
    _DYN_SYMBOLS = symbols


def detect_coins(*texts: str) -> list[str]:
    """Возвращает отсортированный список тикеров, упомянутых в переданных текстах."""
    blob = " ".join(t for t in texts if t)
    found = {
        coin for coin, patterns in _PATTERNS.items() if any(p.search(blob) for p in patterns)
    }
    # динамические монеты по полному имени
    for sym, pat in _DYN_NAME_PATTERNS.items():
        if pat.search(blob):
            found.add(sym)
    # кэштеги $SYM для любой монеты из вселенной
    for m in re.findall(r"\$([A-Za-z]{2,10})", blob):
        s = m.upper()
        if s in _DYN_SYMBOLS or s in COIN_ALIASES:
            found.add(s)
    return sorted(found)
