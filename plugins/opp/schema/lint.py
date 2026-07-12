"""Линтер контракта таблиц фактов: ERROR-проверки, что схема — корректный контракт.

Проверяет САМ контракт (schema/fact-tables.yaml), НЕ данные проекта (память) и НЕ план:
- обязательные секции таблицы (название · группа · тип · поля · стык);
- тип ∈ {первичная, представление, связка}; вид поля ∈ известных; перечисление со словарём;
  ссылка с целью; цели рёбер/ссылок резолвятся (код таблицы | * | <по-уровню> | @внешн);
- ребро ссылается на существующее поле; стык заполнен (даёт/потребляет/зависит_от/где);
- СЕМАНТИКА цели (аудит 03.07): уровень целевой таблицы = уровень в смысле ребра «Ур.N»;
  поле-ссылка (не выводимое) не указывает на таблицу-представление; у не-ссылки нет «цель».

Замкнутость ЗАПОЛНЕННОЙ памяти — отдельный контролёр (cap-t-closure), здесь не дублируется.
Нарушения — общий тип `linter.Violation` (переиспользуем). Прогон встроен в `./opp verify` шагом.
"""

from __future__ import annotations

import re

from linter.violation import Violation
from .model import load_schema, targets_of, ANY, BY_LEVEL, SCHEMA_YAML

_ВИДЫ = {"текст", "число", "дата", "перечисление", "ссылка", "ссылки"}
_ТИПЫ = {"первичная", "представление", "связка"}
_СТЫК = ("даёт", "потребляет", "зависит_от", "где")


def lint_schema(schema=None) -> list:
    """ERROR-проверки контракта. Пустой список — контракт валиден."""
    try:
        schema = schema if schema is not None else load_schema()
    except Exception as exc:  # noqa: BLE001
        return [Violation(where="schema/fact-tables.yaml", message=f"схема не читается: {exc}")]

    problems: list = []
    codes = set(schema.tables)
    допустимо = codes | {ANY, BY_LEVEL}

    def цель_ок(t) -> bool:
        if isinstance(t, list):
            return all(цель_ок(x) for x in t)
        if not isinstance(t, str):
            return False
        return t.startswith("@") or t in допустимо

    for code, tab in schema.tables.items():
        w = f"#{code}"
        for имя, знач in (("название", tab.title), ("группа", tab.group),
                          ("тип", tab.kind), ("поля", tab.fields), ("стык", tab.seam)):
            if not знач:
                problems.append(Violation(where=w, message=f"пустая секция «{имя}»"))
        if tab.kind and tab.kind not in _ТИПЫ:
            problems.append(Violation(where=w, message=f"неизвестный тип «{tab.kind}»"))

        имена = set()
        for f in tab.fields:
            fw = f"{w}.{f.name or '?'}"
            if not f.name:
                problems.append(Violation(where=w, message="поле без имени"))
            имена.add(f.name)
            if f.kind and f.kind not in _ВИДЫ:
                problems.append(Violation(where=fw, message=f"неизвестный вид «{f.kind}»"))
            if f.kind == "перечисление" and not f.enum:
                problems.append(Violation(where=fw, message="перечисление без словаря"))
            # цель обязательна у прямой ссылки; выводимое обратное поле (источник описан) — не требует
            if f.kind in ("ссылка", "ссылки") and not f.derived and f.target is None:
                problems.append(Violation(where=fw, message="ссылка без поля «цель»"))
            for t in targets_of(f.target):
                if not цель_ок(t):
                    problems.append(Violation(where=fw, message=f"цель вне набора таблиц: {t}"))

        # рёбра проверяем на резолв цели; «поле» может описывать и входящее/обратное ребро (не поле этой
        # таблицы) — поэтому существование поля здесь не требуем (структура полей — выше).
        for e in tab.edges:
            ew = f"{w}.ребро→{e.target}"
            if not цель_ок(e.target):
                problems.append(Violation(where=ew, message=f"цель ребра вне набора таблиц: {e.target}"))

        seam = tab.seam or {}
        for k in _СТЫК:
            if not seam.get(k):
                problems.append(Violation(where=w, message=f"стык: пустое «{k}»"))

    problems.extend(_c8_problems(schema))
    problems.extend(_semantic_target_problems(schema))
    problems.extend(_required_derived_problems(schema))
    problems.extend(_edge_field_problems(schema))
    problems.extend(_pipeline_problems(schema))
    problems.extend(_significance_problems(schema))
    return problems


# Флаг «значимость: полнота» (ЗР-0027, спека 08 §2): пустота такого поля у существующей строки —
# дыра картины каркаса (builder asis-levels), не ошибка целостности (C5: пустое поле — тоже фактура).
_ЗНАЧИМОСТЬ = {"полнота"}


def _significance_problems(schema) -> list:
    """Значение атрибута «значимость» (если задан) ∈ словаря допустимых — иное является замечанием
    (опечатка/незнакомое значение в контракте, не в данных проекта)."""
    problems = []
    for code, tab in schema.tables.items():
        for f in tab.fields:
            зн = f.significance
            if зн is None:
                continue
            if зн not in _ЗНАЧИМОСТЬ:
                problems.append(Violation(where=f"#{code}.{f.name}",
                    message=f"неизвестное значение «значимость: {зн}» (допустимо: {sorted(_ЗНАЧИМОСТЬ)})"))
    return problems


def _required_derived_problems(schema) -> list:
    """Гейт Ф1 (04.07): у первичных/связок поле не может быть «обяз: да» И «выводимое: да»
    одновременно — агента заставляют вводить то, что объявлено вычисляемым. Представления
    освобождены (вычисляются целиком, ввод в них запрещён)."""
    problems = []
    for code, tab in schema.tables.items():
        if tab.kind == "представление":
            continue
        for f in tab.fields:
            if f.required in ("да", True) and f.derived:
                problems.append(Violation(where=f"#{code}.{f.name}",
                    message="противоречие «обяз: да» + «выводимое: да» у не-представления "
                            "(вводимое ИЛИ вычисляемое — реши; гейт Ф1)"))
    return problems


# Семантическая проверка целей ссылок (аудит 03.07.2026): линтер раньше сверял лишь «цель ∈ таблицы»,
# из-за чего 13 неверных целей (REP/PRC/ORG/SR/SYS/KBP → представление/чужой уровень) прошли зелёными.
_УР = re.compile(r"Ур\.(\d+)")           # «Ур.N» в смысле ребра
_ССЫЛКИ = {"ссылка", "ссылки"}
_СПЕЦ = {ANY, BY_LEVEL}                    # спец-цели — не код таблицы, уровень не сверяем
# AS-IS представления-картины: ссылаться на них полем-ссылкой нельзя (это выводимые проекции; поле
# должно указывать на конкретную каркасную таблицу). TO-BE-представление TLM разрешено (TO-BE-таблицы
# раскладываются в него по паспортам AV/TDM) — его неверное использование ловит проверка уровня.
_BANNED_VIEW_TARGETS = {"asis-levels", "asis-traceability"}


def _semantic_target_problems(schema) -> list:
    """3 проверки семантики целей: уровень цели ↔ «Ур.N» в смысле; ссылка-поле не на представление;
    цель только у ссылок. Пустой список — контракт семантически валиден."""
    problems = []
    tables = schema.tables

    def level_of(code):
        t = tables.get(code)
        return t.level if t else None

    for code, tab in tables.items():
        # (3) поле вида ≠ ссылка не должно нести «цель» (число-дискриминатор полиморфной ссылки и т.п.)
        for f in tab.fields:
            if f.kind not in _ССЫЛКИ and f.target is not None:
                problems.append(Violation(where=f"#{code}.{f.name}",
                    message=f"у поля вида «{f.kind}» задана «цель» — цель только у ссылок"))
            # (2) поле-ссылка (не выводимое) не указывает на AS-IS представление-картину
            if f.kind in _ССЫЛКИ and not f.derived:
                for tgt in targets_of(f.target):
                    if tgt in _BANNED_VIEW_TARGETS:
                        problems.append(Violation(where=f"#{code}.{f.name}",
                            message=f"ссылка-поле указывает на представление «{tgt}» "
                                    f"(выводимая проекция; поле должно вести на конкретную каркасную таблицу)"))

        # (1) уровень целевой таблицы = уровень, названный в смысле ребра «Ур.N»
        for e in tab.edges:
            levels = {int(n) for n in _УР.findall(e.meaning or "")}
            if not levels:
                continue
            for tgt in targets_of(e.target):
                if tgt in _СПЕЦ or str(tgt).startswith("@") or tgt not in tables:
                    continue
                lvl = level_of(tgt)
                if lvl is not None and lvl not in levels:
                    problems.append(Violation(where=f"#{code}.ребро→{tgt}",
                        message=f"уровень цели «{tgt}» (Ур.{lvl}) не совпадает со смыслом ребра "
                                f"(Ур.{'/'.join(map(str, sorted(levels)))})"))
    return problems


def _edge_field_problems(schema) -> list:
    """ЗР-0024 п.5: ребро без развёрнутого поля — фантом. «Поле» ребра либо намеренно
    `null` (рёбра-проекции — сегодня 4: PSK→KBP, PSK→INT, PRB→asis-levels,
    PRB→asis-traceability; список не хардкодим, просто допускаем None), либо резолвится
    в объявленное поле СВОЕЙ таблицы."""
    problems = []
    for code, tab in schema.tables.items():
        имена = {f.name for f in tab.fields}
        for e in tab.edges:
            if e.field is None:
                continue
            if e.field not in имена:
                problems.append(Violation(
                    where=f"#{code}.ребро→{e.target}",
                    message=f'ребро «{code}→{e.target}»: поле «{e.field}» не объявлено в полях таблицы'))
    return problems


# Конвейер заполнения (ЗР-0024 п.4): ранг упорядоченных стадий («сквозные-управляющие» и
# «представления» вне ранга — не ограничены/только цель соответственно).
_РАНГ_СТАДИИ = {"1-разведка": 1, "2-диагноз": 2, "3-осмысление": 3, "4-целевая": 4}

# Точечные допустимые исключения из правила направления (C14): ребро НЕ-выводимого поля стадии
# N целится вперёд по конвейеру или в представление, но нарушение разобрано по смыслу поля и
# признано осознанным (не ослабление правила молча — см. отчёт агента при заведении исключений).
_ДОПУСТИМЫЕ_ИСКЛЮЧЕНИЯ_НАПРАВЛЕНИЯ = {
    # владелец: единственное заранее известное исключение (ЗР-0024 п.4) — раскладка целевой
    # модели данных (TDM, стадия 4-целевая) в итоговое представление TLM.
    ("TDM", "Обеспечивает целевой отчёт", "TLM"),
    # тот же паттерн, что и TDM→TLM (проектная TO-BE-сущность → представление TLM): вариант
    # архитектуры раскладывается по 11 уровням через TLM.
    ("AV", "Целевая модель по уровням", "TLM"),
    # мягкая необязательная трассировка «доработка → требование» (обяз: условно): доработка
    # обнаруживается на разведке раньше, чем существует требование; поле дозаполняется по мере
    # продвижения к синтезу TB, не создаёт зависимости на момент заполнения CR.
    ("CR", "реализуемое требование", "TB"),
    # трассировка происхождения: гипотеза → проблема (поле необязательное), дозаполняется при
    # переходе гипотезы в проблему — на момент заполнения HYP цели ещё нет.
    ("HYP", "стала кандидатом в проблему", "PRB"),
    # аналогично — происхождение открытого вопроса в проблему/гипотезу (поле необязательное).
    ("OQ", "породившая проблема/гипотеза", "PRB"),
}


def _pipeline_problems(schema) -> list:
    """Конвейер заполнения (ЗР-0024 п.4): каждая таблица контракта приписана ровно одной
    стадии верхнеуровневого ключа «конвейер:»; правило направления (политика C14) — не-
    выводимая ссылка стадии N целится только в таблицы стадии ≤N, в «сквозные-управляющие»
    или (точечным исключением) в «представления». Ключ «конвейер» читается из сырого YAML
    напрямую (модель `schema.model.Schema` его не несёт)."""
    import yaml

    try:
        raw = yaml.safe_load(SCHEMA_YAML.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return [Violation(where="schema/fact-tables.yaml", message=f"конвейер не читается: {exc}")]
    pipeline = raw.get("конвейер") or {}

    counts: dict = {}
    code_stage: dict = {}
    for stage, codes in pipeline.items():
        for c in codes or []:
            counts[c] = counts.get(c, 0) + 1
            code_stage.setdefault(c, stage)

    problems: list = []
    for code in schema.tables:
        n = counts.get(code, 0)
        if n == 0:
            problems.append(Violation(where=f"#{code}",
                message="таблица не приписана ни одной стадии конвейера (ЗР-0024 п.4)"))
        elif n > 1:
            problems.append(Violation(where=f"#{code}",
                message=f"таблица приписана {n} стадиям конвейера одновременно (ЗР-0024 п.4)"))
    for code in code_stage:
        if code not in schema.tables:
            problems.append(Violation(where="#конвейер",
                message=f"код «{code}» в конвейере — таблицы с таким кодом нет в контракте"))

    сквозные = set(pipeline.get("сквозные-управляющие") or [])
    представления = set(pipeline.get("представления") or [])

    for code, tab in schema.tables.items():
        стадия = code_stage.get(code)
        if стадия not in _РАНГ_СТАДИИ:
            continue  # сквозные/представления/непрописанная — направление не ограничиваем
        r_src = _РАНГ_СТАДИИ[стадия]
        for f in tab.fields:
            if f.kind not in ("ссылка", "ссылки") or f.derived:
                continue
            for t in targets_of(f.target):
                if not isinstance(t, str) or t in (ANY, BY_LEVEL) or t.startswith("@"):
                    continue
                if t in сквозные or t == code:
                    continue
                if (code, f.name, t) in _ДОПУСТИМЫЕ_ИСКЛЮЧЕНИЯ_НАПРАВЛЕНИЯ:
                    continue
                if t in представления:
                    problems.append(Violation(where=f"#{code}.{f.name}",
                        message=f'конвейер (C14): поле «{f.name}» (стадия «{стадия}») '
                                f'целится в представление «{t}» (не выводимое)'))
                    continue
                t_stage = code_stage.get(t)
                if t_stage not in _РАНГ_СТАДИИ:
                    continue  # цель без ранга (не прописана в конвейере) — уже поймано выше
                if _РАНГ_СТАДИИ[t_stage] > r_src:
                    problems.append(Violation(where=f"#{code}.{f.name}",
                        message=f'конвейер (C14): поле «{f.name}» (стадия «{стадия}») '
                                f'целится вперёд по конвейеру — в «{t}» (стадия «{t_stage}»)'))
    return problems


# C8 (решение владельца 02.07.2026, вариант Б): общая шкала «степени покрытия» едина дословно
# для GAP/TS/COV; FIT ведёт узаконенную 5-значную детализацию с фиксированным маппингом на общую
# (маппинг — в паспорте FIT и spec/fact-tables/c-policies.md). Словари утверждены — контракт, не данные.
_C8_ОБЩАЯ = ["покрыто типовой", "покрыто частично", "покрыто иначе (не подходит)", "не покрыто"]
_C8_FIT = ["полностью типовой", "частично (есть зазор)", "только доработкой",
           "обходным решением", "не закрывается"]


def _c8_problems(schema) -> list:
    """Единство шкалы покрытия типовой (политика C8) между GAP/TS/COV/FIT."""
    def словарь(code):
        tab = schema.tables.get(code)
        for f in (tab.fields if tab else []):
            if "степень покрытия" in (f.name or "").lower():
                return list(f.enum or [])
        return None

    problems = []
    for code in ("GAP", "TS", "COV"):
        e = словарь(code)
        if e is not None and e != _C8_ОБЩАЯ:
            problems.append(Violation(
                where=f"#{code}.степень покрытия",
                message="C8: словарь отличается от общей шкалы покрытия (GAP/TS/COV едины дословно)"))
    e = словарь("FIT")
    if e is not None and e != _C8_FIT:
        problems.append(Violation(
            where="#FIT.степень покрытия",
            message="C8: словарь FIT ≠ узаконенной 5-значной детализации (решение владельца 02.07.2026)"))
    return problems
