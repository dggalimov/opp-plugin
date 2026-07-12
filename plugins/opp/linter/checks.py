"""Содержательные правила проверки памяти проекта — аудит замкнутости (cap-t-closure).

Память проекта (строки таблиц фактов в `<ws>/memory/*.yaml`) сверяется с КОНТРАКТОМ (`schema.model`,
cap-schema): уникальность кодов в таблице и отсутствие висячих межтабличных ссылок (все цепи замкнуты).
Форму самого контракта проверяет `schema.lint`; существование строк, на которые ссылаются, — здесь.

Плюс семантические инварианты методики (аудит 03.07, ЗР-0020) — раньше жили прозой в паспортах:
гейт ОБЭ (р.6) · замкнутость PRB×TB (р.7) · тип решения ↔ уровень (C6) · ацикличность каскада ·
только-чтение представлений (C3) · «цифровой след» ⇒ источник природы «данные системы» (р.4).

Пустая память → нет нарушений (гигиена: `./opp verify` на пустом проекте остаётся зелёным). Реальное
наполнение проверяется по проекту: `./opp lint <проект>`.
"""

from __future__ import annotations
from collections import defaultdict

from .model import Memory
from .violation import Violation


def _as_list(v):
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def _key_field(tab):
    for f in tab.fields:
        nm = (f.name or "").lower()
        if nm.startswith("код") or nm == "id":
            return f.name
    return tab.fields[0].name if tab.fields else None


def check_memory(memory: Memory) -> list:
    """Аудит замкнутости памяти. Пустая память → пусто."""
    if memory.is_empty:
        return []

    from schema.model import load_schema, targets_of, ANY, BY_LEVEL
    schema = load_schema()
    problems: list = []

    by_level = defaultdict(list)
    for code, tab in schema.tables.items():
        if isinstance(tab.level, int):
            by_level[tab.level].append(code)

    # 1) индекс строк по ключу + уникальность кодов в таблице
    index: dict = defaultdict(dict)
    for row in memory.rows:
        tab = schema.tables.get(row.table)
        if tab is None:
            problems.append(Violation(where=row.source_file,
                                      message=f"таблица «{row.table}» вне контракта"))
            continue
        kf = _key_field(tab)
        key = row.data.get(kf) if kf else None
        if key in (None, ""):
            continue
        if key in index[row.table]:
            problems.append(Violation(where=f"{row.table}:{key}", message="дубль кода в таблице"))
        index[row.table][key] = row

    # 2) висячие межтабличные ссылки: значение ссылочного поля должно резолвиться в строку цели
    for row in memory.rows:
        tab = schema.tables.get(row.table)
        if tab is None:
            continue
        # уровень строки — для полиморфных ссылок «<по-уровню>»
        lvl = None
        for f in tab.fields:
            if "уровень" in (f.name or "").lower():
                try:
                    lvl = int(str(row.data.get(f.name)))
                except (TypeError, ValueError):
                    lvl = None
                if lvl is not None:
                    break
        rk = row.data.get(_key_field(tab))
        for f in tab.fields:
            if f.kind not in ("ссылка", "ссылки") or f.target is None:
                continue
            vals = _as_list(row.data.get(f.name))
            if not vals:
                continue
            tables = set()
            for t in targets_of(f.target):
                if not isinstance(t, str):
                    continue
                if t.startswith("@"):
                    continue                      # внешняя цель — не наша зона
                if t == ANY:
                    tables |= set(schema.tables)
                elif t == BY_LEVEL:
                    if lvl is not None:
                        tables |= set(by_level.get(lvl, []))
                    # уровень не задан → цель не резолвится, висячей не считаем
                elif t in schema.tables:
                    tables.add(t)
            if not tables:
                continue                          # внешняя/нерезолвимая цель — пропускаем
            for val in vals:
                if isinstance(val, (dict, list)):
                    continue
                if not any(val in index.get(c, {}) for c in tables):
                    problems.append(Violation(
                        where=f"{row.table}:{rk}",
                        message=f"висячая ссылка «{f.name}»→«{val}» (нет строки в {', '.join(sorted(tables))})"))

    # 3) семантические инварианты методики (ЗР-0020)
    problems.extend(_semantic_invariants(memory, schema, index))
    return problems


# --- семантические инварианты (аудит 03.07, ЗР-0020) -----------------------

# Статусы доказанности «выше гипотезы» — с них действует гейт ОБЭ (методика р.6).
_ВЫШЕ_ГИПОТЕЗЫ = {"цифровой след", "интервью", "согласовано"}
# Тип решения выводится из уровня (методика р.6, C6): диапазон уровней → префикс значения.
_ТИП_ПО_УРОВНЮ = ((range(1, 4), "методологическое"), (range(4, 7), "организационное"),
                  (range(7, 12), "технологическое"))


def _rows_of(memory, code):
    return [r for r in memory.rows if r.table == code]


def _semantic_invariants(memory, schema, index) -> list:
    problems: list = []
    problems += _check_view_readonly(memory, schema)
    problems += _check_gate_obe(memory, index)
    problems += _check_closure_prb_tb(memory)
    problems += _check_type_vs_level(memory)
    problems += _check_acyclic(memory, "PRB", "код проблемы", "корневая проблема",
                               "цикл в дереве причин (производная ссылается на себя по цепи корневых)")
    problems += _check_acyclic(memory, "TB", "код требования", "зависит от требований",
                               "цикл зависимостей требований")
    problems += _check_acyclic(memory, "PRC", "Код узла", "Родитель",
                               "цикл в иерархии процессов (узел — предок самого себя по цепи «Родитель»)")
    problems += _check_digital_trace(memory, schema, index)
    problems += _check_fullness(memory, schema, index)
    return problems


def _check_view_readonly(memory, schema) -> list:
    """C3: представления выводимы — ручных строк в них быть не может."""
    return [Violation(where=row.source_file,
                      message=f"ручная строка в таблице-представлении «{row.table}» "
                              f"(выводимая, только чтение — C3)")
            for row in memory.rows
            if (schema.tables.get(row.table) or type("t", (), {"kind": ""})).kind == "представление"]


def _check_gate_obe(memory, index) -> list:
    """Гейт ОБЭ (р.6): проблема выше гипотезы обязана нести категорию, «в чём» и живую ссылку на EFF."""
    problems = []
    for row in _rows_of(memory, "PRB"):
        код = row.data.get("код проблемы")
        статус = row.data.get("статус доказанности")
        if статус not in _ВЫШЕ_ГИПОТЕЗЫ:
            continue
        if str(row.data.get("нижняя отсечка", "")).startswith("ниже порога"):
            continue  # особенность учёта — не проблема, гейт не применяется
        расчёт = row.data.get("координата 3 — ОБЭ: сколько (ссылка на расчёт)")
        if not (row.data.get("координата 3 — ОБЭ: категория")
                and row.data.get("координата 3 — ОБЭ: в чём ущерб")
                and расчёт and расчёт in index.get("EFF", {})):
            problems.append(Violation(
                where=f"PRB:{код}",
                message=f"гейт ОБЭ: статус «{статус}» без категории/«в чём»/EFF-расчёта — "
                        f"не выше гипотезы (методика р.6)"))
    return problems


_ПОЛЯ_ПОКРЫТИЯ_TB = ("покрывает проблемы (полностью)", "покрывает проблемы (частично)")


def _check_closure_prb_tb(memory) -> list:
    """Замкнутость (р.7): согласованная проблема ↔ требование через поля покрытия TB (ЗР-0024:
    TBPR поглощена полями «покрывает проблемы (полностью)»/«...(частично)»), в обе стороны."""
    problems = []
    покрытые_проблемы = set()
    for row in _rows_of(memory, "TB"):
        треб = row.data.get("код требования")
        полностью = set(_as_list(row.data.get(_ПОЛЯ_ПОКРЫТИЯ_TB[0])))
        частично = set(_as_list(row.data.get(_ПОЛЯ_ПОКРЫТИЯ_TB[1])))
        покрытые_проблемы |= полностью | частично
        for код_прб in полностью & частично:
            problems.append(Violation(
                where=f"TB:{треб}",
                message=f"проблема «{код_прб}» и в полном, и в частичном покрытии требования "
                        f"«{треб}» одновременно"))
    for row in _rows_of(memory, "PRB"):
        if (row.data.get("статус доказанности") == "согласовано"
                and not str(row.data.get("нижняя отсечка", "")).startswith("ниже порога")
                and row.data.get("код проблемы") not in покрытые_проблемы):
            problems.append(Violation(
                where=f"PRB:{row.data.get('код проблемы')}",
                message="согласованная проблема с существенным ОБЭ без требования (нет покрытия TB) — "
                        "разрыв замкнутости (методика р.7)"))
    for row in _rows_of(memory, "TB"):
        if (row.data.get("статус требования") == "согласовано"
                and not _as_list(row.data.get(_ПОЛЯ_ПОКРЫТИЯ_TB[0]))
                and not _as_list(row.data.get(_ПОЛЯ_ПОКРЫТИЯ_TB[1]))):
            problems.append(Violation(
                where=f"TB:{row.data.get('код требования')}",
                message="согласованное требование без трассировки к проблеме (оба поля покрытия пусты) — "
                        "пожелание, а не требование (методика р.7)"))
    return problems


def _check_type_vs_level(memory) -> list:
    """C6: тип решения согласован с уровнем (Ур.1–3 метод. / 4–6 орг. / 7–11 технол.). Сверка, не вывод (ЗР-0020)."""
    problems = []
    for row in _rows_of(memory, "PRB"):
        тип = str(row.data.get("координата 4 — тип решения") or "")
        try:
            lvl = int(str(row.data.get("координата 1 — уровень (номер)")))
        except (TypeError, ValueError):
            continue
        if not тип:
            continue
        ожидание = next((pref for rng, pref in _ТИП_ПО_УРОВНЮ if lvl in rng), None)
        if ожидание and not тип.startswith(ожидание):
            problems.append(Violation(
                where=f"PRB:{row.data.get('код проблемы')}",
                message=f"тип решения «{тип}» не согласован с уровнем {lvl} "
                        f"(Ур.1–3→метод./4–6→орг./7–11→технол., C6)"))
    return problems


def _check_acyclic(memory, code, key_field, ref_field, msg) -> list:
    """Ацикличность рефлексивной цепочки (каскад PRB, зависимости TB)."""
    graph = {}
    for row in _rows_of(memory, code):
        k = row.data.get(key_field)
        if k:
            graph[k] = [v for v in _as_list(row.data.get(ref_field)) if v]
    problems, чист = [], set()
    for start in graph:
        путь, узел = set(), start
        while узел in graph and узел not in чист:
            if узел in путь:
                problems.append(Violation(where=f"{code}:{start}", message=msg))
                break
            путь.add(узел)
            узел = graph[узел][0] if graph[узел] else None
        чист |= путь
    return problems


def _check_digital_trace(memory, schema, index) -> list:
    """Р.4: статус «цифровой след» ⇒ источник природы «данные системы» (строго этот статус, ЗР-0020)."""
    from schema.model import provenance_field
    problems = []
    for row in memory.rows:
        tab = schema.tables.get(row.table)
        if tab is None or row.data.get("статус доказанности") != "цифровой след":
            continue
        поле_источника = provenance_field(tab)
        if not поле_источника:
            continue
        # после слияния (Р-3) источник может быть списком: достаточно одного «данные системы»
        природы = []
        for val in _as_list(row.data.get(поле_источника)):
            src = index.get("SRC", {}).get(val) if not isinstance(val, (dict, list)) else None
            природы.append(src.data.get("природа доказательства") if src else None)
        if "данные системы" not in природы:
            problems.append(Violation(
                where=f"{row.table}:{row.data.get(_key_field(tab))}",
                message=f"статус «цифровой след» при источнике природы "
                        f"«{', '.join(str(п or '—') for п in природы) or '—'}» — "
                        f"данные системы сильнее слов (методика р.4)"))
    return problems


def _check_fullness(memory, schema, index) -> list:
    """Контроль полноты извлечения (спека 08 §4): опись сущностей MAT ↔ факт извлечённых строк.

    Трёхтактный протокол материалов: опись (до извлечения) → извлечение → счётная сверка.
    Здесь — механическая сверка (такт 3): опись меньше извлечённого — не сигнал (дозаполнение
    другими каналами законно); опись больше извлечённого — WARN «недоизвлечено» (выборочный
    разбор законен, но должен быть виден, не ERROR)."""
    from schema.model import provenance_field
    import yaml
    problems = []
    mat_tab = schema.tables.get("MAT")
    if mat_tab is None:
        return problems
    mat_key = _key_field(mat_tab)
    for row in _rows_of(memory, "MAT"):
        код_мат = row.data.get(mat_key)
        опись_текст = row.data.get("опись сущностей")
        if опись_текст in (None, ""):
            continue  # опись не заявлена — сверять нечего (не брак самой строки MAT)
        try:
            опись = yaml.safe_load(опись_текст)
        except yaml.YAMLError:
            опись = None
        if not isinstance(опись, dict):
            problems.append(Violation(
                where=f"MAT:{код_мат}",
                message=f"опись сущностей не читается как YAML-словарь (MAT-{код_мат})",
                severity="WARN"))
            continue
        src_vals = _as_list(row.data.get("ссылка на источник"))
        код_источника = src_vals[0] if src_vals else None
        for код_таблицы, заявлено in опись.items():
            код_таблицы = str(код_таблицы)
            целевая = schema.tables.get(код_таблицы)
            if целевая is None:
                problems.append(Violation(
                    where=f"MAT:{код_мат}",
                    message=f"опись ссылается на несуществующую таблицу «{код_таблицы}» (MAT-{код_мат})",
                    severity="WARN"))
                continue
            try:
                заявлено_число = int(заявлено)
            except (TypeError, ValueError):
                continue
            поле_источника = provenance_field(целевая)
            извлечено = 0
            if поле_источника and код_источника:
                for r in _rows_of(memory, код_таблицы):
                    if код_источника in _as_list(r.data.get(поле_источника)):
                        извлечено += 1
            if извлечено < заявлено_число:
                problems.append(Violation(
                    where=f"MAT:{код_мат}",
                    message=f"недоизвлечено: {код_таблицы} {извлечено} из {заявлено_число} "
                            f"({код_источника})",
                    severity="WARN"))
    return problems
