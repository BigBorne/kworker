import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp
import orjson
from loguru import logger

from src.constants import HEADERS, KWORK_API_URL, CATEGORY_NAME_BY_ID

_TIMEOUT = aiohttp.ClientTimeout(total=10)


def _fmt_price(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _budget_str(order: dict) -> str:
    price_min = _fmt_price(order.get("priceLimit"))
    price_max = _fmt_price(order.get("possiblePriceLimit"))
    is_range  = order.get("isHigherPrice", False)

    if price_min == 0:
        return "не указан"
    if is_range and price_max > price_min:
        return f"{price_min:,} – {price_max:,} ₽".replace(",", " ")
    return f"{price_min:,} ₽".replace(",", " ")


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _published_at(order: dict) -> str:
    """Дата публикации заказа в ISO формате (UTC). Пусто — если не определена."""
    for key in ("date_create", "dateCreate", "date_confirm", "dateConfirm", "date_active"):
        ts = _to_int(order.get(key))
        if ts > 0:
            try:
                return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except (OverflowError, OSError, ValueError):
                continue
    return ""


def _offers_count(order: dict) -> int:
    """Количество откликов на заказ."""
    for key in ("kwork_count", "kworkCount", "offers_count", "offersCount", "count_offers"):
        n = _to_int(order.get(key))
        if n >= 0 and key in order:
            return n
    return 0


def _time_left(order: dict) -> str:
    """Сколько ещё актуален заказ — человекочитаемая строка."""
    raw = order.get("time_left") or order.get("timeLeft")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    for key in ("date_active_to", "dateActiveTo", "active_to", "activeTo", "date_expire", "dateExpire"):
        ts = _to_int(order.get(key))
        if ts > 0:
            try:
                delta = datetime.fromtimestamp(ts, tz=timezone.utc) - datetime.now(tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                continue
            secs = int(delta.total_seconds())
            if secs <= 0:
                return "истёк"
            days, rem = divmod(secs, 86400)
            hours = rem // 3600
            if days > 0:
                return f"{days} д. {hours} ч." if hours else f"{days} д."
            minutes = (rem % 3600) // 60
            if hours > 0:
                return f"{hours} ч. {minutes} мин." if minutes else f"{hours} ч."
            return f"{minutes} мин."
    return ""


def _buyer_info(order: dict) -> tuple[str, int, int]:
    """Возвращает (username, total_projects, hired_percent) для заказчика."""
    user = order.get("user") if isinstance(order.get("user"), dict) else {}
    profile = user.get("profile") if isinstance(user.get("profile"), dict) else {}

    sources = (order, user, profile)

    def pick_str(*keys: str) -> str:
        for src in sources:
            for key in keys:
                val = src.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return ""

    def pick_int(*keys: str) -> int:
        for src in sources:
            for key in keys:
                if key in src:
                    n = _to_int(src.get(key))
                    if n > 0:
                        return n
        return 0

    username = pick_str("username", "userName", "user_name", "login")
    total_projects = pick_int(
        "wants_total", "wantsTotal", "all_orders_count", "allOrdersCount",
        "orders_count", "ordersCount", "wants_count", "wantsCount",
    )
    hired_percent = pick_int(
        "wants_hired_percent", "wantsHiredPercent",
        "hired_percent", "hiredPercent",
        "user_hired_percent", "userHiredPercent",
    )
    return username, total_projects, hired_percent


async def fetch_orders(session: aiohttp.ClientSession, category_id: str) -> list[dict]:
    """Получить все заказы со страницы 1 для категории."""
    data = aiohttp.FormData()
    data.add_field("c", category_id)
    data.add_field("page", "1")

    try:
        async with session.post(
            KWORK_API_URL, data=data, headers=HEADERS, timeout=_TIMEOUT
        ) as resp:
            raw = await resp.read()
    except asyncio.TimeoutError:
        logger.warning(f"Таймаут для категории {category_id}")
        return []
    except aiohttp.ClientError as e:
        logger.warning(f"Сетевая ошибка для категории {category_id}: {e}")
        return []

    try:
        payload = orjson.loads(raw)
        orders: list[dict] = payload.get("data", {}).get("wants", [])
    except Exception as e:
        logger.error(f"Ошибка разбора JSON для категории {category_id}: {e}")
        return []

    result: list[dict] = []
    for o in orders:
        if not o.get("id"):
            continue
        username, total_projects, hired_percent = _buyer_info(o)
        result.append({
            "order_id":      int(o["id"]),
            "title":         o.get("name", "Без названия"),
            "description":   (o.get("description") or "")[:2000].strip(),
            "budget":        _budget_str(o),
            "price_min":     _fmt_price(o.get("priceLimit")),
            "category_id":   category_id,
            "category_name": CATEGORY_NAME_BY_ID.get(category_id, f"Категория {category_id}"),
            "kwork_published_at": _published_at(o),
            "offers_count":  _offers_count(o),
            "time_left":     _time_left(o),
            "buyer_username":       username,
            "buyer_total_projects": total_projects,
            "buyer_hired_percent":  hired_percent,
        })
    return result
