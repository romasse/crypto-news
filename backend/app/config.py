"""Конфигурация приложения. Значения читаются из окружения / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# .env лежит в корне проекта (на уровень выше backend). Грузим по фиксированному
# пути, чтобы не зависеть от текущей рабочей директории запуска.
# override=True: .env — авторитетный источник. В окружении может торчать пустой
# ANTHROPIC_API_KEY, который иначе тенью перекрыл бы значение из .env.
load_dotenv(BASE_DIR.parent / ".env", override=True)


class Settings:
    # AI / Anthropic
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    # Модель для анализа. Sonnet — баланс цена/качество для потока новостей.
    model: str = os.getenv("CRYPTO_NEWS_MODEL", "claude-sonnet-4-6")

    # Если ключа нет — analyzer работает в режиме заглушки (детерминированный стаб),
    # чтобы скелет крутился сквозняком на моках без затрат на API.
    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    # CoinGecko: опциональный ключ для повышения лимитов.
    # - бесплатный demo-ключ (coingecko.com/en/api) → заголовок x-cg-demo-api-key
    # - платный Pro-ключ → COINGECKO_PRO=1, заголовок x-cg-pro-api-key + pro-домен
    # Без ключа работает публичный тариф (жёсткий rate-limit).
    coingecko_api_key: str | None = os.getenv("COINGECKO_API_KEY") or None
    coingecko_pro: bool = os.getenv("COINGECKO_PRO", "").lower() in ("1", "true", "yes")

    # Хранилище
    db_path: str = os.getenv("CRYPTO_NEWS_DB", str(BASE_DIR / "data" / "crypto_news.db"))

    # Какие источники включены по умолчанию (через запятую): mock, rss, cryptopanic
    # cryptopanic тихо пропускается, если не задан CRYPTOPANIC_TOKEN.
    enabled_sources: list[str] = (
        os.getenv("CRYPTO_NEWS_SOURCES", "rss,investing,cryptopanic,mock")
        .replace(" ", "")
        .split(",")
    )


settings = Settings()
