# main.py — Точка входу Telegram-бота для моніторингу новин

import os
import sys
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from news_checker import NewsChecker


# Отримання токену та ID групи з середовища
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")

if not BOT_TOKEN or not GROUP_ID:
    print("❌ Помилка: відсутні TELEGRAM_BOT_TOKEN або TELEGRAM_GROUP_ID у середовищі!")
    sys.exit(1)


# Ініціалізація бота та диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# Створення NewsChecker (робиться один раз при запуску)
news_checker = NewsChecker()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Відповідь на команду /start."""
    await message.answer(
        "🤖 Я бот для моніторингу новин про завершення війни!\n\n"
        "Я двічі на день перевіряю новинні джерела і публікую в цю групу "
        "ті, що стосуються перемовин, перемир'я, мирних угод тощо.\n\n"
        f"📊 Статистика:\n"
        f"• Еталонні речення: {news_checker.get_stats()['etalon_sentences_count']}\n"
        f"• RSS-джерела: {news_checker.get_stats()['rss_sources_count']}\n"
        f"• Опубліковано новин: {news_checker.get_stats()['published_count']}",
        parse_mode="HTML"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Відповідь на команду /stats — показує поточну статистику."""
    stats = news_checker.get_stats()
    await message.answer(
        f"📊 Статистика бота:\n\n"
        f"• Еталонні речення: {stats['etalon_sentences_count']}\n"
        f"• Порог схожості: {stats['similarity_threshold']}\n"
        f"• RSS-джерела: {stats['rss_sources_count']}\n"
        f"• Опубліковано новин: {stats['published_count']}",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Відповідь на команду /help."""
    await message.answer(
        "📖 Допомога:\n\n"
        "/start — показати інформацію про бота\n"
        "/stats — показати статистику\n"
        "/help — ця допомога",
        parse_mode="HTML"
    )


async def post_news_to_group(news: dict):
    """Відправка нової новини в Telegram-групу."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Відкрити", url=news["link"])]
    ])
    
    await bot.send_message(
        chat_id=GROUP_ID,
        text=news_checker.get_formatted_post(news),
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def run_news_check():
    """Асинхронна функція для перевірки новин (використовується в GitHub Actions)."""
    feeds = news_checker.fetch_rss_feeds()
    relevant_news = news_checker.filter_news(feeds)
    
    if not relevant_news:
        print("ℹ️ Релевантних новин не знайдено.")
        return
    
    for news in relevant_news:
        await post_news_to_group(news)
    
    stats = news_checker.get_stats()
    print(f"✅ Перевірка завершена! Опубліковано: {len(relevant_news)} новин")


@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    """Команда /check — перевіряє новини і публікує релевантні."""
    await message.answer("🔄 Перевірка новин...")
    
    # Отримання RSS-стрічок
    feeds = news_checker.fetch_rss_feeds()
    print(f"✅ Отримано {len(feeds)} записів з RSS-джерел")
    
    # Фільтрація новин
    relevant_news = news_checker.filter_news(feeds)
    print(f"✅ Знайдено {len(relevant_news)} релевантних новин")
    
    if not relevant_news:
        await message.answer("ℹ️ Релевантних новин не знайдено.")
        return
    
    # Відправка новин в групу
    for news in relevant_news:
        await post_news_to_group(news)
    
    # Статистика після перевірки
    stats = news_checker.get_stats()
    await message.answer(
        f"✅ Перевірка завершена!\n\n"
        f"• Отримано записів з RSS: {len(feeds)}\n"
        f"• Релевантних новин: {len(relevant_news)}\n"
        f"• Опубліковано всього: {stats['published_count']}",
        parse_mode="HTML"
    )


# Запуск бота
if __name__ == "__main__":
    print("🚀 Запуск Telegram-бота...")
    print(f"🤖 Токен бота: {BOT_TOKEN[:20]}...")
    print(f"👥 ID групи: {GROUP_ID}")
    
    # Виконуємо перевірку новин, потім запускаємо бота
    asyncio.run(run_news_check())
    dp.start_polling(bot)
