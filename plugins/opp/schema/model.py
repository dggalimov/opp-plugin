"""Парсер контракта таблиц фактов (schema/fact-tables.yaml) в модель.

Контракт — единый источник правды (reg-facttables): 39 таблиц, у каждой поля · рёбра · рецепт ·
инструкция · инварианты целостности · стык. Читается «в структуру» через YAML (не разбором текста).
Модель потребляют: линтер схемы (`schema.lint` — ERROR-проверки самого контракта) и, позже,
контролёр памяти/замкнутости (проверка строк проекта против этой схемы — cap-t-closure).
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_YAML = ROOT / "schema" / "fact-tables.yaml"

# Спец-цели рёбер/ссылок (не код таблицы):
ANY = "*"                 # любая таблица (провенанс)
BY_LEVEL = "<по-уровню>"  # полиморфно по полю «уровень» строки
# Префикс «@» — внешняя ссылка (БЗ-реестр/профили/навык), вне набора таблиц фактов.


@dataclass
class Field:
    name: str        # имя
    kind: str        # вид: текст | число | дата | перечисление | ссылка | ссылки
    required: object  # обяз: да | нет | условно
    enum: object     # словарь (list | None)
    target: object   # цель (код таблицы | список | спец-цель | None)
    derived: bool    # выводимое
    raw: dict


@dataclass
class Edge:
    target: object   # к (код таблицы | список | спец-цель)
    field: str       # поле
    cardinality: str  # кардинальность
    meaning: str     # смысл
    raw: dict


@dataclass
class Table:
    code: str
    title: str        # название
    group: str        # группа
    kind: str         # тип: первичная | представление | связка
    level: object     # уровень (1..11 | None)
    coverage: str     # покрытие_методикой
    fields: list      # поля -> [Field]
    edges: list       # рёбра -> [Edge]
    recipe: dict      # рецепт
    instruction: dict  # инструкция
    integrity: list   # целостность
    lifecycle: dict   # жизненный_цикл
    projection: list  # проекция
    seam: dict        # стык (даёт/потребляет/зависит_от/где)
    raw: dict


@dataclass
class Schema:
    version: object
    tables: dict      # code -> Table


def _yaml():
    import yaml
    return yaml


def _field_of(d: dict) -> Field:
    return Field(name=d.get("имя", ""), kind=d.get("вид", ""), required=d.get("обяз"),
                 enum=d.get("словарь"), target=d.get("цель"),
                 derived=bool(d.get("выводимое")), raw=d)


def _edge_of(d: dict) -> Edge:
    return Edge(target=d.get("к"), field=d.get("поле", ""),
                cardinality=d.get("кардинальность", ""), meaning=d.get("смысл", ""), raw=d)


def _table_of(code: str, d: dict) -> Table:
    d = d or {}
    return Table(
        code=code, title=d.get("название", ""), group=d.get("группа", ""),
        kind=d.get("тип", ""), level=d.get("уровень"), coverage=d.get("покрытие_методикой", ""),
        fields=[_field_of(f) for f in (d.get("поля") or []) if isinstance(f, dict)],
        edges=[_edge_of(e) for e in (d.get("рёбра") or []) if isinstance(e, dict)],
        recipe=d.get("рецепт") or {}, instruction=d.get("инструкция") or {},
        integrity=d.get("целостность") or [], lifecycle=d.get("жизненный_цикл") or {},
        projection=d.get("проекция") or [], seam=d.get("стык") or {}, raw=d)


def load_schema(path: Path = SCHEMA_YAML) -> Schema:
    """Прочитать контракт таблиц фактов в модель."""
    data = _yaml().safe_load(Path(path).read_text(encoding="utf-8")) or {}
    tables_raw = data.get("таблицы") or {}
    tables = {code: _table_of(code, blk) for code, blk in tables_raw.items()}
    return Schema(version=data.get("версия"), tables=tables)


def targets_of(value) -> list:
    """Цели ссылки/ребра как список (строка|список → список)."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


# Канонические имена поля-провенанса факта (после унификации Фазой 2 в контракте — одно имя).
# «источник заявления» (TB) сюда не входит: у TB нет обязательного провенанс-поля в смысле
# «факт → источник» (заявитель/заявление, а не факт со статусом доказанности).
PROVENANCE_FIELD_NAMES = {"источник"}


def provenance_field(table: Table) -> object:
    """Точное имя поля-провенанса факта таблицы (или None, если его нет).

    Ищет ТОЧНОЕ совпадение имени поля с каноническим именем провенанса (без подстрочного
    поиска — подстрока «источник» ловит и однофамильцев вроде «источник-эталон» (GAP),
    «система-источник» (INT, цель SYS, не SRC), «расхождение-источник» (PRB, происхождение
    суждения, не факта), объявленных в контракте раньше настоящего поля-провенанса).
    """
    for f in table.fields:
        if (f.name in PROVENANCE_FIELD_NAMES and f.kind in ("ссылка", "ссылки")
                and "SRC" in targets_of(f.target)):
            return f.name
    return None
