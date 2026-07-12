"""Развёртывание рабочей папки проекта из каркаса и сценария.

Структура выводится из `reference/framework.yaml` (папки по 11 уровням) + сценария (каналы определяют,
какие подпапки источников создавать) — а не копируется из фиксированного шаблона. Одинаковые входы →
одинаковая структура. Идемпотентно: повторный запуск создаёт недостающее и НЕ затирает уже
заполненные файлы (паспорт/правила/тему).

Соответствие «песочным часам»: Источники (сырьё, техслой под «Проектной памятью») →
Проектная память (факты по уровням) → Документы.
"""

from __future__ import annotations
from pathlib import Path

from capabilities import paths

_STATUS_YAML = (
    "# машинный файл статуса проекта; ведут навыки (не правится руками)\n"
    "онбординг:\n"
    "  завершён: false\n"
    "  шаг: 0\n"
    "методика-синтеза-показана: false\n"
)

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "reference"

ALL_CHANNELS = ["документы", "база данных", "интервью"]
_CHANNEL_FOLDER = {"документы": "Документы", "база данных": "База данных", "интервью": "Интервью"}


def _safe_name(name: str) -> str:
    """Имя папки без символов-разделителей пути (напр. «НСИ / аналитики» → «НСИ · аналитики»)."""
    for bad in ("/", "\\", ":"):
        name = name.replace(bad, "·")
    return name.strip()


def _level_folders() -> list[str]:
    from reference.framework import load_framework
    fw = load_framework()
    return [f'{lvl["номер"]} — {_safe_name(lvl["название"])}' for lvl in fw["уровни"]]


def _overview_text(name: str, channels: list[str]) -> str:
    return (
        f"# Обзор проекта\n\n"
        f"- Проект: {name}\n"
        f"- Каналы: {', '.join(channels)}\n\n"
        f"Структура: **Проектная память/Источники** (сырьё) → **Проектная память** (факты по "
        f"11 уровням каркаса) → **Документы** (результат).\n\n"
        f"Паспорт, правила и оформление — в корне проекта; правятся в окне (`./opp ui`).\n"
    )


def deploy_workspace(target, channels=None) -> list[Path]:
    """Развернуть/починить рабочую папку. Возвращает список созданных элементов."""
    target = Path(target)
    channels = [c for c in (channels or ALL_CHANNELS) if c in _CHANNEL_FOLDER] or ALL_CHANNELS
    created: list[Path] = []

    def mkdir(path: Path) -> None:
        if not path.exists():
            path.mkdir(parents=True)
            created.append(path)

    def place(relpath: str, text: str) -> None:
        f = target / relpath
        if not f.exists():
            f.write_text(text, encoding="utf-8")
            created.append(f)

    mkdir(target)

    # приёмные папки (ЗР-0025): пользовательское — сюда владелец кладёт файлы, ingest читает
    # отсюда; технический слой узлов-источников — в «Проектная память/Источники/» (ЗР-0027 п.7),
    # пользователь туда не ходит.
    mkdir(target / "Входные материалы")
    mkdir(target / "Встречи")

    memory = target / "Проектная память"
    mkdir(memory)
    karkas = memory / "Каркас"
    mkdir(karkas)
    for folder in _level_folders():
        mkdir(karkas / folder)
    mkdir(memory / "Наложения")
    mkdir(memory / "Рабочие")

    # paths.sources_dir мигрирует старый корневой «Источники/» при первом обращении, если есть.
    sources = paths.sources_dir(target)
    mkdir(sources)
    for ch in channels:
        mkdir(sources / _CHANNEL_FOLDER[ch])

    mkdir(target / "Документы")

    place("Паспорт проекта.md", (REFERENCE / "passport.template.md").read_text(encoding="utf-8"))
    place("Правила проекта.md", (REFERENCE / "principles.default.md").read_text(encoding="utf-8"))
    place("Оформление.yaml", (REFERENCE / "themes" / "первый-бит.yaml").read_text(encoding="utf-8"))
    place("обзор.md", _overview_text(target.name, channels))
    place(".gitignore", (REFERENCE / "gitignore.template").read_text(encoding="utf-8"))
    place(".статус.yaml", _STATUS_YAML)

    return created
