"""cap-t-extract — ядро наполнения таблиц фактов: сырьё проекта → валидные строки таблиц (silver).

Первое «T:»-преобразование доказательной цепочки (Источник → Факт уровня, методика р.2). Это РЕЛЬСЫ,
а не экстрактор: само суждение (читать источник, выносить факт со статусом и источником) делает навык
(opp:analyze-materials / analyze-meeting / synthesis). cap-t-extract даёт детерминированную обвязку:

- `fill_request(код, проект)` — задание на извлечение: поля контракта + эффективная инструкция
  (дефолт схемы + правка проекта, если есть) + входы (сырьё, таблицы-предшественники, БЗ по роли);
- `write_rows(код, строки, проект)` — приём строк: валидация против контракта (схема) и запись в
  `<проект>/memory/<код>.yaml` с накоплением: строка с тем же ключом СЛИВАЕТСЯ (непустое поверх,
  источники списком, прежний снимок — в «историю»; методика р.3, Р-3 ЗР-0020).

Задание на извлечение отдаёт агенту ВИДИМОСТЬ памяти (K2-2, ЗР-0020): занятые коды своей таблицы
(дедуп, стабильность кодов) и коды+формулировки предшественников (резолв ссылок не вслепую).

Существование межтабличных ссылок проверяет НЕ здесь, а аудит замкнутости (cap-t-closure).
Переиспользует `schema.model` (контракт) и `linter.Violation` (общий тип нарушения).
"""

from __future__ import annotations
from pathlib import Path

from capabilities import paths
from linter.violation import Violation
from .model import load_schema, Table, targets_of

_MEMORY_DIR = "memory"        # строки таблиц фактов (silver)
_INSTR_DIR = "инструкции"     # правка инструкции пользователем per-project: <ws>/инструкции/<код>.md


def _yaml():
    import yaml
    return yaml


def _table(code: str, schema=None) -> Table:
    schema = schema if schema is not None else load_schema()
    if code not in schema.tables:
        raise KeyError(f"нет таблицы «{code}» в контракте schema/fact-tables.yaml")
    return schema.tables[code]


def _effective_instruction(table: Table, workspace: Path) -> dict:
    """Эффективная инструкция: правка проекта заменяет дефолт (не склейка); нет правки → дефолт."""
    default = (table.instruction or {}).get("дефолт", "")
    override = Path(workspace) / _INSTR_DIR / f"{table.code}.md"
    if override.is_file():
        text = override.read_text(encoding="utf-8").strip()
        if text:
            return {"эффективная": text, "источник": "правка проекта", "файл": str(override)}
    return {"эффективная": default, "источник": "дефолт продукта"}


def _predecessors(table: Table, schema, workspace: Path) -> list:
    """Таблицы-предшественники: коды таблиц, на которые ссылается эта (рёбра + цели полей)."""
    codes = set()
    for src in (e.target for e in table.edges):
        for t in targets_of(src):
            if isinstance(t, str) and t in schema.tables and t != table.code:
                codes.add(t)
    for src in (f.target for f in table.fields):
        for t in targets_of(src):
            if isinstance(t, str) and t in schema.tables and t != table.code:
                codes.add(t)
    return [{"код": c, "название": schema.tables[c].title,
             "строки_в_памяти": _memory_digest(schema.tables[c], workspace)} for c in sorted(codes)]


def _memory_digest(table: Table, workspace: Path, максимум: int = 200) -> list:
    """Дайджест строк таблицы из памяти: {ключ, формулировка} — чтобы агент резолвил ссылки
    и дедуплицировал по существующим кодам, не читая memory/*.yaml целиком (K2-2, ЗР-0020)."""
    f = Path(workspace) / _MEMORY_DIR / f"{table.code}.yaml"
    if not f.is_file():
        return []
    loaded = _yaml().safe_load(f.read_text(encoding="utf-8"))
    rows = loaded if isinstance(loaded, list) else (loaded or {}).get("rows", [])
    out = []
    for r in rows[:максимум]:
        if not isinstance(r, dict):
            continue
        ключ = _row_key(table, r)
        текст = next((str(r[f.name])[:120] for f in table.fields
                      if f.kind == "текст" and not (f.name or "").lower().startswith("код")
                      and r.get(f.name)), "")
        out.append({"ключ": ключ, "формулировка": текст})
    return out


def _raw_sources(workspace: Path) -> list:
    """Все узлы-источники «Источники/» РЕКУРСИВНО (навыки кладут в подпапки Документы/, База данных/…).
    Относительный путь — чтобы агент видел канал/подпапку (полнота входа, методика р.3)."""
    d = paths.sources_dir(workspace)
    if not d.is_dir():
        return []
    return sorted(str(p.relative_to(d)) for p in d.rglob("*.md")
                  if p.is_file() and not any(part.startswith(".") for part in p.relative_to(d).parts))


def fill_request(code: str, workspace) -> dict:
    """Задание на извлечение для таблицы: контракт полей + инструкция + входы. Не пишет — только собирает."""
    workspace = Path(workspace)
    schema = load_schema()
    table = _table(code, schema)
    поля = [{"имя": f.name, "вид": f.kind, "обяз": f.required, "словарь": f.enum,
             "цель": f.target, "выводимое": f.derived} for f in table.fields]
    return {
        "таблица": code,
        "название": table.title,
        "тип": table.kind,
        "уровень": table.level,
        "поля": поля,
        "инструкция": _effective_instruction(table, workspace),
        "входы": {
            "сырьё": _raw_sources(workspace),
            "уже_в_памяти": _memory_digest(table, workspace),
            "таблицы_предшественники": _predecessors(table, schema, workspace),
            "базы_знаний": ["методика kb-audit — логика суждения (всегда)",
                            "доменные БЗ — по подключениям проекта (KBP), роль под уровень таблицы"],
        },
        "куда_писать": f"{_MEMORY_DIR}/{code}.yaml",
    }


def _required(f) -> bool:
    return f.required in ("да", True)


def _is_number(v) -> bool:
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).replace(",", "."))
        return True
    except (TypeError, ValueError):
        return False


def _row_key(table: Table, row: dict):
    """Ключ строки для накопления (upsert): поле «код*»/«id», иначе первое поле таблицы."""
    for f in table.fields:
        nm = (f.name or "").lower()
        if nm.startswith("код") or nm == "id":
            return row.get(f.name)
    return row.get(table.fields[0].name) if table.fields else None


def validate_rows(code: str, rows: list) -> list:
    """Проверить строки против контракта таблицы (обяз. поля, словари, числа).

    Existence межтабличных ссылок — НЕ здесь (это аудит замкнутости). Лишние поля — WARN, не ERROR.
    Таблицы типа «представление» выводимы и руками не заполняются (C3, ЗР-0020) — запись отклоняется.
    """
    table = _table(code)
    by_name = {f.name: f for f in table.fields}
    problems: list = []
    if table.kind == "представление" and rows:
        problems.append(Violation(
            where=code, message="таблица типа «представление» выводима и не заполняется руками (C3)"))
        return problems
    for i, row in enumerate(rows):
        w = f"{code}[{i}]"
        if not isinstance(row, dict):
            problems.append(Violation(where=w, message="строка — не словарь"))
            continue
        for f in table.fields:
            val = row.get(f.name)
            empty = val is None or val == ""
            if _required(f) and empty:
                problems.append(Violation(where=w, message=f"нет обязательного поля «{f.name}»"))
            if f.kind == "перечисление" and f.enum and not empty and val not in f.enum:
                problems.append(Violation(where=w, message=f"«{f.name}»: «{val}» не из словаря"))
            if f.kind == "число" and not empty and not _is_number(val):
                problems.append(Violation(where=w, message=f"«{f.name}»: «{val}» не число"))
        for k in row:
            if k not in by_name and k != _HISTORY and k != _CLEAR_KEY:
                problems.append(Violation(where=w, message=f"поле «{k}» вне контракта", severity="WARN"))
    return problems


_HISTORY = "история"     # служебный подсписок строки: прежние снимки (накопление, методика р.3)
_CLEAR_KEY = "очистить"   # служебный ключ патча: список полей для явного обнуления (p.3 реестра решений)
_SOURCE_FIELDS = ("источник", "Источник", "Источник (сквозное)", "источник заявления",
                  "подтверждающие источники", "источники расхождения")   # аккумулируются списком (гейт Ф1; «сквозное» — прогон встреч Ф3)


def _merge_row(old: dict, new: dict) -> dict:
    """Слияние при совпадении ключа (Р-3, ЗР-0020): непустые поля новой строки поверх старой,
    ничего не обнуляется по умолчанию; источники аккумулируются списком; прежний снимок — в «историю».

    Явное обнуление — служебный ключ «очистить» (список имён полей): применяется ДО обычного
    слияния, поэтому если в том же патче для того же поля пришло и «очистить», и новое значение —
    побеждает новое значение (обычный цикл ниже перезапишет сброс)."""
    merged = dict(old)
    history = list(merged.pop(_HISTORY, []) or [])
    snapshot = {k: v for k, v in old.items() if k != _HISTORY}
    changed = False
    for field in new.get(_CLEAR_KEY, []) or []:
        if merged.get(field) not in (None, ""):
            merged[field] = ""
            changed = True
    for k, v in new.items():
        if k == _HISTORY or k == _CLEAR_KEY or v is None or v == "":
            continue                      # пустое не затирает заполненное
        if k in _SOURCE_FIELDS and merged.get(k) not in (None, "", v):
            acc = merged[k] if isinstance(merged[k], list) else [merged[k]]
            if v not in acc:
                acc = acc + (v if isinstance(v, list) else [v])
            merged[k] = acc
            changed = True
        elif merged.get(k) != v:
            merged[k] = v
            changed = True
    if changed:
        history.append(snapshot)
    if history:
        merged[_HISTORY] = history
    return merged


def write_rows(code: str, rows: list, workspace) -> list:
    """Принять строки: валидация против контракта + запись в <проект>/memory/<код>.yaml.

    Накопление (методика р.3, Р-3 ЗР-0020): строка с существующим ключом СЛИВАЕТСЯ с прежней
    (непустое поверх, источники — списком, прежний снимок — в «историю»), не перезаписывается.
    При наличии ERROR-нарушений не пишет ничего. Возвращает список нарушений
    (может содержать только WARN — тогда запись выполнена).
    """
    table = _table(code)
    mem_dir = Path(workspace) / _MEMORY_DIR
    f = mem_dir / f"{code}.yaml"

    existing: list = []
    if f.is_file():
        loaded = _yaml().safe_load(f.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            existing = loaded
        elif isinstance(loaded, dict) and isinstance(loaded.get("rows"), list):
            existing = loaded["rows"]

    merged: list = list(existing)
    index = {}
    for pos, r in enumerate(merged):
        if isinstance(r, dict):
            k = _row_key(table, r)
            if k is not None:
                index[k] = pos
    candidates: list = []   # финальные строки — их и валидируем (дельта-patch легитимен, р.3)
    for r in rows:
        k = _row_key(table, r)
        if k is not None and k in index:
            merged[index[k]] = _merge_row(merged[index[k]], r)
            candidates.append(merged[index[k]])
        else:
            r = {k2: v2 for k2, v2 in r.items() if k2 != _CLEAR_KEY}   # новой строке нечего чистить
            merged.append(r)
            candidates.append(r)
            if k is not None:
                index[k] = len(merged) - 1

    problems = validate_rows(code, candidates)
    if any(getattr(p, "severity", "ERROR") == "ERROR" for p in problems):
        return problems

    mem_dir.mkdir(parents=True, exist_ok=True)
    f.write_text(_yaml().safe_dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return problems
