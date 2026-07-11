"""cap-t-triangulate — движок «сверить» T-конвейера осмысления (вход синтеза).

Перекрёстная сверка наполненных таблиц фактов по уровням каркаса (методика р.5) → задание для суждения
навыка `skill-synthesis` + детерминированные белые пятна. Это РЕЛЬСЫ, не суждение: какие факты реально
расходятся по смыслу и проблема ли это — решает навык. Кандидаты (гипотезы-расхождения → таблица HYP,
открытые вопросы → OQ) навык пишет через `cap-t-extract.write_rows` — здесь запись НЕ дублируем.

Переиспользует: `schema.model` (контракт: уровни, рёбра), `linter.model.load_memory` (строки проекта,
устойчиво к отсутствию), `reference/framework.yaml` (перекрёстные сверки уровней — проза-ориентир).
"""

from __future__ import annotations
from collections import defaultdict
from pathlib import Path

from schema.model import load_schema, targets_of, provenance_field
from linter.model import load_memory

ROOT = Path(__file__).resolve().parent.parent
_HYP = "HYP"   # гипотезы-расхождения
_OQ = "OQ"     # открытые вопросы (нужен ответ заказчика)


def _framework_checks() -> dict:
    """перекрёстные_сверки по номеру уровня из reference/framework.yaml (ориентир для навыка)."""
    try:
        import yaml
        data = yaml.safe_load((ROOT / "reference" / "framework.yaml").read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}
    return {lv.get("номер"): lv.get("перекрёстные_сверки", "") for lv in data.get("уровни", [])}


def _rows_by_table(workspace) -> dict:
    mem = load_memory(Path(workspace))
    out = defaultdict(list)
    for r in mem.rows:
        out[r.table].append(r.data)
    return out


def _level_tables(schema) -> dict:
    """Первичные каркасные таблицы по номеру уровня (представления/связки не входят)."""
    by_level = defaultdict(list)
    for code, tab in schema.tables.items():
        if isinstance(tab.level, int) and tab.kind == "первичная":
            by_level[tab.level].append((code, tab))
    return by_level


def find_gaps(workspace) -> list:
    """Детерминированные белые пятна: уровень без фактов при НАЧАТОЙ разведке (методика — гейт готовности)."""
    schema = load_schema()
    rows = _rows_by_table(workspace)
    by_level = _level_tables(schema)
    started = any(rows.get(c) for codes in by_level.values() for c, _ in codes)
    if not started:
        return []                       # разведка не начата — пробелов не считаем
    gaps = []
    for lvl in sorted(by_level):
        codes = [c for c, _ in by_level[lvl]]
        if all(not rows.get(c) for c in codes):
            gaps.append({"вид": "белое пятно", "уровень": lvl, "таблицы": codes,
                         "описание": f"Уровень {lvl} не покрыт разведкой (нет фактов) — кандидат в открытый вопрос."})
    return gaps


def _source_counts(rows: list, sf) -> dict:
    counts: dict = defaultdict(int)
    if not sf:
        return {}
    for r in rows:
        v = r.get(sf)
        for s in (v if isinstance(v, list) else [v]):
            if s:
                counts[str(s)] += 1
    return dict(counts)


def triangulate_request(workspace) -> dict:
    """Задание на триангуляцию для навыка skill-synthesis: по каждому уровню — картина сверки.

    Собирает: строки уровня по источникам (материал для «источник × источник»), рёбра на другие уровни
    (структурная плоскость «уровень × уровень»), прозаические сверки каркаса (ориентир). Не судит.
    """
    schema = load_schema()
    rows = _rows_by_table(workspace)
    checks = _framework_checks()
    by_level = _level_tables(schema)

    по_уровням = []
    for lvl in sorted(by_level):
        таблицы = []
        for code, tab in by_level[lvl]:
            trows = rows.get(code, [])
            sf = provenance_field(tab)
            src_count = _source_counts(trows, sf)
            cross = []
            for e in tab.edges:
                for t in targets_of(e.target):
                    tt = schema.tables.get(t) if isinstance(t, str) else None
                    if tt is not None and isinstance(tt.level, int) and tt.level != lvl:
                        cross.append({"на_таблицу": t, "уровень": tt.level, "через_поле": e.field})
            таблицы.append({
                "таблица": code, "название": tab.title, "строк": len(trows),
                "по_источникам": src_count,
                "несколько_источников_на_уровне": len(src_count) > 1,
                "рёбра_на_другие_уровни": cross,
            })
        по_уровням.append({"уровень": lvl, "таблицы": таблицы, "сверки_каркаса": checks.get(lvl, "")})

    return {
        "этап": "1.8 — перекрёстная сверка (триангуляция)",
        "плоскости_сверки": [
            "источник × источник (один уровень): документ vs данные vs слова",
            "уровень × уровень (вертикаль каркаса): по рёбрам и сверкам каркаса",
            "заявленное × фактическое × эталонное (норма / журнал / типовая функция БЗ)",
        ],
        "по_уровням": по_уровням,
        "детерминированные_пробелы": find_gaps(workspace),
        "куда_писать_кандидатов": {
            "расхождения_гипотезы": _HYP,
            "открытые_вопросы": _OQ,
            "запись": "через cap-t-extract.write_rows(код, строки, проект) — не дублируем",
        },
        "правило": "расхождение = кандидат в гипотезу/открытый вопрос (методика р.5); "
                   "проблема (доказанный ОБЭ) — уже cap-t-prove",
    }
