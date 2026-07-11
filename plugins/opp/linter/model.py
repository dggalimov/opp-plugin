"""Загрузка проектной памяти в модель.

Память лежит в `<рабочее-пространство>/memory/*.yaml`. Каждый файл — одна таблица фактов; имя файла
(без расширения) — имя таблицы. Содержимое читается «в модель» через YAML (не разбором текста по
шаблонам). На пустой памяти модель пуста.

В Итерации 0 памяти ещё нет — функция отрабатывает на пустой папке и возвращает пустую модель.
Полный состав таблиц и полей появится в Итерации 4.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Row:
    table: str
    data: dict
    source_file: str


@dataclass
class Memory:
    rows: list[Row] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.rows


class MemoryLoadError(Exception):
    """Память есть, но прочитать не удалось (нет PyYAML или битый YAML)."""


def load_memory(workspace: Path) -> Memory:
    """Прочитать память рабочего пространства в модель. Пустая/отсутствующая память → пустая модель."""
    mem = Memory()
    mem_dir = Path(workspace) / "memory"
    if not mem_dir.is_dir():
        return mem

    yaml_files = sorted(p for p in mem_dir.glob("*.yaml") if p.is_file())
    if not yaml_files:
        return mem  # пустая память — это нормально

    try:
        import yaml
    except ImportError as exc:  # библиотека нужна только когда память реально не пуста
        raise MemoryLoadError(
            "Для чтения файлов памяти нужна библиотека PyYAML. Установите её в локальное окружение: "
            "./.venv/bin/python -m pip install pyyaml"
        ) from exc

    for yf in yaml_files:
        try:
            content = yaml.safe_load(yf.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise MemoryLoadError(f"Не удалось прочитать {yf.name}: {exc}") from exc

        if content is None:
            continue
        table = yf.stem
        if isinstance(content, list):
            items = content
        elif isinstance(content, dict) and isinstance(content.get("rows"), list):
            items = content["rows"]
        else:
            items = [content]
        for item in items:
            data = item if isinstance(item, dict) else {"value": item}
            mem.rows.append(Row(table=table, data=data, source_file=yf.name))

    return mem
