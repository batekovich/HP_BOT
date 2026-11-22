import json
from pathlib import Path

from config import (
    EXP_NAME,
    FAST_NAME,
    NORMAL_NAME,
    SOSATEL_NAME,
    SUPER_NAME,
)


strings_path = Path(__file__).resolve().parent / "strings.json"
with strings_path.open(encoding="utf-8") as strings_file:
    _STR = json.load(strings_file)


def STR(key: str) -> str:
    return _STR.get(key, key)


def human_time_left(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts: list[str] = []
    if h:
        parts.append(f"{h} ч")
    if m:
        parts.append(f"{m} мин")
    if s or not parts:
        parts.append(f"{s} сек")
    return " ".join(parts)


def format_with_names(template: str, **kwargs: object) -> str:
    base: dict[str, object] = {
        "normal_name": NORMAL_NAME,
        "fast_name": FAST_NAME,
        "super_name": SUPER_NAME,
        "exp_name": EXP_NAME,
        "sosatel_name": SOSATEL_NAME,
    }
    base.update(kwargs)
    return template.format(**base)
