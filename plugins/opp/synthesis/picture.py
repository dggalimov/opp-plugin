"""cap-t-picture — движок «Картина каркаса» итеративного ядра (спека 08 §1, ЗР-0027 п.1).

Детерминированный расчёт готовности разведки по 11 уровням каркаса: сколько фактов собрано,
пройден ли ведущий канал уровня, есть ли база для перекрёстной сверки, где дыры полноты (три
вида — пустой уровень / пустое значимое поле / непройденный ведущий канал), какие вопросы висят
на уровне и какой у него статус готовности («не начат → в разведке → готов к синтезу →
синтезирован»). Это РЕЛЬСЫ: builder не судит семантику расхождений (эта работа — навыка
synthesis через triangulate), только механически честный минимум по контракту.

Переиспользует: `synthesis.triangulate._rows_by_table`/`_level_tables` (строки проекта по
таблицам/уровням), `schema.model` (контракт), `reference.framework.load_framework` (акцент
источника уровня — не выдумываем словарь заново), `schema.extract.write_rows` (запись OQ).
"""

from __future__ import annotations
import re
from datetime import date
from pathlib import Path

from schema.model import load_schema, targets_of, provenance_field
from schema.extract import write_rows
from linter.model import load_memory
from reference.framework import load_framework
from synthesis.triangulate import _rows_by_table, _level_tables

_OQ_OPEN = ("открыт", "в работе")
_HYP_OPEN = ("открыта", "перепроверяется")
_ПРОИСХОЖДЕНИЕ_ПЯТНО = "белое пятно (пробел данных)"   # OQ.происхождение (спека 08 §1/§5)
_КРИТИЧНОСТЬ_ДЕФОЛТ = "важный"                          # автогенерация не решает за владельца, что «стоп»

# маркеры дедупа/распознавания собственных формулировок (см. _existing_open_index)
_МАРКЕР_БЕЗ_СТРОК = "не содержит ни одной собранной строки"
_МАРКЕР_КАНАЛ = "не пройден ведущий канал"
_ПОЛЕ_RE = re.compile(r"поля «([^»]+)»")   # родительный падеж («не содержит значения поля «X»»)


# ---------------------------------------------------------------------------
# служебные резолверы (упрощённый паттерн capabilities/render/engine.py::_make_resolver)
# ---------------------------------------------------------------------------

def _row_code(table, row: dict):
    """Ключ строки: поле «код*»/«id», иначе первое поле таблицы (тот же приём, что cap-t-extract)."""
    for f in table.fields:
        nm = (f.name or "").lower()
        if nm.startswith("код") or nm == "id":
            return row.get(f.name)
    return row.get(table.fields[0].name) if table.fields else None


def _row_label(table, row: dict) -> str:
    """Человеческое имя строки: первое непустое текстовое поле, не «код*» — без кодов памяти."""
    for f in table.fields:
        if (f.kind == "текст" and not (f.name or "").lower().startswith("код")
                and row.get(f.name)):
            return str(row[f.name])
    code = _row_code(table, row)
    return str(code) if code is not None else "?"


def _is_empty(v) -> bool:
    return v is None or v == "" or v == []


def _level_num(value) -> object:
    """«5 Процессы» → 5; PRB несёт число напрямую. Не резолвится — None."""
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip().split(" ", 1)[0])
    except ValueError:
        return None


def _level_enum_map(schema) -> dict:
    """Номер уровня → точная строка словаря OQ.«уровень каркаса» (пишем строго по контракту)."""
    field = next((f for f in schema.tables["OQ"].fields if f.name == "уровень каркаса"), None)
    out = {}
    for item in (field.enum if field else []) or []:
        n = _level_num(item)
        if n is not None:
            out[n] = item
    return out


def _channel_types(schema) -> set:
    field = next((f for f in schema.tables["SRC"].fields if f.name == "тип канала"), None)
    return set((field.enum if field else []) or [])


# ---------------------------------------------------------------------------
# картина
# ---------------------------------------------------------------------------

def build_picture(workspace) -> dict:
    """Собрать картину по 11 уровням каркаса. Показатели — ровно по таблице спеки 08 §1."""
    workspace = Path(workspace)
    schema = load_schema()
    rows = _rows_by_table(workspace)
    by_level = _level_tables(schema)
    fw = load_framework()
    fw_by_level = {lv["номер"]: lv for lv in fw.get("уровни", [])}
    known_channels = _channel_types(schema)

    src_by_code = {r.get("код источника"): r for r in rows.get("SRC", []) if isinstance(r, dict)}

    oq_rows = [r for r in rows.get("OQ", []) if isinstance(r, dict)]
    hyp_rows = [r for r in rows.get("HYP", []) if isinstance(r, dict)]
    prb_rows = [r for r in rows.get("PRB", []) if isinstance(r, dict)]

    уровни = []
    for lvl in range(1, 12):
        fw_lvl = fw_by_level.get(lvl, {})
        название = fw_lvl.get("название", f"Уровень {lvl}")
        полоса = fw_lvl.get("полоса", "")
        codes_tabs = by_level.get(lvl, [])

        по_таблицам = {}
        source_codes_seen: set = set()
        for code, tab in codes_tabs:
            trows = rows.get(code, [])
            по_таблицам[code] = len(trows)
            sf = provenance_field(tab)
            if not sf:
                continue
            for r in trows:
                v = r.get(sf)
                for one in (v if isinstance(v, list) else [v]):
                    if one:
                        source_codes_seen.add(str(one))
        собрано = sum(по_таблицам.values())

        актуальные_каналы = set()
        for sc in source_codes_seen:
            src = src_by_code.get(sc)
            if src:
                тип = src.get("тип канала")
                if тип:
                    актуальные_каналы.add(тип)

        ожидаемые = list(fw_lvl.get("акцент_источника") or [])
        if not set(ожидаемые) <= known_channels:
            ведущий_статус = "не определён"
        elif not актуальные_каналы:
            ведущий_статус = "нет"
        elif set(ожидаемые) <= актуальные_каналы:
            ведущий_статус = "да"
        elif set(ожидаемые) & актуальные_каналы:
            ведущий_статус = "частично"
        else:
            ведущий_статус = "нет"

        # перекрёстные сверки: честный минимум (есть ли база — строки на обеих сторонах ребра);
        # «расхождение» — только если уже есть открытый OQ с происхождением «нестыковка уровней»
        cross_edges = []
        for code, tab in codes_tabs:
            for e in tab.edges:
                for t in targets_of(e.target):
                    tt = schema.tables.get(t) if isinstance(t, str) else None
                    if tt is not None and isinstance(tt.level, int) and tt.level != lvl:
                        cross_edges.append(t)
        if not cross_edges:
            сверки = "не проверена"
        else:
            есть_база = any(len(rows.get(t, [])) > 0 for t in cross_edges) and собрано > 0
            есть_расхождение = any(
                _level_num(oq.get("уровень каркаса")) == lvl
                and oq.get("происхождение") == "нестыковка уровней"
                and oq.get("статус закрытия") in _OQ_OPEN
                for oq in oq_rows
            )
            if not есть_база:
                сверки = "не проверена"
            elif есть_расхождение:
                сверки = "расхождение"
            else:
                сверки = "замкнута"

        # дыры полноты (спека 08 §1: а/б/в)
        дыры = []
        if собрано == 0:
            дыры.append({
                "вид": "уровень без строк", "уровень": lvl,
                "описание": f'Уровень {lvl} «{название}» не содержит ни одной собранной строки '
                            f'— раздел обследования не начат.',
            })
        for code, tab in codes_tabs:
            значимые = [f for f in tab.fields if f.significance == "полнота"]
            if not значимые:
                continue
            for row in rows.get(code, []):
                label = _row_label(tab, row)
                for f in значимые:
                    if _is_empty(row.get(f.name)):
                        дыры.append({
                            "вид": "пустое значимое поле", "уровень": lvl,
                            "таблица": code, "строка": _row_code(tab, row), "поле": f.name,
                            "описание": f'Строка «{label}» ({tab.title}) на уровне {lvl} «{название}» '
                                        f'не содержит значения поля «{f.name}».',
                        })
        if собрано > 0 and ведущий_статус != "да":
            дыры.append({
                "вид": "ведущий канал не пройден", "уровень": lvl,
                "описание": f'На уровне {lvl} «{название}» не пройден ведущий канал '
                            f'({", ".join(ожидаемые)}) — часть фактов не подтверждена '
                            f'ожидаемым источником (фактически: {", ".join(sorted(актуальные_каналы)) or "—"}).',
            })

        oq_level = [r for r in oq_rows
                    if _level_num(r.get("уровень каркаса")) == lvl and r.get("статус закрытия") in _OQ_OPEN]
        hyp_level = [r for r in hyp_rows
                     if _level_num(r.get("уровень")) == lvl and r.get("статус проверки") in _HYP_OPEN]
        критичные = [r for r in oq_level if r.get("критичность") == "критичный (стоп перед синтезом)"]

        prb_level = [r for r in prb_rows if _level_num(r.get("координата 1 — уровень (номер)")) == lvl]

        блокирующие_дыры = [d for d in дыры if d["вид"] != "уровень без строк"]  # (а) уже покрыт «не начат»
        if собрано == 0:
            статус = "не начат"
        elif prb_level:
            статус = "синтезирован"
        elif not блокирующие_дыры and ведущий_статус == "да" and not критичные:
            статус = "готов к синтезу"
        else:
            статус = "в разведке"

        уровни.append({
            "уровень": lvl, "название": название, "полоса": полоса,
            "собрано": {"всего": собрано, "по_таблицам": по_таблицам},
            "каналы": {"ожидаемые": ожидаемые, "фактические": sorted(актуальные_каналы),
                      "ведущий_пройден": ведущий_статус},
            "перекрёстные_сверки": сверки,
            "дыры": дыры,
            "вопросы": {"OQ": [r.get("код вопроса") for r in oq_level],
                       "HYP": [r.get("код гипотезы") for r in hyp_level],
                       "критичных": len(критичные)},
            "доказанные_проблемы": [r.get("код проблемы") for r in prb_level],
            "статус_готовности": статус,
        })

    return {
        "этап": "картина каркаса (спека 08 §1)",
        "уровни": уровни,
        "счётчики": {
            "уровней": len(уровни),
            "не начат": sum(1 for л in уровни if л["статус_готовности"] == "не начат"),
            "в разведке": sum(1 for л in уровни if л["статус_готовности"] == "в разведке"),
            "готов к синтезу": sum(1 for л in уровни if л["статус_готовности"] == "готов к синтезу"),
            "синтезирован": sum(1 for л in уровни if л["статус_готовности"] == "синтезирован"),
            "дыр всего": sum(len(л["дыры"]) for л in уровни),
        },
    }


# ---------------------------------------------------------------------------
# сводка (клиентски чистая — без кодов памяти)
# ---------------------------------------------------------------------------

def fmt_picture(data: dict) -> str:
    lines = ["# Картина обследования по уровням", ""]
    lines.append("| Ур. | Уровень | Полоса | Собрано | Ведущий канал | Сверки | Готовность |")
    lines.append("|---|---|---|---|---|---|---|")
    for л in data["уровни"]:
        lines.append(
            f'| {л["уровень"]} | {л["название"]} | {л["полоса"]} | {л["собрано"]["всего"]} | '
            f'{л["каналы"]["ведущий_пройден"]} | {л["перекрёстные_сверки"]} | {л["статус_готовности"]} |'
        )
    lines.append("")

    счётчики = data["счётчики"]
    lines.append(f'Уровней: {счётчики["уровней"]} · не начат: {счётчики["не начат"]} · '
                 f'в разведке: {счётчики["в разведке"]} · готов к синтезу: {счётчики["готов к синтезу"]} · '
                 f'синтезирован: {счётчики["синтезирован"]}')
    lines.append("")

    lines.append("## Дыры полноты")
    lines.append("")
    есть_дыры = False
    for л in data["уровни"]:
        if not л["дыры"]:
            continue
        есть_дыры = True
        lines.append(f'### Уровень {л["уровень"]} — {л["название"]}')
        for d in л["дыры"]:
            lines.append(f'- {d["описание"]}')
        lines.append("")
    if not есть_дыры:
        lines.append("Дыр не обнаружено.")
        lines.append("")

    return "\n".join(lines)


def write_picture(workspace) -> Path:
    """Пересобрать канон картины: <workspace>/Проектная память/Рабочие/картина.md.

    Детерминированно: одинаковая память → байт-в-байт тот же файл.
    """
    workspace = Path(workspace)
    data = build_picture(workspace)
    text = fmt_picture(data)
    out_dir = workspace / "Проектная память" / "Рабочие"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "картина.md"
    out_path.write_text(text, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# заведение открытых вопросов из дыр (--вопросы)
# ---------------------------------------------------------------------------

def _existing_open_index(oq_rows: list) -> tuple[set, set, set]:
    """Разобрать уже заведённые ОТКРЫТЫЕ OQ на «предметы» для дедупа автогенерации.

    Возвращает (уровни_без_строк, уровни_с_непройденным_каналом, {(уровень, строка, поле)}) —
    узнаём собственные прежние формулировки по стабильным маркерам-подстрокам (детерминированные
    шаблоны ниже пишутся только этой функцией, коллизии с чужим текстом маловероятны и не критичны:
    дедуп консервативен — в худшем случае пропустит лишний вопрос, не потеряет реальный).
    """
    без_строк: set = set()
    канал: set = set()
    поле: set = set()
    for r in oq_rows:
        if r.get("статус закрытия") not in _OQ_OPEN:
            continue
        lvl = _level_num(r.get("уровень каркаса"))
        if lvl is None:
            continue
        текст = str(r.get("формулировка") or "")
        строка_каркаса = r.get("строка каркаса") or []
        if not isinstance(строка_каркаса, list):
            строка_каркаса = [строка_каркаса]
        if строка_каркаса:
            m = _ПОЛЕ_RE.search(текст)
            имя_поля = m.group(1) if m else None
            for rc in строка_каркаса:
                поле.add((lvl, rc, имя_поля))
        elif _МАРКЕР_БЕЗ_СТРОК in текст:
            без_строк.add(lvl)
        elif _МАРКЕР_КАНАЛ in текст:
            канал.add(lvl)
    return без_строк, канал, поле


def _next_code(taken: set) -> str:
    width = 2
    max_n = 0
    for c in taken:
        m = re.match(r"^OQ-(\d+)$", str(c))
        if m:
            digits = m.group(1)
            width = max(width, len(digits))
            max_n = max(max_n, int(digits))
    n = max_n + 1
    code = f"OQ-{n:0{width}d}"
    while code in taken:
        n += 1
        code = f"OQ-{n:0{width}d}"
    return code


def generate_questions(workspace, data: dict | None = None) -> dict:
    """Завести OQ из дыр картины (белое пятно). Дедуп по уровню+предмету. Возвращает отчёт."""
    workspace = Path(workspace)
    if data is None:
        data = build_picture(workspace)
    schema = load_schema()
    level_enum = _level_enum_map(schema)

    memory = load_memory(workspace)
    oq_rows = [r.data for r in memory.rows if r.table == "OQ"]
    taken_codes = {r.get("код вопроса") for r in oq_rows if r.get("код вопроса")}
    без_строк_idx, канал_idx, поле_idx = _existing_open_index(oq_rows)

    today = date.today().isoformat()
    candidates: list = []
    пропущено = 0

    for л in data["уровни"]:
        lvl = л["уровень"]
        for d in л["дыры"]:
            вид = d["вид"]
            if вид == "уровень без строк":
                if lvl in без_строк_idx:
                    пропущено += 1
                    continue
            elif вид == "ведущий канал не пройден":
                if lvl in канал_idx:
                    пропущено += 1
                    continue
            elif вид == "пустое значимое поле":
                key = (lvl, d.get("строка"), d.get("поле"))
                if key in поле_idx:
                    пропущено += 1
                    continue
            else:
                continue

            code = _next_code(taken_codes)
            taken_codes.add(code)
            row = {
                "код вопроса": code,
                "формулировка": d["описание"],
                "происхождение": _ПРОИСХОЖДЕНИЕ_ПЯТНО,
                "критичность": _КРИТИЧНОСТЬ_ДЕФОЛТ,
                "уровень каркаса": level_enum.get(lvl, str(lvl)),
                "статус закрытия": "открыт",
                "дата постановки": today,
            }
            if вид == "пустое значимое поле" and d.get("строка") is not None:
                row["строка каркаса"] = [d["строка"]]
            candidates.append(row)

    заведено = 0
    if candidates:
        problems = write_rows("OQ", candidates, workspace)
        errors = [p for p in problems if getattr(p, "severity", "ERROR") == "ERROR"]
        if not errors:
            заведено = len(candidates)

    return {
        "заведено": заведено,
        "пропущено дублей": пропущено,
        "коды": [r["код вопроса"] for r in candidates] if заведено else [],
    }
