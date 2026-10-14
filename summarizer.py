import os
from openai import OpenAI


# Скільки символів опису максимум віддаємо моделі.
MAX_DESCRIPTION_CHARS = 3000


def generate_summary(title: str, description: str) -> dict:
    """
    Генерує власний заголовок та переказ новини через Groq API.

    Args:
        title: Оригінальний заголовок новини
        description: Опис/текст новини

    Returns:
        dict з ключами "title" (новий заголовок) та "summary" (переказ)
    """
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"]
    )

    # Дуже довгі тексти (повні статті з RSS) не передаємо в модель цілком:
    # так менше шансів упертися в ліміти Groq, а для переказу вистачає початку.
    description = (description or "")[:MAX_DESCRIPTION_CHARS]

    prompt = f"""Ось новина. Заголовок: {title}. Опис: {description}.
Твоє завдання:
1. Придумай власний короткий заголовок (до 10 слів), що відображає суть новини
2. Напиши короткий переказ українською мовою, 2-3 речення, тільки головна думка.
   Якщо опис порожній — нічого не вигадуй, залиш "summary" порожнім рядком.

Дай відповідь СТРОГО у форматі JSON, без пояснень і без markdown-розмітки:
{{"title": "...", "summary": "..."}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )

        content = response.choices[0].message.content.strip()

        # Очищення відповіді від можливих маркдаун-тегів
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        import json
        result = json.loads(content)

        new_title = result.get("title")
        new_summary = result.get("summary")

        return {
            "title": new_title if isinstance(new_title, str) and new_title.strip() else title,
            "summary": new_summary if isinstance(new_summary, str) else ""
        }

    except Exception as e:
        print(f"⚠️ Помилка при генерації summary: {e}")
        # Fallback: оригінальний заголовок і БЕЗ переказу. Сирий опис (який
        # може бути повною статтею на тисячі символів) у пост не підставляємо.
        return {
            "title": title,
            "summary": ""
        }