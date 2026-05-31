"""AI-слой: интерпретация новости моделью Claude по жёсткой схеме вывода.

Если ANTHROPIC_API_KEY задан — используется Anthropic SDK с tool-use для
получения строго структурированного JSON. Если ключа нет — работает
детерминированный стаб на ключевых словах, чтобы конвейер крутился на моках.
"""
from __future__ import annotations

import json

from ..config import settings
from ..models import Analysis, Bias, CorrelationCheck, DirectionalBias, NewsItem

# --- Схема инструмента: жёсткий контракт вывода (раздел 3 спеки) ---------------

ANALYSIS_TOOL = {
    "name": "report_analysis",
    "description": "Структурированный анализ влияния крипто-новости на рынок.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Executive Summary: суть события в 1-2 фразах"},
            "ai_analysis": {"type": "string", "description": "Вектор влияния и прогноз на торговую сессию (Daily Outlook)"},
            "sentiment": {"type": "number", "description": "Сентимент от -1 (негатив) до +1 (позитив)"},
            "directional_bias": {
                "type": "object",
                "properties": {
                    "BTC": {"type": "string", "enum": ["Bullish", "Neutral", "Bearish"]},
                    "ETH": {"type": "string", "enum": ["Bullish", "Neutral", "Bearish"]},
                    "SOL": {"type": "string", "enum": ["Bullish", "Neutral", "Bearish"]},
                },
                "required": ["BTC", "ETH", "SOL"],
            },
            "correlation_check": {
                "type": "object",
                "properties": {
                    "btc_volume": {"type": "string"},
                    "dxy": {"type": "string"},
                    "nasdaq": {"type": "string"},
                    "funding_rate": {"type": "string"},
                },
            },
        },
        "required": ["summary", "ai_analysis", "sentiment", "directional_bias"],
    },
}

SYSTEM_PROMPT = (
    "Ты — крипто-аналитик. По одной новости дай сжатую интерпретацию её влияния "
    "на рынок и направленный прогноз для BTC, ETH, SOL. Не пересказывай новость "
    "дословно — оценивай эффект. Всегда вызывай инструмент report_analysis."
)


def _to_analysis(data: dict) -> Analysis:
    db = data.get("directional_bias", {})
    cc = data.get("correlation_check", {})
    return Analysis(
        summary=data.get("summary", ""),
        ai_analysis=data.get("ai_analysis", ""),
        sentiment=float(data.get("sentiment", 0.0)),
        directional_bias=DirectionalBias(
            BTC=Bias(db.get("BTC", "Neutral")),
            ETH=Bias(db.get("ETH", "Neutral")),
            SOL=Bias(db.get("SOL", "Neutral")),
        ),
        correlation_check=CorrelationCheck(
            btc_volume=cc.get("btc_volume"),
            dxy=cc.get("dxy"),
            nasdaq=cc.get("nasdaq"),
            funding_rate=cc.get("funding_rate"),
        ),
    )


# --- Стаб: эвристика на ключевых словах ---------------------------------------

_POS = ["inflow", "приток", "record", "рекорд", "partnership", "партнёрств", "upgrade", "апгрейд", "cuts fees", "bullish", "adoption"]
_NEG = ["outage", "сбой", "hack", "взлом", "hotter than expected", "выше прогноза", "sell", "продаж", "dump", "bearish", "под давлением", "lawsuit", "иск"]


def _stub_analysis(item: NewsItem) -> Analysis:
    text = f"{item.title} {item.body}".lower()
    score = sum(w in text for w in _POS) - sum(w in text for w in _NEG)
    sentiment = max(-1.0, min(1.0, score / 2))
    if sentiment > 0.1:
        bias = Bias.bullish
    elif sentiment < -0.1:
        bias = Bias.bearish
    else:
        bias = Bias.neutral

    # bias применяем к упомянутым монетам, прочие топ-активы — neutral
    def b(coin: str) -> Bias:
        return bias if coin in item.coins else Bias.neutral

    return Analysis(
        summary=item.title,
        ai_analysis=f"[stub] Оценка по ключевым словам: сентимент={sentiment:+.2f}. "
        f"Затронутые активы: {', '.join(item.coins) or 'нет'}.",
        sentiment=sentiment,
        directional_bias=DirectionalBias(BTC=b("BTC"), ETH=b("ETH"), SOL=b("SOL")),
        correlation_check=CorrelationCheck(
            btc_volume="n/a (stub)", dxy="n/a", nasdaq="n/a", funding_rate="n/a"
        ),
    )


class Analyzer:
    """Анализирует NewsItem. Лениво создаёт Anthropic-клиент при наличии ключа."""

    def __init__(self):
        self._client = None
        if settings.ai_enabled:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def analyze(self, item: NewsItem, market_context: str | None = None) -> Analysis:
        if self._client is None:
            return _stub_analysis(item)
        try:
            return await self._analyze_with_claude(item, market_context)
        except Exception:
            # сбой API не должен ронять конвейер — откатываемся к стабу
            return _stub_analysis(item)

    async def _analyze_with_claude(self, item: NewsItem, market_context: str | None) -> Analysis:
        user = (
            f"Новость (источник: {item.source}, монеты: {', '.join(item.coins) or 'не определены'}):\n"
            f"Заголовок: {item.title}\n"
            f"Текст: {item.body}"
        )
        if market_context:
            user += f"\n\nТекущий рыночный контекст: {market_context}"
        resp = await self._client.messages.create(
            model=settings.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[ANALYSIS_TOOL],
            tool_choice={"type": "tool", "name": "report_analysis"},
            # Классификация потока новостей: думать глубоко не нужно — быстро и дёшево.
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == "report_analysis":
                data = block.input if isinstance(block.input, dict) else json.loads(block.input)
                return _to_analysis(data)
        return _stub_analysis(item)
