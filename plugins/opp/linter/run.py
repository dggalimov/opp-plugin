"""Контролёр целостности: единая точка прогона проверок памяти рабочего пространства."""

from __future__ import annotations
from pathlib import Path

from .model import load_memory, MemoryLoadError
from .checks import check_memory
from .violation import Violation


def lint_workspace(workspace) -> list[Violation]:
    """Проверить память рабочего пространства. Пустая память → нет нарушений."""
    try:
        memory = load_memory(Path(workspace))
    except MemoryLoadError as exc:
        return [Violation(where=str(workspace), message=str(exc))]
    return check_memory(memory)
