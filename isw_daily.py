"""
Точка входу для щоденного отримання й публікації звіту ISW.

Запускається щоранку о 8:00 за Києвом (5:00 UTC) і публікує переклад 
звіту ISW за вчора у Telegram-групу.
"""

import html
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


def _truncate_at_sentence_boundary(text: str, max_length: int) -> str:
    """
    Обрізає текст до max_length символів, але не посеред речення чи слова:
    шукає останню крапку/знак оклику/питання перед лімітом і ріже там.

    Якщо в межах ліміту не знайшлося жодного завершеного речення (текст
    складається з одного дуже довгого речення), ріже по останньому пробілу,
    щоб хоча б не розривати слово навпіл.

    Args:
        text: Вхідний текст
        max_length: Максимальна довжина результату (без урахування "…")

    Returns:
        Текст, обрізаний за реченням/словом, з "…" в кінці якщо обрізали;
        оригінальний текст без змін, якщо він і так вкладався в ліміт.
    """
    if len(text) <= max_length:
        return text

    # Лишаємо трохи місця під "…"
    budget = max(max_length - 1, 0)
    candidate = text[:budget]

    sentence_end = max(
        candidate.rfind(". "),
        candidate.rfind("! "),
        candidate.rfind("? "),
        candidate.rfind(".\n"),
        candidate.rfind("!\n"),
        candidate.rfind("?\n"),
    )

    if sentence_end != -1:
        return candidate[: sentence_end + 1].rstrip() + "…"

    # Немає завершеного речення в межах ліміту — ріжемо по останньому пробілу
    space_pos = candidate.rfind(" ")
    if space_pos != -1:
        return candidate[:space_pos].rstrip() + "…"

    # Взагалі без пробілів (малоймовірно) — ріжемо як є
    return candidate.rstrip() + "…"


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

    # Telegram обмежує повідомлення 4096 символами (лічиться разом зі
    # схованою частиною <blockquote expandable>, а не лише видимою).
    # Модель просимо писати коротко (див. isw_report.py), але не покладаємось
    # тільки на це — тут гарантована підстраховка, якщо звіт все ж завеликий.
    TELEGRAM_MAX_LEN = 4096

    header = f"🎖️ Аналіз ISW за {formatted_date}:\n\n"
    footer = f"\n\n🔗 Оригінал: {url}"
    wrapper_overhead = len("<blockquote expandable></blockquote>")

    available_for_summary = TELEGRAM_MAX_LEN - len(header) - len(footer) - wrapper_overhead

    raw_summary = _truncate_at_sentence_boundary(summary, available_for_summary)
    escaped_summary = html.escape(raw_summary)

    post_text = f"{header}<blockquote expandable>{escaped_summary}</blockquote>{footer}"

    # Остання підстраховка: якщо після escape() (яке подовжує текст через
    # &, < або >) все одно вилізли за межі — ріжемо ще раз, вже жорстко.
    if len(post_text) > TELEGRAM_MAX_LEN:
        overflow = len(post_text) - TELEGRAM_MAX_LEN
        escaped_summary = escaped_summary[:-(overflow + 1)].rstrip() + "…"
        post_text = f"{header}<blockquote expandable>{escaped_summary}</blockquote>{footer}"

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
