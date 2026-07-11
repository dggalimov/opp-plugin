"""Темы оформления OPP: загрузка, проверка, выбор активной темы.

Тема — это данные (yaml). Используется и для документов, и для оформления окна. Тема по умолчанию —
«Первый Бит». У проекта может быть своя тема (файл «Оформление.yaml» в папке проекта).
"""

from __future__ import annotations
from pathlib import Path

HERE = Path(__file__).resolve().parent
THEMES_DIR = HERE / "themes"
DEFAULT_THEME = THEMES_DIR / "первый-бит.yaml"
PROJECT_THEME_FILE = "Оформление.yaml"

_FALLBACK = {
    "accent": "#E4007E", "secondary": "#12A5A5",
    "text": "#1A1A1A", "bg": "#FFFFFF", "block": "#F4F4F4",
}


def load_theme(path) -> dict:
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def validate_theme(theme) -> list[str]:
    """Проверить тему. Пустой список — всё в порядке."""
    problems: list[str] = []
    if not isinstance(theme, dict):
        return ["тема пуста или не является объектом"]
    if not theme.get("id"):
        problems.append("нет поля «id»")
    if not theme.get("название"):
        problems.append("нет поля «название»")
    pal = theme.get("палитра")
    if not isinstance(pal, dict):
        problems.append("нет палитры")
    else:
        for key in ("акцент", "текст", "фон"):
            if not pal.get(key):
                problems.append(f"в палитре нет «{key}»")
    return problems


def palette(theme) -> dict:
    """Цвета темы в виде hex с решёткой (для CSS)."""
    pal = (theme or {}).get("палитра", {}) if isinstance(theme, dict) else {}

    def hx(key: str, default: str) -> str:
        value = (pal.get(key) or default).strip()
        return value if value.startswith("#") else "#" + value

    return {
        "accent": hx("акцент", "E4007E"),
        "secondary": hx("вторичный", "12A5A5"),
        "text": hx("текст", "1A1A1A"),
        "bg": hx("фон", "FFFFFF"),
        "block": hx("фон_блока", "F4F4F4"),
    }


def load_active_theme(project_path=None) -> dict:
    """Активная тема проекта (его «Оформление.yaml») или тема по умолчанию."""
    if project_path:
        candidate = Path(project_path) / PROJECT_THEME_FILE
        if candidate.is_file():
            try:
                theme = load_theme(candidate)
                if not validate_theme(theme):
                    return theme
            except Exception:
                pass
    try:
        return load_theme(DEFAULT_THEME)
    except Exception:
        return {"id": "fallback", "название": "Запасная", "палитра": {
            "акцент": "E4007E", "текст": "1A1A1A", "фон": "FFFFFF"}}


def active_palette(project_path=None) -> dict:
    try:
        return palette(load_active_theme(project_path))
    except Exception:
        return dict(_FALLBACK)
