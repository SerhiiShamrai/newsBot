"""
Модуль для ротації цитат дня.
Зберігає стан показаних цитат у файлі quotes_state.json.
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

from quotes import QUOTES


STATE_FILE = "quotes_state.json"


def _load_state() -> dict:
    """Завантажити стан з файлу або створити новий."""
    state_path = Path(STATE_FILE)
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"shown_indices": [], "last_shown": None}


def _save_state(state: dict) -> None:
    """Зберегти стан у файл."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_next_quote() -> str | None:
    """
    Отримати наступну цитату для показу.
    
    Якщо всі цитати вже були показані — починає новий цикл.
    Випадковим чином обирає індекс з тих, що ще не в shown_indices.
    Додає цей індекс до shown_indices і зберігає стан.
    
    Повертає текст цитати або None, якщо QUOTES порожній.
    """
    if not QUOTES:
        return None
    
    state = _load_state()
    shown_indices = set(state.get("shown_indices", []))
    
    # Якщо всі цитати вже були показані — скидаємо список
    if len(shown_indices) >= len(QUOTES):
        shown_indices = set()
    
    # Отримуємо індекси, які ще не були показані
    available_indices = [i for i in range(len(QUOTES)) if i not in shown_indices]
    
    if not available_indices:
        # На випадок, якщо щось пішло не так — починаємо з нуля
        shown_indices = set()
        available_indices = list(range(len(QUOTES)))
    
    # Випадковим чином обираємо індекс
    chosen_index = random.choice(available_indices)
    shown_indices.add(chosen_index)
    
    # Оновлюємо стан
    state["shown_indices"] = list(shown_indices)
    state["last_shown"] = date.today().isoformat()
    _save_state(state)
    
    return QUOTES[chosen_index]