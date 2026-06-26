from aiogram import Bot
from aiogram.enums import ParseMode
from loguru import logger

from src.constants import ORDER_MESSAGE


def _format_offers(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "0"
    return str(n)


def _format_time_left(value) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "—"


def _format_username(value) -> str:
    if isinstance(value, str) and value.strip():
        name = value.strip()
        return name if name.startswith("@") else f"@{name}"
    return "—"


def _format_total_projects(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "—"
    return str(n) if n > 0 else "—"


def _format_hired_percent(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "—"
    return f"{n}%"


async def send_order(bot: Bot, chat_id: int, order: dict, utc_offset: int = 3) -> None:
    payload = dict(order)
    payload["offers_count_str"] = _format_offers(order.get("offers_count"))
    payload["time_left_str"] = _format_time_left(order.get("time_left"))
    payload["buyer_username_str"] = _format_username(order.get("buyer_username"))
    payload["buyer_total_projects_str"] = _format_total_projects(order.get("buyer_total_projects"))
    payload["buyer_hired_percent_str"] = _format_hired_percent(order.get("buyer_hired_percent"))

    text = ORDER_MESSAGE.format(**payload)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки в {chat_id}: {e}")
