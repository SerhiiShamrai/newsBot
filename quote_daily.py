"""
Скрипт для щоденної публікації цитати в Telegram-групу.
Використовує змінні оточення TELEGRAM_BOT_TOKEN та TELEGRAM_CHAT_ID.
"""

import os
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.types import Message

from quote_of_day import get_next_quote


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def format_message(quote: str) -> str:
    """Форматує повідомлення з цитатою."""
    return (
        f"💬 Цитата дня:\n\n"
        f"{quote}\n\n"
        f"— Лесь Подерв'янський"
    )


async def send_quote_to_telegram() -> None:
    """Відправляє цитату в Telegram-групу."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Помилка: TELEGRAM_BOT_TOKEN або TELEGRAM_CHAT_ID не встановлені")
        return
    
    quote = get_next_quote()
    if not quote:
        print("Помилка: цитата не знайдена (список QUOTES порожній)")
        return
    
    message_text = format_message(quote)
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=int(TELEGRAM_CHAT_ID),
            text=message_text,
        )
        print(f"Цитату дня успішно опубліковано: {datetime.now()}")
    except Exception as e:
        print(f"Помилка при відправці повідомлення: {e}")
    finally:
        await bot.session.close()


def main():
    """Точка входу скрипта."""
    import asyncio
    asyncio.run(send_quote_to_telegram())


if __name__ == "__main__":
    main()