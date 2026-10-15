"""
Модуль для отримання й перекладу звітів ISW (Institute for the Study of War).
"""

import json
import os
import time
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openai import (
    APIConnectionError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

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


def _container_text(container) -> str:
    """Текст абзаців/заголовків/пунктів списку всередині контейнера."""
    lines = []
    for elem in container.find_all(["p", "h2", "h3", "h4", "li"]):
        text = elem.get_text(" ", strip=True)
        if not text or "{{" in text:
            continue
        # Короткі <li> — це переважно пункти меню, а не текст звіту.
        if elem.name == "li" and len(text) < 60:
            continue
        lines.append(text)
    return "\n\n".join(lines)


def _longest_json_string(node, best: str = "") -> str:
    """Найдовший рядок усередині розібраного JSON (рекурсивно)."""
    if isinstance(node, str):
        return node if len(node) > len(best) else best
    if isinstance(node, dict):
        for value in node.values():
            best = _longest_json_string(value, best)
    elif isinstance(node, list):
        for value in node:
            best = _longest_json_string(value, best)
    return best


def _extract_from_embedded_json(soup) -> Optional[str]:
    """
    Запасний варіант для сторінок, де текст підвантажується скриптом:
    шукає у JSON-блоках (__NEXT_DATA__, application/json тощо) найдовший
    рядок і чистить його від HTML-тегів.
    """
    best = ""
    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        if "json" not in script_type and script.get("id") not in ("__NEXT_DATA__", "__NUXT_DATA__"):
            continue
        raw = script.string or script.get_text()
        if not raw or len(raw) < MIN_REPORT_CHARS:
            continue
        try:
            best = _longest_json_string(json.loads(raw), best)
        except ValueError:
            continue

    if len(best) < MIN_REPORT_CHARS:
        return None

    cleaned = BeautifulSoup(best, "html.parser")
    lines = [
        t for t in (el.get_text(" ", strip=True) for el in cleaned.find_all(["p", "h2", "h3", "h4", "li"]))
        if t and "{{" not in t
    ]
    text = "\n\n".join(lines) if lines else cleaned.get_text("\n", strip=True)
    return text if len(text) >= MIN_REPORT_CHARS else None


def _describe_page(html: str, soup) -> str:
    """Короткий опис сторінки для логу, щоб було видно, чому текст не знайшовся."""
    title = soup.title.get_text(strip=True)[:120] if soup.title else "—"
    json_scripts = sum(
        1 for s in soup.find_all("script")
        if "json" in (s.get("type") or "").lower() or s.get("id") in ("__NEXT_DATA__", "__NUXT_DATA__")
    )
    return (
        f"title='{title}', html={len(html)} символів, "
        f"article={len(soup.find_all('article'))}, main={len(soup.find_all('main'))}, "
        f"p={len(soup.find_all('p'))}, li={len(soup.find_all('li'))}, json-скриптів={json_scripts}"
    )


def _extract_report_text(html: str) -> Optional[str]:
    """
    Дістає текст звіту з HTML сторінки.

    Не покладається на перший-ліпший <article> (це може бути маленька картка
    «читайте також»): серед усіх кандидатів — <article>, <main>, контейнери
    з "content"/"body" у класі та <body> — бере той, де найбільше тексту.
    Відкидає навігацію/футер і незаповнені шаблонні плейсхолдери ({{...}}).
    Якщо в HTML тексту немає (його малює скрипт) — пробує JSON усередині
    сторінки. Повертає None, якщо тексту замало, щоб бути справжнім звітом.
    """
    soup = BeautifulSoup(html, "html.parser")

    # JSON-скрипти читаємо до того, як прибрати <script> з дерева.
    json_text = _extract_from_embedded_json(soup)
    page_info = _describe_page(html, soup)

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    candidates = list(soup.find_all("article")) + list(soup.find_all("main"))
    candidates += soup.find_all(
        "div",
        class_=lambda c: c and any(k in c.lower() for k in ("entry-content", "post-content", "content", "body", "text")),
    )
    if soup.body:
        candidates.append(soup.body)

    best_text = ""
    for container in candidates:
        text = _container_text(container)
        if len(text) > len(best_text):
            best_text = text

    if len(best_text) >= MIN_REPORT_CHARS:
        return best_text
    if json_text:
        return json_text

    print(f"ℹ️ Діагностика сторінки: {page_info}; найбільше тексту у контейнері: {len(best_text)} символів")
    return None


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


# --- Переказ звіту ---------------------------------------------------------

# Повний звіт ISW — десятки тисяч символів. Раніше бот віддавав моделі лише
# перші 10 000, тому переказ охоплював тільки початок. Тепер довгий звіт
# ділиться на частини: з кожної модель виписує ключові факти, а потім із
# цієї добірки робиться один зв'язний переказ усього звіту.
SINGLE_PASS_CHARS = 14000   # до цього розміру звіт іде в модель одним запитом
CHUNK_CHARS = 9000          # розмір однієї частини для довгого звіту
MAX_CHUNKS = 7              # запобіжник: не більше стількох частин
CHUNK_PAUSE_SEC = float(os.environ.get("ISW_CHUNK_PAUSE_SEC", "6"))  # пауза проти лімітів Groq

# Telegram приймає до 4096 символів разом із заголовком і посиланням.
SUMMARY_TARGET_CHARS = 2800  # на скільки символів просимо переказ
SUMMARY_HARD_CHARS = 3600    # довше за це — просимо модель скоротити

SKIP_MARKER = "ПРОПУСТИТИ"


def _split_into_chunks(text: str, size: int) -> list[str]:
    """Ділить текст на частини до `size` символів по межах абзаців."""
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        # Надто довгий абзац ріжемо жорстко, щоб він не розпирав частину.
        while len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:size])
            paragraph = paragraph[size:]
        if current and len(current) + len(paragraph) + 2 > size:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def _call_llm(client: OpenAI, prompt: str, max_tokens: int, temperature: float = 0.3) -> tuple[str, str]:
    """
    Один запит до моделі з повторами при лімітах/збоях мережі.

    Returns:
        (текст відповіді, finish_reason). finish_reason == "length" означає,
        що модель обірвалась на ліміті токенів і текст неповний.
    """
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = response.choices[0]
            return (choice.message.content or "").strip(), choice.finish_reason or ""
        except (RateLimitError, APIConnectionError, InternalServerError) as e:
            if attempt == attempts:
                raise
            wait = 15 * attempt
            print(f"⏳ {type(e).__name__}, повтор через {wait} с (спроба {attempt}/{attempts})")
            time.sleep(wait)
    return "", ""


def _chunk_prompt(chunk: str, index: int, total: int) -> str:
    return (
        f"Це частина {index} з {total} щоденного аналітичного звіту про війну Росії "
        "проти України (англійською). Випиши українською ключові факти саме з цього "
        "фрагмента: 5-8 коротких пунктів, кожен — одне речення. Що і де відбулося, "
        "хто що заявив, які оцінки дали аналітики, що важливого про озброєння чи тактику. "
        "Використовуй ТІЛЬКИ факти з тексту, нічого не вигадуй. "
        f"Якщо фрагмент складається лише з посилань, приміток чи службового тексту — "
        f"відповідай одним словом: {SKIP_MARKER}."
        f"\n\n{chunk}"
    )


def _final_prompt(material: str, from_facts: bool) -> str:
    source = (
        "добірка ключових фактів, виписаних з усіх частин звіту"
        if from_facts
        else "текст звіту"
    )
    return (
        "Нижче — " + source + " щоденного аналітичного звіту ISW про війну Росії проти України. "
        "Зроби з нього змістовний стислий переказ українською мовою, як для ранкової новинної добірки.\n\n"
        "Вимоги:\n"
        f"- Загальний обсяг — не більше {SUMMARY_TARGET_CHARS} символів.\n"
        "- Почни з 1-2 речень про головне за добу, далі — ключові події по напрямках фронту, "
        "важливі заяви, оцінки аналітиків, деталі про озброєння чи тактику.\n"
        "- Відбирай найважливіше, а не переказуй усе підряд; другорядне пропускай.\n"
        "- Закінчуй повним реченням.\n"
        "- Використовуй ТІЛЬКИ факти з тексту; не додавай дат, цифр чи подій, яких там немає.\n"
        "- Пиши суцільним текстом без markdown-розмітки (без зірочок, решіток, списків з дефісами).\n\n"
        f"{material}"
    )


def _shorten_prompt(summary: str) -> str:
    return (
        f"Скороти цей переказ до {SUMMARY_TARGET_CHARS} символів. Збережи найважливіші факти, "
        "нічого не додавай, закінчи повним реченням. Без markdown-розмітки.\n\n"
        f"{summary}"
    )


def translate_and_summarize_isw(text: str) -> dict:
    """
    Робить стислий переказ звіту ISW українською мовою через Groq API.

    Короткий звіт іде в модель одним запитом. Довгий ділиться на частини:
    з кожної виписуються ключові факти, а з них пишеться підсумковий переказ.
    Якщо відповідь вийшла надто довгою або обірвалась, модель просять скоротити,
    а не різати текст механічно.

    Args:
        text: Текст звіту англійською мовою

    Returns:
        Словник {"summary": "переказ"} або fallback при помилці
    """
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
        max_retries=3,
    )

    print(f"📄 Перші 500 символів тексту для ISW: {text[:500]}")

    try:
        if len(text) <= SINGLE_PASS_CHARS:
            material, from_facts = text, False
        else:
            chunks = _split_into_chunks(text, CHUNK_CHARS)[:MAX_CHUNKS]
            print(f"🧩 Звіт довгий ({len(text)} символів), ділю на {len(chunks)} частин")
            partials: list[str] = []
            for i, chunk in enumerate(chunks, 1):
                if i > 1:
                    time.sleep(CHUNK_PAUSE_SEC)
                part, _ = _call_llm(client, _chunk_prompt(chunk, i, len(chunks)), 2000)
                if part and part.strip(" .!\n").upper() != SKIP_MARKER:
                    partials.append(part)
            if not partials:
                raise ValueError("жодна частина звіту не дала фактів")
            material, from_facts = "\n\n".join(partials), True
            time.sleep(CHUNK_PAUSE_SEC)

        summary, finish = _call_llm(client, _final_prompt(material, from_facts), 3000)
        if not summary:
            raise ValueError("модель повернула порожню відповідь")

        if finish == "length" or len(summary) > SUMMARY_HARD_CHARS:
            print(f"✂️ Переказ завеликий або обірваний ({len(summary)} символів), прошу скоротити")
            time.sleep(CHUNK_PAUSE_SEC)
            shorter, finish2 = _call_llm(client, _shorten_prompt(summary), 3000)
            if shorter and finish2 != "length":
                summary = shorter

        print(f"📝 Переказ готовий ({len(summary)} символів)")
        return {"summary": summary}

    except Exception as e:
        # Лог показує назву моделі й тип помилки — це прискорить діагностику
        # наступного разу (модель деактивують, ключ протермінується, ліміт вичерпається).
        print(
            f"⚠️ Помилка при перекладі ISW звіту (модель {GROQ_MODEL}): "
            f"{type(e).__name__}: {e}"
        )
        fallback_text = text[:1000] if len(text) > 1000 else text
        return {
            "summary": f"(не вдалося перекласти)\n\n{fallback_text}"
        }
