"""
Точка входу для щоденного отримання й публікації звіту ISW.

Запускається щоранку о 8:00 за Києвом (5:00 UTC) і публікує переклад 
звіту ISW за вчора у Telegram-групу.
"""

import os
from datetime import date, timedelta
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from isw_report import build_isw_url, fetch_isw_report, translate_and_summarize_isw


def format_date_ukrainian(target_date: date) -> str:
    """
    Форматує дату українською мовою.

    Args:
        target_date: Дата для форматування

    Returns:
        Дата у форматі "21 липня 2026"
    """
    months_ukrainian = [
        "січня", "лютого", "березня", "квітня", "травня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"
    ]

    day = target_date.day
    month = months_ukrainian[target_date.month - 1]
    year = target_date.year

    return f"{day} {month} {year}"


async def post_to_telegram(summary: str, url: str, report_date: date) -> bool:
    """
    Публікує переклад звіту ISW у Telegram-групу.

    Args:
        summary: Переклад звіту українською мовою
        url: URL оригіналу звіту
        report_date: Дата звіту для форматування

    Returns:
        True якщо успішно опубліковано, False в іншому разі
    """
    from aiogram import Bot

    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_BOT_TOKEN або TELEGRAM_CHAT_ID не встановлені")
        return False

    formatted_date = format_date_ukrainian(report_date)

    post_text = (
        f"🎖️ Аналіз ISW за {formatted_date}:\n\n"
        f"{summary}\n\n"
        f"🔗 Оригінал: {url}"
    )

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=int(TELEGRAM_CHAT_ID),
            text=post_text,
            parse_mode="HTML"
        )
        print(f"✅ Звіт ISW за {formatted_date} опубліковано")
        return True
    except Exception as e:
        print(f"❌ Помилка при публікації в Telegram: {e}")
        return False
    finally:
        await bot.session.close()


async def main():
    """Основна функція для щоденного запуску."""
    today = date.today()
    yesterday = today - timedelta(days=1)

    print(f"📅 Отримання звіту ISW за {yesterday}...")

    url = build_isw_url(yesterday)
    print(f"URL: {url}")

    text = fetch_isw_report(url)

    if not text:
        print("⚠️ Звіт не знайдено, завершуємо роботу без помилки")
        return

    print(f"📝 Отримано текст звіту ({len(text)} символів)")

    result = translate_and_summarize_isw(text)
    summary = result.get("summary", "")

    if not summary or "не вдалося перекласти" in summary:
        print("⚠️ Переклад не вдався, публікуємо fallback")

    success = await post_to_telegram(summary, url, yesterday)

    if not success:
        print("⚠️ Не вдалося опублікувати у Telegram")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
