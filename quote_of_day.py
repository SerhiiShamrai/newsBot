"""
Модуль для ротації цитат дня.
Зберігає стан показаних цитат у файлі quotes_state.json.

Стан (файл quotes_state.json) обов'язково зберігається та оновлюється
в межах репозиторію, щоб GitHub Actions міг закомітити його назад
і наступний запуск продовжив ротацію з правильного місця.
"""

import json
from datetime import date
from pathlib import Path

from quotes import QUOTES


# Директорій, де лежить цей модуль (корінь репозиторію).
_MODULE_DIR = Path(__file__).resolve().parent


STATE_FILE = "quotes_state.json"


def _resolve_state_paths() -> list[Path]:
    """
    Шляхи, де може лежати файл стану.

    Спочатку — відносно поточної директорії (зворотна сумісність),
    потім — поруч із модулем (корінь репозиторію). Другий варіант
    гарантує, що навіть якщо скрипт запускається з іншої директорії,
    стан все одно буде записано всередину репозиторію, звідки
    GitHub Actions зможе його закомітити.
    """
    return [Path(STATE_FILE), _MODULE_DIR / STATE_FILE]


def _load_state() -> dict:
    """Завантажити стан з файлу або створити новий."""
    for state_path in _resolve_state_paths():
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if isinstance(state, dict):
                    return state
            except (json.JSONDecodeError, OSError):
                # Пошкоджений файл стану — починаємо з чистого листа.
                pass
    return {"shown_indices": [], "last_shown": None}


def _save_state(state: dict) -> None:
    """
    Зберегти стан у файл.

    Файл завжди записується в корінь репозиторію (поруч із модулем),
    щоб workflow міг зробити commit і push оновленого стану.
    Якщо поточна директорія відрізняється, робимо копію й там,
    щоб уникнути розбіжностей між двома можливими місцями зберігання.
    """
    repo_path = _MODULE_DIR / STATE_FILE
    with open(repo_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    cwd_path = Path(STATE_FILE).resolve()
    if cwd_path != repo_path.resolve():
        try:
            with open(cwd_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except OSError:
            pass


def get_next_quote() -> str | None:
    """
    Отримати наступну цитату для показу.
    
    Цитати йдуть одна за одною без повторень у межах циклу.
    Коли всі цитати показано — починається новий цикл (з першої).
    
    Повертає текст цитати або None, якщо QUOTES порожній.
    """
    if not QUOTES:
        return None
    
    state = _load_state()
    total = len(QUOTES)
    
    # Валідуємо збережені індекси: лишаємо лише коректні та унікальні.
    raw_shown = state.get("shown_indices", [])
    shown_indices: set[int] = set()
    if isinstance(raw_shown, list):
        for idx in raw_shown:
            if isinstance(idx, int) and 0 <= idx < total:
                shown_indices.add(idx)
    
    # Якщо всі цитати вже були показані — починаємо новий цикл.
    if len(shown_indices) >= total:
        shown_indices = set()
    
    available_indices = [i for i in range(total) if i not in shown_indices]
    
    if not available_indices:
        # Захист на випадок некоректного стану — починаємо з нуля.
        shown_indices = set()
        available_indices = list(range(total))
    
    # Беремо першу доступну цитату за порядком — так цитати гарантовано
    # слідують одна за одною без повторень до завершення всього списку.
    chosen_index = available_indices[0]
    shown_indices.add(chosen_index)
    
    # Оновлюємо стан (список показаних + історія останніх показів).
    history = state.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append({"index": chosen_index, "date": date.today().isoformat()})
    history = history[-total:]  # тримаємо історію не довшу за один цикл
    
    state["shown_indices"] = sorted(shown_indices)
    state["last_shown"] = date.today().isoformat()
    state["last_index"] = chosen_index
    state["history"] = history
    _save_state(state)
    
    return QUOTES[chosen_index]