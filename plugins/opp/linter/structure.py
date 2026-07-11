"""Структурный контроль репозитория.

Ловит запрещённые «устаревшие шапки»: баннеры и заголовки о замене/старой версии внутри документов.
Действующий документ = правда; наслоения старых версий внутри файла запрещены (история — в git).

Проверяются только заголовки markdown (строки, начинающиеся с #) и отдельные жирные строки-баннеры
(`**…**` целой строкой). Упоминания этих слов в обычном тексте (например, в описании самого правила)
не считаются нарушением.

Плюс: уникальность номеров записей решений (`decisions/NNNN-*.md`) — номер ЗР должен быть
однозначным адресом (аудит 02.07.2026: номера 0015 и 0016 делили по два файла).
"""

from __future__ import annotations
import re
from pathlib import Path

from .violation import Violation

_FORBIDDEN = re.compile(
    r"(DEPRECATED|SUPERSED|УСТАРЕЛО|УСТАРЕВШ|"
    r"СТАР(?:АЯ|ОЕ|ЫЕ)\s+ВЕРСИ|"
    r"ЗАМЕНЯЕТ\s+(?:СОБОЙ|ВЕРСИ|ПРЕДЫ)|"
    r"БОЛЬШЕ\s+НЕ\s+АКТУ)",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_BANNER = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")
_SKIP_DIRS = {".venv", ".git", "__pycache__", "node_modules"}


def check_structure(repo_root) -> list[Violation]:
    """Найти «устаревшие шапки» в markdown-файлах репозитория."""
    root = Path(repo_root)
    violations: list[Violation] = []

    for path in sorted(root.rglob("*.md")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for num, line in enumerate(lines, start=1):
            heading = _HEADING.match(line)
            banner = _BANNER.match(line)
            target = heading.group(1) if heading else (banner.group(1) if banner else None)
            if target and _FORBIDDEN.search(target):
                rel = path.relative_to(root)
                violations.append(Violation(
                    where=f"{rel}:{num}",
                    message="запрещённая «устаревшая шапка» в заголовке/баннере — правьте документ на месте",
                ))

    violations.extend(_check_decision_numbers(root))
    return violations


def _check_decision_numbers(root: Path) -> list[Violation]:
    """Номер ЗР (NNNN в decisions/NNNN-имя.md) встречается ровно один раз."""
    seen: dict[str, str] = {}
    violations: list[Violation] = []
    decisions = root / "decisions"
    if not decisions.is_dir():
        return []
    for path in sorted(decisions.glob("[0-9][0-9][0-9][0-9]-*.md")):
        num = path.name[:4]
        if num in seen:
            violations.append(Violation(
                where=f"decisions/{path.name}",
                message=f"дубль номера ЗР {num} (уже занят: decisions/{seen[num]}) — номер должен быть уникальным адресом",
            ))
        else:
            seen[num] = path.name
    return violations
