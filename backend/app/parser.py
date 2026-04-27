import re
from datetime import date, timedelta

from rapidfuzz import fuzz

# Триггеры сортированы от длинных к коротким — важно для окна поиска
TRIGGERS = [
    ("дата выполнения задачи", "date"),
    ("время на задачу",        "time_spent"),
    ("действия по задаче",     "description"),
    ("номер задачи",           "task"),
]

FUZZY_THRESHOLD = 68  # % совпадения: допускает ~32% ошибок распознавания

MISSING_LABELS = {
    "task":        "номер задачи",
    "time_spent":  "время на задачу",
    "date":        "дату выполнения задачи",
    "description": "действия по задаче",
}

_DATE_WORDS = {"сегодня": 0, "сейчас": 0, "вчера": -1, "позавчера": -2}

_MONTHS_RU = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
    "май": 5, "мая": 5, "июн": 6, "июл": 7, "август": 8,
    "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def _normalize_date(raw: str) -> str:
    s = raw.strip().lower()
    today = date.today()
    for word, delta in _DATE_WORDS.items():
        if word in s:
            return (today + timedelta(days=delta)).isoformat()
    m = re.search(r"(\d{1,2})[^\d]+(\w+)", s)
    if m:
        day, month_str = int(m.group(1)), m.group(2)[:6]
        for key, num in _MONTHS_RU.items():
            if month_str.startswith(key[:4]):
                try:
                    return date(today.year, num, day).isoformat()
                except ValueError:
                    pass
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else today.year
        if yr < 100:
            yr += 2000
        try:
            return date(yr, mo, d).isoformat()
        except ValueError:
            pass
    return raw


def _find_triggers(text: str) -> list[tuple[int, int, str]]:
    """
    Возвращает список (trigger_start, value_start, field) отсортированный по позиции.
    trigger_start — для определения границ значений,
    value_start   — откуда начинается само значение поля.
    """
    text_lower = text.lower()
    words = text_lower.split()

    # Позиции начала каждого слова в строке
    word_starts: list[int] = []
    pos = 0
    for w in words:
        word_starts.append(pos)
        pos += len(w) + 1

    found: list[tuple[int, int, int, str]] = []  # (score, trig_start, val_start, field)

    for trigger, field in TRIGGERS:
        trigger_words = trigger.split()
        n = len(trigger_words)
        best_score, best_i = 0, -1

        for i in range(len(words) - n + 1):
            window = " ".join(words[i:i + n])
            score = fuzz.ratio(window, trigger)
            if score > best_score:
                best_score, best_i = score, i

        if best_score >= FUZZY_THRESHOLD and best_i != -1:
            trig_start = word_starts[best_i]
            val_word_idx = best_i + n
            val_start = word_starts[val_word_idx] if val_word_idx < len(word_starts) else len(text)
            found.append((trig_start, val_start, field))

    return sorted(found, key=lambda x: x[0])


def _build_question(missing: list[str]) -> str:
    labels = [MISSING_LABELS[f] for f in missing]
    if len(labels) == 1:
        return f"Не расслышал {labels[0]}. Можешь повторить?"
    return "Не расслышал " + ", ".join(labels[:-1]) + " и " + labels[-1] + ". Можешь повторить?"


def _build_voice_response(_parsed: dict) -> str:
    return "Запись успешно сохранена в файл."


def parse_worklog(text: str, context: dict | None = None) -> dict:
    result: dict = dict(context or {})
    triggers = _find_triggers(text)

    for i, (trig_start, val_start, field) in enumerate(triggers):
        val_end = triggers[i + 1][0] if i + 1 < len(triggers) else len(text)
        value = text[val_start:val_end].strip(" .,;:\n")
        if value:
            result[field] = value

    if result.get("date"):
        result["date"] = _normalize_date(result["date"])

    required = ["task", "time_spent", "date"]
    missing = [f for f in required if not result.get(f)]

    result["needs_clarification"] = bool(missing)
    result["question"] = _build_question(missing) if missing else None
    result["voice_response"] = _build_question(missing) if missing else _build_voice_response(result)

    return result
