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

_HOURS_WORDS = {
    "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
    "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
}

_MINUTES_WORDS = {
    **_HOURS_WORDS,
    "пятнадцать": 15, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "десять": 10, "пятнадцать": 15,
}


def _normalize_task(raw: str, prefix: str = "") -> str:
    """Build task key from voice-extracted value and optional UI prefix."""
    digits = re.sub(r"\D", "", raw.strip())
    if prefix and digits:
        return f"{prefix}-{digits}"
    s = raw.strip()
    if re.match(r"^[A-Za-z]{1,5}-\d+$", s):
        return s.upper()
    if digits:
        return digits
    return s


def parse_task_only(text: str, prefix: str) -> str:
    """Extract digits from text and combine with prefix. Used for task re-record."""
    digits = re.sub(r"\D", "", text)
    return f"{prefix}-{digits}" if (prefix and digits) else digits


def _normalize_time(raw: str) -> str:
    """Приводит время к формату Jira: 1h 25m."""
    s = raw.strip().lower()

    # Уже в формате 1h 25m
    if re.match(r"^\d+h(\s+\d+m)?$", s) or re.match(r"^\d+m$", s):
        return s

    hours = 0
    minutes = 0

    # Числа словами или цифрами перед "час" и "минут"
    h_match = re.search(r"(\d+|[а-яё]+)\s*час", s)
    m_match = re.search(r"(\d+|[а-яё]+)\s*мин", s)

    if h_match:
        val = h_match.group(1)
        hours = int(val) if val.isdigit() else _HOURS_WORDS.get(val, 0)
    if m_match:
        val = m_match.group(1)
        minutes = int(val) if val.isdigit() else _MINUTES_WORDS.get(val, 0)

    if hours or minutes:
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        return " ".join(parts)

    return raw


def _normalize_date(raw: str) -> str | None:
    """Возвращает дату ISO или None если не удалось распознать."""
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
    return None


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


def parse_worklog(text: str, context: dict | None = None, task_prefix: str = "") -> dict:
    result: dict = dict(context or {})
    triggers = _find_triggers(text)

    for i, (trig_start, val_start, field) in enumerate(triggers):
        val_end = triggers[i + 1][0] if i + 1 < len(triggers) else len(text)
        value = text[val_start:val_end].strip(" .,;:\n")
        if value:
            result[field] = value

    if result.get("task"):
        result["task"] = _normalize_task(result["task"], prefix=task_prefix)

    if result.get("time_spent"):
        result["time_spent"] = _normalize_time(result["time_spent"])

    if result.get("date"):
        normalized = _normalize_date(result["date"])
        result["date"] = normalized if normalized else None

    required = ["task", "time_spent", "date"]
    missing = [f for f in required if not result.get(f)]

    result["needs_clarification"] = bool(missing)
    result["question"] = _build_question(missing) if missing else None
    result["voice_response"] = _build_question(missing) if missing else _build_voice_response(result)

    return result
