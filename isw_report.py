"""
Модуль для отримання й перекладу звітів ISW (Institute for the Study of War).
"""

import os
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# Модель Groq для перекладу/переказу.
# llama-3.3-70b-versatile деактивована Groq 16.08.2026 — саме через це
# бот падав у fallback "(не вдалося перекласти)".
# Можна перевизначити змінною середовища GROQ_MODEL, не змінюючи код.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")


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


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Щоденні звіти "Russian Offensive Campaign Assessment" ISW тепер виходять
# на criticalthreats.org (на understandingwar.org бот їх більше не знаходив —
# саме тому публікації ISW припинилися). Лишаємо обидва джерела:
# спершу пробуємо кожну адресу напряму, потім шукаємо у списку публікацій.
CRITICAL_THREATS_LISTING_URL = "https://www.criticalthreats.org/analysis"

# Мінімальна довжина тексту, щоб вважати сторінку справжнім звітом, а не
# порожньою оболонкою чи сторінкою з меню/футером (повний звіт — десятки тисяч символів).
MIN_REPORT_CHARS = 3000


def _report_slug(target_date: date) -> str:
    """Slug звіту за датою, напр. russian-offensive-campaign-assessment-october-14-2026."""
    month_name = target_date.strftime("%B").lower()
    return (
        f"russian-offensive-campaign-assessment-"
        f"{month_name}-{target_date.day}-{target_date.year}"
    )


def build_candidate_urls(target_date: date) -> list[str]:
    """
    Усі відомі адреси звіту за датою, у порядку спроб.

    Перший — criticalthreats.org (там звіти зараз з'являються), далі той самий
    без "www" та старий формат understandingwar.org.
    """
    slug = _report_slug(target_date)
    return [
        f"https://www.criticalthreats.org/analysis/{slug}",
        f"https://criticalthreats.org/analysis/{slug}",
        build_isw_url(target_date),
    ]


def _extract_report_text(html: str) -> Optional[str]:
    """
    Дістає текст звіту з HTML сторінки.

    Відкидає навігацію/футер і незаповнені шаблонні плейсхолдери ({{...}}),
    якими сторінка criticalthreats.org наповнена поза основним текстом.
    Повертає None, якщо тексту замало, щоб бути справжнім звітом.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    article_content = soup.find("article")
    if not article_content:
        article_content = soup.find("div", class_=["entry-content", "post-content"])
    if not article_content:
        article_content = soup.find("main")
    if not article_content:
        article_content = soup.body
    if not article_content:
        return None

    lines = []
    for elem in article_content.find_all(["p", "h2", "h3", "h4"]):
        text = elem.get_text(" ", strip=True)
        if text and "{{" not in text:
            lines.append(text)

    result = "\n\n".join(lines)
    if len(result) < MIN_REPORT_CHARS:
        return None
    return result


def fetch_isw_report(url: str) -> Optional[str]:
    """
    Отримує текст звіту ISW за вказаним URL.

    Args:
        url: URL звіту ISW

    Returns:
        Текст звіту як рядок, або None якщо звіт не знайдено
    """
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if response.status_code != 200:
            print(f"⚠️ Звіт не знайдено (статус {response.status_code}): {url}")
            return None

        text = _extract_report_text(response.text)
        if text is None:
            print(f"⚠️ Не вдалося знайти текст звіту (замало контенту): {url}")
        return text

    except requests.RequestException as e:
        print(f"⚠️ Помилка при завантаженні звіту ISW: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Помилка при обробці звіту ISW: {e}")
        return None


def _find_url_in_listing(target_date: date) -> Optional[str]:
    """
    Шукає адресу звіту у списку публікацій criticalthreats.org.

    Деякі звіти мають у slug додатковий хеш (напр. ...-october-2-2026-6ac053ceab44c),
    тому пряма адреса за датою їх не знаходить.
    """
    slug = _report_slug(target_date)
    try:
        response = requests.get(
            CRITICAL_THREATS_LISTING_URL, headers=REQUEST_HEADERS, timeout=30
        )
        if response.status_code != 200:
            print(f"⚠️ Список публікацій недоступний (статус {response.status_code})")
            return None
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            if slug in link["href"]:
                return urljoin(CRITICAL_THREATS_LISTING_URL, link["href"])
    except requests.RequestException as e:
        print(f"⚠️ Помилка при завантаженні списку публікацій: {e}")
    except Exception as e:
        print(f"⚠️ Помилка при пошуку звіту у списку публікацій: {e}")
    return None


def fetch_isw_report_for_date(target_date: date) -> Optional[tuple[str, str]]:
    """
    Знаходить і завантажує звіт ISW за датою, пробуючи всі відомі джерела.

    Returns:
        (текст звіту, URL, з якого його взято) або None, якщо жодне джерело
        не віддало справжній звіт.
    """
    candidates = build_candidate_urls(target_date)

    for url in candidates:
        print(f"🔎 Пробую: {url}")
        text = fetch_isw_report(url)
        if text:
            return text, url

    listed_url = _find_url_in_listing(target_date)
    if listed_url and listed_url not in candidates:
        print(f"🔎 Знайдено у списку публікацій: {listed_url}")
        text = fetch_isw_report(listed_url)
        if text:
            return text, listed_url

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

    # Вивід перших 500 символів у лог для перевірки контенту перед відправкою в Groq
    print(f"📄 Перші 500 символів тексту для ISW: {truncated_text[:500]}")

    prompt = (
        "Ось звіт англійською мовою про останні події війни Росії проти України. "
        "Зроби стислий переказ українською мовою, приблизно 10-12 речень, "
        "охопи всі ключові тези: ситуацію на фронті по напрямках, ключові заяви й події, "
        "оцінки аналітиків, важливі деталі про озброєння чи тактику, якщо згадуються. "
        "\n\nВАЖЛИВО: Використовуй ТІЛЬКИ факти з наданого тексту нижче. "
        "НЕ додавай жодної інформації, дат чи цифр, яких немає в оригінальному тексті. "
        "Якщо якась деталь незрозуміла — краще пропусти її, ніж вигадуй."
        f"\n\n{truncated_text}"
    )

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1500
        )
        summary = response.choices[0].message.content.strip()
        return {"summary": summary}

    except Exception as e:
        # Лог тепер показує назву моделі й тип помилки — це прискорить
        # діагностику наступного разу (модель знову деактивують,
        # ключ протермінується, ліміт вичерпається тощо).
        print(
            f"⚠️ Помилка при перекладі ISW звіту (модель {GROQ_MODEL}): "
            f"{type(e).__name__}: {e}"
        )
        fallback_text = text[:1000] if len(text) > 1000 else text
        return {
            "summary": f"(не вдалося перекласти)\n\n{fallback_text}"
        }
