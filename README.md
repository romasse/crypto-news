# Crypto News Analyzer

Мини-сайт: парсинг крипто-новостей → AI-анализ (Claude) → дашборд с лентой и
сентиментом по монетам. Веб-версия как прототип под будущий мобильный клиент
(API и фронт разделены).

## Архитектура

```
backend/app/
├── sources/      # единый интерфейс Source → NewsItem (rss, cryptopanic, mock)
├── market/       # рыночные данные: CoinGecko (цены/объёмы) + Binance (funding)
├── inference/    # AI-слой: Claude по жёсткой схеме вывода + stub без ключа
├── aggregator/   # Time-Window: сбор за N часов, дедуп, агрегация сентимента
├── store/        # SQLite-хранилище проанализированных новостей
└── api/          # REST: /api/feed, /api/collect, /api/market, /api/sentiment
frontend/         # статический SPA (vanilla JS + Chart.js): лента, цены, сентимент
```

**Схема AI-вывода** (на каждое событие): Executive Summary → AI-анализ +
Daily Outlook → Directional Bias (BTC/ETH/SOL: Bullish/Neutral/Bearish) →
Correlation Check (объём BTC, DXY, Nasdaq, funding rate).

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env          # по желанию — впиши ANTHROPIC_API_KEY
uvicorn app.main:app --reload --app-dir backend
```

Открой http://127.0.0.1:8000 → жми «Собрать сейчас».

Без `ANTHROPIC_API_KEY` AI-слой работает в режиме **stub** (эвристика на
ключевых словах) — весь конвейер крутится сквозняком на mock-новостях.

## API

| Метод | Путь | Назначение |
|------|------|-----------|
| GET  | `/api/health`   | статус, режим AI, источники, наличие токена CryptoPanic |
| POST | `/api/collect?hours=2` | сбор и анализ за окно (+ срез рынка) |
| GET  | `/api/feed?coin=BTC`   | лента (фильтр по монете) |
| GET  | `/api/market`          | цены/объёмы/изменение + funding rate BTC |
| GET  | `/api/sentiment`       | средний сентимент по монетам |

## Источники (живые)

- **RSS** — CoinDesk, Cointelegraph, Decrypt (без ключа).
- **Investing.com** — русскоязычная крипто-лента через RSS `news_301` (без ключа).
- **CryptoPanic** — нужен бесплатный `CRYPTOPANIC_TOKEN`; без него тихо пропускается.
- **CoinGecko + Binance** — рыночные данные и funding rate для Correlation Check.
- **mock** — резервные новости для офлайн-демо.

## Деплой (GitHub + Render)

Один сервис: FastAPI отдаёт и API, и фронт. Конфиг — в [render.yaml](render.yaml).

**1. Запушить в приватный репозиторий GitHub:**
```bash
# создай пустой приватный репо на github.com, затем:
git remote add origin git@github.com:<user>/<repo>.git   # или https://...
git branch -M main
git push -u origin main
```

**2. Развернуть на Render:**
- Render Dashboard → **New → Blueprint** → подключить репозиторий (Render найдёт `render.yaml`).
- В переменных окружения задать **`ANTHROPIC_API_KEY`** (секрет, не в репозитории) и при желании `CRYPTOPANIC_TOKEN`.
- Deploy → открыть выданный `https://<app>.onrender.com`.

**Нюансы Render free tier:**
- Инстанс засыпает при простое → первый запрос после паузы холодный (~50с).
- ФС эфемерная: SQLite-история обнуляется при редеплое/рестарте. Для постоянной БД — примонтировать Render Disk и задать `CRYPTO_NEWS_DB=/var/data/crypto_news.db`.

> **Ключи в репозиторий не коммитятся** (`.env` в `.gitignore`). Секреты задаются только в дашборде Render.

## Дальше (бэклог)

- Соцслой: X-«Radar»-аккаунты, Telegram по ссылкам (платные API/авторизация).
- Макро-индикаторы DXY и Nasdaq в Correlation Check (пока `—`).
- Реальный Claude-анализ (вписать `ANTHROPIC_API_KEY`).
- Экспорт отчётов в Markdown (Obsidian PKM).
- Перенос фронта в React Native.
