"""cap-instr — контракт правки per-project инструкций заполнения таблиц: read / save / revert.

Дефолт инструкции принадлежит КОНТРАКТУ (reg-facttables, schema/fact-tables.yaml) и здесь
НЕПРИКОСНОВЕНЕН. Правка пользователя живёт в `<проект>/инструкции/<КОД>.md`, ЗАМЕНЯЕТ дефолт целиком;
откат = удалить файл. Читающую половину переиспользуем из cap-t-extract
(`schema.extract._effective_instruction`) — не дублируем. Папка `инструкции/` создаётся лениво.
"""

from __future__ import annotations
from pathlib import Path

from .extract import _effective_instruction, _INSTR_DIR
from .model import load_schema


def _table(code: str):
    schema = load_schema()
    if code not in schema.tables:
        raise KeyError(f"нет таблицы «{code}» в контракте schema/fact-tables.yaml")
    return schema.tables[code]


def _override_path(code: str, workspace) -> Path:
    # защита от traversal: код пишем в имя файла — он должен быть «чистым» кодом таблицы
    if "/" in code or "\\" in code or ".." in code:
        raise ValueError(f"недопустимый код таблицы: {code!r}")
    return Path(workspace) / _INSTR_DIR / f"{code}.md"


def read_instruction(code: str, workspace) -> dict:
    """Эффективная инструкция таблицы + её источник + дефолт продукта (для «откатить к…»)."""
    table = _table(code)
    eff = _effective_instruction(table, Path(workspace))   # переиспользование cap-t-extract
    default = (table.instruction or {}).get("дефолт", "")
    return {
        "код": code,
        "эффективная": eff.get("эффективная", ""),
        "источник": eff.get("источник", ""),               # «дефолт продукта» | «правка проекта»
        "дефолт": default,
        "есть_правка": eff.get("источник") == "правка проекта",
        "файл": eff.get("файл"),
    }


def save_instruction(code: str, workspace, text: str):
    """Сохранить правку в <проект>/инструкции/<КОД>.md (папка — лениво). Замена дефолта целиком.

    Пустой текст → откат к дефолту (правка удаляется). Возвращает путь к файлу или None (если откат).
    """
    _table(code)                                           # код существует в контракте?
    text = (text or "").strip()
    if not text:
        revert_instruction(code, workspace)
        return None
    p = _override_path(code, workspace)
    p.parent.mkdir(parents=True, exist_ok=True)            # ленивое создание инструкции/
    p.write_text(text + "\n", encoding="utf-8")
    return p


def revert_instruction(code: str, workspace) -> bool:
    """Откат к дефолту продукта: удалить правку. True — была и удалена; False — правки не было."""
    _table(code)
    p = _override_path(code, workspace)
    if p.is_file():
        p.unlink()
        return True
    return False
