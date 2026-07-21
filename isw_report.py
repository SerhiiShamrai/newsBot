"""
Модуль для отримання й перекладу звітів ISW (Institute for the Study of War).
"""

import os
from datetime import date, datetime
from typing import Optional
import requests
from bs4 import BeautifulSoup
from openai import OpenAI


def build_isw_url(target_date: date) -> str:
    """
    Формує URL звіту ISW за вказаною датою.

    Args:
        target_date: Дата для формування URL (об'єкт datetime.date)

    Returns:
        URL звіту у форматі:
        https://understandingwar.org/research/russia-ukraine/
        russian-offensive-campaign-assessment-{month}-{day}-{year}/

    Приклад:
        >>> build_isw_url(date(2026, 7, 21))
        'https://understandingwar.org/research/russia-ukraine/
         russian-offensive-campaign-assessment-july-21-2026/'
    """
    month_name = target_date.strftime("%B").lower()
    day = target_date.day
    year = target_date.year

    return (
        f"https://understandingwar.org/research/russia-ukraine/"
        f"russian-offensive-campaign-assessment-{month_name}-{day}-{year}/"
    )


def fetch_isw_report(url: str) -> Optional[str]:
    """
    Отримує текст звіту ISW за вказаним URL.

    Args:
        url: URL звіту ISW

    Returns:
        Текст звіту як рядок, або None якщо звіт не знайдено
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            print(f"⚠️ Звіт не знайдено (статус {response.status_code}): {url}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        article_content = soup.find("article")
        if not article_content:
            article_content = soup.find("div", class_=["entry-content", "post-content"])

        if not article_content:
            main = soup.find("main")
            if main:
                article_content = main

        if not article_content:
            print(f"⚠️ Не вдалося знайти контент статті: {url}")
            return None

        text_elements = article_content.find_all(["p", "h2", "h3", "h4"])
        lines = []

        for elem in text_elements:
            text = elem.get_text(" ", strip=True)
            if text:
                lines.append(text)

        return "\n\n".join(lines)

    except requests.RequestException as e:
        print(f"⚠️ Помилка при завантаженні звіту ISW: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Помилка при обробці звіту ISW: {e}")
        return None


def translate_and_summarize_isw(text: str) -> dict:
    """
    Перекладає звіт ISW українською мовою через Groq API.

    Args:
        text: Текст звіту англійською мовою

    Returns:
        Словник {"summary": "переклад"} або fallback при помилці
    """
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"]
    )

    truncated_text = text[:10000] if len(text) > 10000 else text

    prompt = (
        "Ось звіт англійською мовою про останні події війни Росії проти України. "
        "Зроби детальний переказ українською мовою, приблизно 20 речень, "
        "охопи всі ключові тези: ситуацію на фронті по напрямках, ключові заяви й події, "
        "оцінки аналітиків, важливі деталі про озброєння чи тактику, якщо згадуються. "
        f"{truncated_text}"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=4000
        )

        summary = response.choices[0].message.content.strip()
        return {"summary": summary}

    except Exception as e:
        print(f"⚠️ Помилка при перекладі ISW звіту: {e}")
        fallback_text = text[:1000] if len(text) > 1000 else text
        return {
            "summary": f"(не вдалося перекласти)\n\n{fallback_text}"
        }