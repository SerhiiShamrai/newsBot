import os
from openai import OpenAI


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

    prompt = f"""Ось новина. Заголовок: {title}. Опис: {description}.
Твоє завдання:
1. Придумай власний короткий заголовок (до 10 слів), що відображає суть новини
2. Напиши короткий переказ українською мовою, 2-3 речення, тільки головна думка

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

        return {
            "title": result.get("title", title),
            "summary": result.get("summary", description)
        }

    except Exception as e:
        print(f"⚠️ Помилка при генерації summary: {e}")
        # Fallback: повертаємо оригінальні дані
        return {
            "title": title,
            "summary": description
        }