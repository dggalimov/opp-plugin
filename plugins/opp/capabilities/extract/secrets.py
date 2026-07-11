"""Секреты сотрудника (API-ключи): глобально, не в проекте.

Ключ (Ньютон и будущие) — персональный для сотрудника, а не проектный: хранится вне папки
проекта, поэтому физически не может утечь в git проекта (ЗР-0025 п.2). Каскад чтения:
переменная окружения → файл `~/.config/opp/secrets.env` (KEY=VALUE построчно, права 600).
"""

from __future__ import annotations
import os
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "opp" / "secrets.env"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def get_secret(name: str, path: Path = DEFAULT_PATH) -> str | None:
    """Каскад: переменная окружения → файл secrets.env. Нет нигде → None (не ошибка)."""
    value = os.environ.get(name)
    if value:
        return value
    return _read_env_file(path).get(name) or None


def save_secret(name: str, value: str, path: Path = DEFAULT_PATH) -> Path:
    """Записать/заменить ключ в secrets.env (создать каталог/файл при отсутствии, права 600)."""
    values = _read_env_file(path)
    values[name] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path
