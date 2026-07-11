"""cap-render / engine — память проекта (memory/*.yaml) → канонический markdown по конфигу документа.

Замыкает несущий принцип 2 (повторяемость, спека 05-a-render): готовый документ — детерминированная
проекция зафиксированных фактов. Один прогон на одной памяти И одних параметрах обязан давать
байт-в-байт тот же md (проверяет tests/test_render.py) — поэтому здесь НЕТ «сейчас», дат генерации,
случайного порядка: строки каждой секции сортируются по ключевой колонке, счётчики выводятся из тех
же данных.

Конфиг документа (`documents/<id>/config.yaml`) описывает: паспорт (заголовок + выводимые счётчики
по таблицам), список секций (одна таблица памяти = одна секция — правило спеки; симметрия с split.py),
для каждой секции — код таблицы, ключевая колонка (сортировка), список колонок (поле контракта →
заголовок, опционально «редактируемо»), и общую подпись провенанса в конце документа.

Состав секций конфига обязан быть подмножеством контракта (`schema.model`, поле «проекция» таблицы):
это проверяет `sections_within_projection` (используется тестом и, по желанию, вызывающим кодом),
а не сам рендер — рендер лишь проецирует то, что описано в конфиге.

Параметры рендера (спека 06-b-analyze-meeting): значения фильтра секции («поле»/«значения») и путь
секции-кадров могут держать плейсхолдер `{имя}` — при рендере он подставляется параметром с тем же
именем, переданным вызывающим кодом (CLI `--источник`/`--кадры`). Плейсхолдер в конфиге, для
которого нет параметра, — явная ошибка `RenderError` (не молчаливая пустая секция). Фильтр по полю
работает и на списочном значении поля строки (после слияния write_rows источники накапливаются
списком, методика р.3): совпадение = хотя бы один элемент списка строки входит в допустимые.
Отдельный плейсхолдер `{якорь:<поле>}` (спека 06-e) — значение поля якорной строки условных секций
(`документ.якорь`), а не параметра рендера: нужен там, где фильтр секции адресуется полем, которого
у параметра рендера нет (напр. AGD ссылается на встречу кодом MTG, а параметр протокола — источник
SRC; якорь уже знает код встречи).

Секция «тип: текст» (спека 05-b-report-asis, редакция 2) вставляет зафиксированный нарративный
файл (`файл: "<относительный путь>"`) как есть — этот файл часть входа рендера, поэтому байт-
стабильность держится: тот же файл → тот же md. Подзаголовки `###` и таблицы внутри файла не
трогаются и НЕ участвуют в автонумерации секций документа (нумеруются только секции конфига).

Шаблоны документов per-project (спека 06-f, ЗР-0025): `load_config(..., workspace=...)` — если
у проекта есть свой `<workspace>/шаблоны документов/<document>.yaml`, он ЗАМЕЩАЕТ продуктовый
конфиг ЦЕЛИКОМ (тот же принцип, что у инструкций таблиц, `schema/instructions.py`); отката —
удалить файл шаблона. Обе точки рендера (`render_markdown` и `split.py::_render_canon_blocks`)
обязаны резолвить ОДИН и тот же эффективный конфиг — иначе split сравнивает md, отрендеренный
по одному конфигу, с базовой линией по другому. Проектный шаблон валидируется ЛЕНИВО, только
при рендере (не при каждом чтении): `sections_within_projection` + уникальность литеральных
«номер» секций — раньше, чем документ будет собран из битого шаблона молча.
"""

from __future__ import annotations
import re
from pathlib import Path

from linter.model import load_memory

ROOT = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_DIR = ROOT / "documents"
_TEMPLATES_DIR = "шаблоны документов"   # <проект>/шаблоны документов/<document>.yaml — замещение целиком

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png")


class RenderError(Exception):
    """Параметр, объявленный в конфиге документа (плейсхолдер «{имя}»), не передан вызывающим кодом;

    либо проектный шаблон документа (`<проект>/шаблоны документов/<document>.yaml`) не проходит
    ленивую валидацию при рендере (проекция контракта, уникальность номеров секций)."""


def _yaml():
    import yaml
    return yaml


def _project_template_path(document: str, workspace) -> Path | None:
    """Путь проектного шаблона документа, если он существует; иначе None (в т.ч. workspace=None)."""
    if workspace is None:
        return None
    path = Path(workspace) / _TEMPLATES_DIR / f"{document}.yaml"
    return path if path.is_file() else None


def load_config(document: str, documents_dir: Path = DOCUMENTS_DIR, workspace=None) -> dict:
    """Прочитать конфиг документа: проектный шаблон (если есть) ЗАМЕЩАЕТ продуктовый целиком.

    `workspace=None` (дефолт) — прежнее поведение байт-в-байт: только продуктовый конфиг,
    без служебных ключей. `workspace` задан — в возвращаемый dict добавляется служебный ключ
    «_источник_конфига»: «шаблон проекта» (найден `<workspace>/шаблоны документов/<document>.yaml`)
    или «дефолт продукта» (файла нет — откат) — используется в сообщениях об ошибках и split.
    """
    override = _project_template_path(document, workspace)
    if override is not None:
        cfg = _yaml().safe_load(override.read_text(encoding="utf-8")) or {}
        cfg["_источник_конфига"] = "шаблон проекта"
        return cfg
    path = Path(documents_dir) / document / "config.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"нет конфига документа «{document}»: {path}")
    cfg = _yaml().safe_load(path.read_text(encoding="utf-8")) or {}
    if workspace is not None:
        cfg["_источник_конфига"] = "дефолт продукта"
    return cfg


def _duplicate_section_numbers(config: dict) -> list[str]:
    """Литеральные («не авто») номера секций обязаны быть уникальны — иначе автонумерация видимых

    секций (правило render_markdown) молча даёт документ с двумя одинаково пронумерованными
    разделами. «авто» из проверки исключается — уникальность считает движок автонумерации."""
    problems: list[str] = []
    by_number: dict = {}
    for sec in config.get("секции") or []:
        номер = sec.get("номер")
        if номер is None or номер == "авто":
            continue
        by_number.setdefault(номер, []).append(sec.get("заголовок"))
    for номер, titles in by_number.items():
        if len(titles) > 1:
            problems.append(
                f"номер секции «{номер}» повторяется в секциях: {', '.join(str(t) for t in titles)}")
    return problems


def _projection_matches(declared: str, projection_name: str) -> bool:
    """Совпадение имени проекции: строка контракта РАВНА проекции документа ИЛИ

    НАЧИНАЕТСЯ С «<проекция> (» — контракт у 20+ таблиц объявляет уточнение в скобках
    («Отчёт об обследовании AS-IS (раздел …)»): это смысл раздела, не другой документ.
    Простой префикс без разделителя-скобки не считается совпадением (иначе «Отчёт об
    обследовании AS-ISX» ложно совпал бы с «Отчёт об обследовании AS-IS»).
    """
    return declared == projection_name or declared.startswith(projection_name + " (")


def sections_within_projection(config: dict, schema) -> list[str]:
    """Проверить: у каждой секции конфига таблица объявляет эту проекцию в контракте (R9-стык).

    Пустой список — конфиг согласован с контрактом. Название проекции берётся из
    `документ.проекция` конфига (одна строка — она же должна быть в `проекция:` таблицы схемы,
    точно или с уточнением в скобках — см. `_projection_matches`).
    """
    problems: list[str] = []
    document_cfg = config.get("документ") or {}
    projection_name = document_cfg.get("проекция")
    if not projection_name:
        return ["конфиг: не задано «документ.проекция»"]
    sections = config.get("секции") or []
    for sec in sections:
        if sec.get("тип") in ("кадры", "текст"):
            continue  # секция-кадры/текст не проецирует таблицу фактов — файлы, не память
        code = sec.get("таблица")
        table = schema.tables.get(code)
        if table is None:
            problems.append(f"секция «{sec.get('заголовок')}»: таблица «{code}» не в контракте")
            continue
        if not any(_projection_matches(p, projection_name) for p in (table.projection or [])):
            problems.append(
                f"секция «{sec.get('заголовок')}» (таблица {code}): проекция «{projection_name}» "
                f"не объявлена в контракте (schema/fact-tables.yaml#{code}.проекция)")
        # имена полей колонок обязаны существовать в контракте таблицы: опечатка поля иначе
        # даёт молча пустую колонку документа (рендер не отличит «нет данных» от «нет поля»)
        known = {f.name for f in table.fields}
        for col in sec.get("колонки") or []:
            if col.get("поле") not in known:
                problems.append(
                    f"секция «{sec.get('заголовок')}» (таблица {code}): поле «{col.get('поле')}» "
                    f"отсутствует в контракте таблицы")

    # условные секции («когда:», спека 06-e): защита от опечатки, чтобы «когда» не могло молча
    # навсегда спрятать секцию — якорь объявлен, поле якорной таблицы существует, а если поле
    # перечисление — все «значения» из чек-листа реально есть в его словаре
    anchor_cfg = document_cfg.get("якорь")
    when_sections = [sec for sec in sections if sec.get("когда")]
    if when_sections and not anchor_cfg:
        problems.append(
            "конфиг: есть секции с «когда», но не объявлен «документ.якорь» "
            "({таблица, поле})")
    anchor_table = schema.tables.get((anchor_cfg or {}).get("таблица")) if anchor_cfg else None
    if anchor_cfg and anchor_table is None:
        problems.append(f"конфиг: «документ.якорь.таблица» «{anchor_cfg.get('таблица')}» не в контракте")
    for sec in when_sections:
        if anchor_table is None:
            continue  # якорь отсутствует/не в контракте — уже отмечено выше
        когда = sec.get("когда") or {}
        anchor_known = {f.name: f for f in anchor_table.fields}
        field = anchor_known.get(когда.get("поле"))
        if field is None:
            problems.append(
                f"секция «{sec.get('заголовок')}»: поле «когда.{когда.get('поле')}» отсутствует "
                f"в контракте якорной таблицы «{anchor_cfg.get('таблица')}»")
            continue
        if field.enum:
            bad = [v for v in (когда.get("значения") or []) if v not in field.enum]
            if bad:
                problems.append(
                    f"секция «{sec.get('заголовок')}»: «когда.значения» {bad} не входят в "
                    f"словарь поля «{field.name}»")
    return problems


# --- чтение памяти -----------------------------------------------------------

def _rows_by_table(workspace: Path) -> dict[str, list[dict]]:
    mem = load_memory(workspace)
    out: dict[str, list[dict]] = {}
    for row in mem.rows:
        out.setdefault(row.table, []).append(row.data)
    return out


_DERIVED_REF = re.compile(r"^([A-Za-z0-9-]+)\.(.+)$")   # «TBL.поле» в «источник:» выводимого поля


def _row_key_of(table, row: dict):
    """Ключ строки таблицы: поле «код*»/«id», иначе первое поле (та же семантика, что у рельсов записи)."""
    for f in table.fields:
        nm = (f.name or "").lower()
        if nm.startswith("код") or nm == "id":
            return row.get(f.name)
    return row.get(table.fields[0].name) if table.fields else None


def _back_refs_of(src_code: str, src_field: str, table, rows_by_table: dict, schema) -> dict:
    """Обратные ссылки одного источника «TBL.поле»: {ключ_цели -> [ключи строк TBL]}."""
    src_table = schema.tables.get(src_code)
    src_rows = rows_by_table.get(src_code) or []
    back: dict = {}
    if src_table is None or not src_rows:
        return back
    for s in src_rows:
        tgt = s.get(src_field)
        for t in (tgt if isinstance(tgt, list) else [tgt]):
            if t:
                back.setdefault(str(t), []).append(_row_key_of(src_table, s))
    return back


def _augment_derived(rows_by_table: dict, codes: set, schema) -> dict:
    """Досчитать выводимые обратные ссылки для проекции (дефект стыка, валидация Ф3).

    Контракт объявляет их машинно-читаемо: «выводимое: да, источник: TBL.поле» — строки TBL,
    чьё поле указывает на ключ этой строки. Считается ТОЛЬКО в проекцию (память не трогается);
    непустое вычисленное замещает материализованное (выводимое = вычисляется, руками не ведётся),
    пустое — оставляет как есть (обратная совместимость с памятью, где связь заполнена рукой).

    «источник» может быть списком строк «TBL.поле» (ЗР-0024, напр. PRB.«требования-ответы» ←
    оба поля TB «покрывает проблемы (…)») — тогда результат объединяет обратные ссылки всех
    источников: порядок — по порядку источников в списке, внутри источника — как соберётся,
    без повторов. Одиночная строка-источник ведёт себя байт-в-байт как раньше (сортировка).
    """
    out = dict(rows_by_table)
    for code in codes:
        table = schema.tables.get(code)
        if table is None:
            continue
        for f in table.fields:
            ref = (f.raw or {}).get("источник") if f.derived else None

            if isinstance(ref, list):
                specs = []
                for r in ref:
                    m = _DERIVED_REF.match(r.strip()) if isinstance(r, str) else None
                    if m:
                        specs.append((m.group(1), m.group(2).strip()))
                if not specs:
                    continue
                back: dict = {}
                for src_code, src_field in specs:
                    for key, vals in _back_refs_of(src_code, src_field, table, rows_by_table, schema).items():
                        lst = back.setdefault(key, [])
                        for v in vals:
                            if v not in lst:
                                lst.append(v)
                rebuilt = []
                for r in out.get(code) or []:
                    computed = back.get(str(_row_key_of(table, r)))
                    rebuilt.append(dict(r, **{f.name: computed}) if computed else dict(r))
                out[code] = rebuilt
                continue

            m = _DERIVED_REF.match(ref.strip()) if isinstance(ref, str) else None
            if not m:
                continue
            src_code, src_field = m.group(1), m.group(2).strip()
            src_table = schema.tables.get(src_code)
            src_rows = rows_by_table.get(src_code) or []
            if src_table is None or not src_rows:
                continue
            back = _back_refs_of(src_code, src_field, table, rows_by_table, schema)
            rebuilt = []
            for r in out.get(code) or []:
                computed = back.get(str(_row_key_of(table, r)))
                rebuilt.append(dict(r, **{f.name: sorted(computed)}) if computed else dict(r))
            out[code] = rebuilt
    return out


def _sort_key(value) -> tuple:
    """Ключ сортировки, устойчивый к сравнению разнотипных значений (число/строка/None)."""
    if value is None:
        return (2, "")
    if isinstance(value, (int, float)):
        return (0, value)
    return (1, str(value))


def _cell_text(value) -> str:
    """Значение ячейки как текст канонического md. Списки (провенанс/аккумулированные поля) — через «; »."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(_cell_text(v) for v in value)
    return str(value)


def _escape_cell(text: str) -> str:
    """Экранировать управляющие для markdown-таблицы символы («|» ломает границу колонки, переносы строк)."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", "")


# --- параметры рендера (плейсхолдеры «{источник}»/«{кадры}» в конфиге) --------

_ANCHOR_PLACEHOLDER = re.compile(r"^\{якорь:(.+)\}$")


def _resolve(value: str, params: dict, where: str, anchor_row: dict | None = None) -> str:
    """Подставить параметры в строку-значение конфига; плейсхолдер без параметра — RenderError.

    Отдельный плейсхолдер «{якорь:<поле>}» (спека 06-e, п.2 задания фикс-06-e): значение всей
    строки целиком — вместо параметра рендера подставляется поле ЯКОРНОЙ строки условных секций
    (`_resolve_anchor_row`). Нужен там, где фильтр секции не может опираться на параметр рендера
    напрямую (AGD ссылается на встречу кодом MTG, а параметр рендера протокола — «источник» SRC;
    якорь уже знает код встречи — фильтр берёт его оттуда, не заводя второй обязательный параметр).
    Якоря нет (не определён/не найден) или в нём нет такого поля — RenderError, не молчаливая
    пустая секция."""
    anchor_match = _ANCHOR_PLACEHOLDER.match(value)
    if anchor_match:
        field = anchor_match.group(1)
        if anchor_row is None:
            raise RenderError(
                f"{where}: конфиг ожидает якорную строку для «{{якорь:{field}}}», "
                f"а якорь не определён (нет подходящего параметра рендера или совпадений)")
        if field not in anchor_row:
            raise RenderError(
                f"{where}: поле «{field}» отсутствует в якорной строке (плейсхолдер «{{якорь:{field}}}»)")
        return str(anchor_row.get(field))

    def _sub(m: "re.Match") -> str:
        name = m.group(1)
        if name not in params or params[name] in (None, ""):
            raise RenderError(
                f"{where}: конфиг ожидает параметр «{name}» (плейсхолдер «{{{name}}}»), "
                f"он не передан — укажите ./opp render … --{name} <значение>")
        return str(params[name])
    return _PLACEHOLDER.sub(_sub, value)


def _row_matches_filter(row: dict, field: str, allowed: set) -> bool:
    """Совпадение фильтра: значение поля строки может быть списком (накопленные источники,
    методика р.3) — совпадение, если хотя бы один элемент списка входит в допустимые.
    Сравнение строковое: «значения» конфига проходят подстановку плейсхолдеров и приходят
    строками, а поле строки может быть числом (уровень каркаса) — типы не должны мешать."""
    value = row.get(field)
    if isinstance(value, list):
        return any(str(v) in allowed for v in value)
    return str(value) in allowed


def _resolve_anchor_row(anchor_cfg: dict | None, rows_by_table: dict, params: dict) -> dict | None:
    """Якорная строка условных секций «когда:» (спека 06-e): строка `документ.якорь.таблица`,
    у которой поле `документ.якорь.поле` содержит текущий параметр «источник» (та же логика
    совпадения, что у фильтра секции — `_row_matches_filter`; поле обычно списочное-выводимое,
    напр. MTG.«источники из встречи» ← SRC.«ссылка на встречу»).

    Якоря нет в конфиге, параметр «источник» не передан или совпадений нет — None: условные
    секции считаются скрытыми (протокол деградирует к безусловным секциям, не ошибка).
    Структурно совпадений ≤1 (SRC.«ссылка на встречу» — одиночная ссылка); если их больше —
    это дефект данных, не рендера, берётся первая.
    """
    if not anchor_cfg:
        return None
    src_value = params.get("источник")
    if not src_value:
        return None
    field = anchor_cfg.get("поле")
    for row in rows_by_table.get(anchor_cfg.get("таблица")) or []:
        if _row_matches_filter(row, field, {str(src_value)}):
            return row
    return None


# --- сборка md ----------------------------------------------------------------

def _passport_md(config: dict, rows_by_table: dict) -> list[str]:
    passport = config.get("паспорт") or {}
    lines = [f"# {passport.get('заголовок', config.get('документ', {}).get('название', ''))}", ""]
    counters = passport.get("счётчики") or []
    if counters:
        lines.append("## Паспорт")
        lines.append("")
        for c in counters:
            code = c.get("таблица")
            n = len(rows_by_table.get(code, []))
            lines.append(f"- {c.get('подпись', code)}: {n}")
        lines.append("")
    return lines


def _section_title(section: dict) -> str:
    # «подуровень: да» — таблица-вкрапление внутри раздела: ### без номера (иерархия
    # корпоративного документа, редакция 2 спеки 05-b); автонумерация её не считает
    if section.get("подуровень"):
        return f"### {section.get('заголовок', '')}"
    номер = section.get("номер")
    заголовок = section.get("заголовок", "")
    return f"## {номер}. {заголовок}" if номер else f"## {заголовок}"


def _make_resolver(rows_by_table: dict, schema):
    """Резолвер «код → человеческое имя» для колонок с «резолв: да» (корпоративная редакция:
    коды — адресация памяти, читателю нужны имена). Имя = первое непустое текстовое поле
    строки, не начинающееся с «код» (та же эвристика, что у дайджеста памяти). Код, не
    найденный в целевых таблицах, остаётся как есть (честнее, чем пустота)."""
    titles: dict = {}   # (код таблицы) -> {ключ строки -> имя}

    def _titles_of(code: str) -> dict:
        if code in titles:
            return titles[code]
        table = schema.tables.get(code)
        out: dict = {}
        for r in rows_by_table.get(code) or []:
            key = _row_key_of(table, r) if table else None
            if key is None:
                continue
            name = next((str(r[f.name]) for f in (table.fields if table else [])
                         if f.kind == "текст" and not (f.name or "").lower().startswith("код")
                         and r.get(f.name)), None)
            out[str(key)] = name or str(key)
        titles[code] = out
        return out

    def resolve(value, target_codes: list) -> object:
        def one(v):
            for tc in target_codes:
                hit = _titles_of(tc).get(str(v))
                if hit is not None:
                    return hit
            return v
        if isinstance(value, list):
            return [one(v) for v in value]
        return one(value) if value is not None else value

    return resolve


def _column_targets(table, field_name: str) -> list:
    """Целевые таблицы поля-ссылки по контракту (для резолва кодов в имена)."""
    from schema.model import targets_of
    if table is None:
        return []
    for f in table.fields:
        if f.name == field_name:
            return [t for t in targets_of(f.target) if isinstance(t, str)]
    return []


def _section_md(section: dict, rows: list[dict], params: dict,
                resolver=None, schema=None, anchor_row: dict | None = None) -> tuple[list[str], int]:
    """Строки md секции + число ПОКАЗАННЫХ строк (после фильтра — оно идёт в подпись «строк: N»).

    Пустой список строк md означает «секция скрыта целиком» (флаг «скрывать пустую: да» + нет
    строк после фильтра) — так протокол не тащит пустые разделы, не относящиеся к источнику.
    """
    title = _section_title(section)
    columns = section.get("колонки") or []
    key_field = section.get("ключ") or (columns[0]["поле"] if columns else None)
    sort_field = section.get("сортировка", key_field)
    where = f"секция «{section.get('заголовок')}»"

    # фильтр опциональный: {поле, значения} — оставить только строки со значением из списка;
    # значения фильтра могут нести плейсхолдер «{источник}» — подставляется параметром рендера
    filtro = section.get("фильтр")
    filtered = rows
    if filtro and filtro.get("поле"):
        raw_values = filtro.get("значения") or []
        if anchor_row is None and any(_ANCHOR_PLACEHOLDER.match(str(v)) for v in raw_values):
            # якорной строки для этого рендера нет (источник/встреча не найдены среди якорной
            # таблицы) — секция, чей фильтр адресуется полем якоря, не может дать совпадений;
            # это деградация протокола (спека 06-e), не ошибка конфига (та ловится отдельно,
            # ниже по коду документа-уровня — «когда»/«{якорь:…}» без «документ.якорь»)
            filtered = []
        else:
            allowed = {_resolve(str(v), params, where, anchor_row) for v in raw_values}
            filtered = [r for r in rows if _row_matches_filter(r, filtro["поле"], allowed)]

    if not filtered and section.get("скрывать пустую"):
        return [], 0

    lines = [title, ""]
    ordered = sorted(filtered, key=lambda r: _sort_key(r.get(sort_field)))

    if not ordered:
        lines.append("_Нет строк._")
        lines.append("")
        return lines, 0

    headers = [c.get("заголовок", c["поле"]) for c in columns]
    table = schema.tables.get(section.get("таблица")) if schema else None
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in ordered:
        cells = []
        for c in columns:
            value = row.get(c["поле"])
            if c.get("резолв") and resolver is not None:
                value = resolver(value, _column_targets(table, c["поле"]))
            cells.append(_escape_cell(_cell_text(value)))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines, len(ordered)


# --- секция «тип: процессы» (спека 06-e): дерево PRC ---------------------------

_PRC_KEY_FIELD = "Код узла"
_PRC_PARENT_FIELD = "Родитель"
_PRC_LEVEL_FIELD = "Уровень декомпозиции"
_PRC_LEVEL_HEADERS = {"функция": "###", "процесс": "####", "подпроцесс": "#####"}
_PRC_STEP_LEVEL = "шаг (операция)"
_PRC_GATE_FIELD = "Точка решения"
_PRC_GATE_VALUE = "точка решения"


def _prc_ancestors(selected_codes, by_code: dict) -> tuple[set, set, set]:
    """Предки выборки до корня (полная таблица PRC) + пометки «контекст»/«цикл».

    Возвращает (union_codes, context_codes, cycle_codes): union — выборка + все предки;
    context — предки НЕ из выборки (скелет-заголовки без деталей); cycle — узел, на
    котором подъём оборван зацикленной цепочкой «Родитель» (дефект данных, не рендера).
    """
    union_codes = set(selected_codes)
    context_codes: set = set()
    cycle_codes: set = set()
    for start in selected_codes:
        seen = {start}
        cur = start
        while True:
            row = by_code.get(cur)
            parent = row.get(_PRC_PARENT_FIELD) if row else None
            if not parent:
                break
            if parent in seen:
                cycle_codes.add(cur)
                break
            if parent not in by_code:
                break  # родитель не найден в PRC вовсе — обрыв, не цикл
            seen.add(parent)
            union_codes.add(parent)
            if parent not in selected_codes:
                context_codes.add(parent)
            cur = parent
    return union_codes, context_codes, cycle_codes


def _process_tree_md(section: dict, all_rows: list[dict], params: dict,
                      anchor_row: dict | None = None) -> tuple[list[str], int]:
    """Секция «тип: процессы»: детерминированное дерево PRC функция→процесс→подпроцесс,
    операции («шаг (операция)») — таблицей под своим непосредственным родителем.

    `all_rows` — ПОЛНАЯ таблица PRC (не только выборка секции): предки узлов выборки, лежащие
    вне фильтра, подтягиваются заголовками-скелетами с пометкой «контекст» (норма: один блок
    процессов разбирается на нескольких встречах, провенанс не размывается). Защита от циклов
    родительской цепочки — обязательна (данные не гарантированно ацикличны).
    Возвращает (lines, count), count = число строк ИЗ ВЫБОРКИ (контекстные предки не считаются),
    как у `_section_md` — секция участвует в общем счётчике «строк: N».
    """
    title = _section_title(section)
    where = f"секция «{section.get('заголовок')}»"

    filtro = section.get("фильтр")
    selected = all_rows
    if filtro and filtro.get("поле"):
        raw_values = filtro.get("значения") or []
        if anchor_row is None and any(_ANCHOR_PLACEHOLDER.match(str(v)) for v in raw_values):
            selected = []   # якорной строки нет для этого рендера — деградация, не ошибка (см. _section_md)
        else:
            allowed = {_resolve(str(v), params, where, anchor_row) for v in raw_values}
            selected = [r for r in all_rows if _row_matches_filter(r, filtro["поле"], allowed)]

    if not selected and section.get("скрывать пустую"):
        return [], 0

    if not selected:
        return [title, "", "_Нет строк._", ""], 0

    by_code = {r.get(_PRC_KEY_FIELD): r for r in all_rows if r.get(_PRC_KEY_FIELD)}
    selected_codes = {r.get(_PRC_KEY_FIELD) for r in selected if r.get(_PRC_KEY_FIELD)}
    union_codes, context_codes, cycle_codes = _prc_ancestors(selected_codes, by_code)

    children: dict = {}
    roots: list = []
    for code in union_codes:
        if code in cycle_codes:
            # цепочка «Родитель» оборвана здесь (_prc_ancestors обнаружил цикл на подъёме) —
            # ребро к родителю НЕ строим, иначе мутный цикл A↔B оставит оба узла без общего
            # корня (каждый «ребёнок» другого) и оба выпадут из обхода дерева молча
            roots.append(code)
            continue
        parent = by_code[code].get(_PRC_PARENT_FIELD)
        if parent and parent in union_codes and parent != code:
            children.setdefault(parent, []).append(code)
        else:
            roots.append(code)

    def sort_key(code):
        row = by_code[code]
        return (_sort_key(row.get("Порядок в потоке")), _sort_key(row.get(_PRC_KEY_FIELD)))

    roots.sort(key=sort_key)
    for lst in children.values():
        lst.sort(key=sort_key)

    lines: list[str] = [title, ""]

    def render_operations(op_codes: list) -> None:
        lines.append("| Операция | Вход | Действие | Выход | Система | Владелец | Локатор |")
        lines.append("|---|---|---|---|---|---|---|")
        for oc in op_codes:
            row = by_code[oc]
            name = row.get("Название", "") or ""
            is_gate = row.get(_PRC_GATE_FIELD) == _PRC_GATE_VALUE
            name_cell = f"⬦ {name} (шлюз)" if is_gate else name
            cells = [name_cell, row.get("Вход"), row.get("Действие"), row.get("Выход"),
                     row.get("Система"), row.get("Владелец"), row.get("локатор в источнике")]
            lines.append("| " + " | ".join(_escape_cell(_cell_text(c)) for c in cells) + " |")
        lines.append("")

    def render_node(code, path: frozenset) -> None:
        if code in path:
            return  # доп. подстраховка обхода (цикл уже помечен на этапе сбора предков)
        row = by_code[code]
        level = row.get(_PRC_LEVEL_FIELD)
        name = row.get("Название", "") or ""
        marker = _PRC_LEVEL_HEADERS.get(level, "######")
        suffix = " _(контекст — из других встреч)_" if code in context_codes else ""
        suffix += " _(цикл в иерархии — дефект данных)_" if code in cycle_codes else ""
        lines.append(f"{marker} {name}{suffix}")
        lines.append("")
        if code not in context_codes:
            fragments = [f"{lbl}: {row.get(fld)}" for fld, lbl in
                         (("Вход", "Вход"), ("Действие", "Действие"), ("Выход", "Выход")) if row.get(fld)]
            if fragments:
                lines.append(f"_{'; '.join(fragments)}_")
                lines.append("")
        kids = children.get(code) or []
        op_codes = [c for c in kids if by_code[c].get(_PRC_LEVEL_FIELD) == _PRC_STEP_LEVEL]
        other_codes = [c for c in kids if by_code[c].get(_PRC_LEVEL_FIELD) != _PRC_STEP_LEVEL]
        if op_codes:
            render_operations(op_codes)
        for oc in other_codes:
            render_node(oc, path | {code})

    for r in roots:
        if by_code[r].get(_PRC_LEVEL_FIELD) == _PRC_STEP_LEVEL:
            render_operations([r])   # операция-сирота (родителя нет вовсе) — не молчим
        else:
            render_node(r, frozenset())

    return lines, len(selected_codes)


def _frames_section_md(section: dict, workspace: Path, params: dict) -> list[str]:
    """Секция «тип: кадры»: перечисляет *.jpg/*.png из «<ws>/{кадры}» по сортировке имён.

    Путь несёт плейсхолдер «{кадры}» — параметр не задан → секция скрывается целиком (не ошибка:
    демо-встреча без кадров — обычный случай, спека 06-b). Параметр задан, но папки нет/она
    пуста — секция рендерится с пометкой «нет кадров», молчаливой пропажи не бывает.
    """
    raw_path = section.get("путь", "")
    name_match = _PLACEHOLDER.search(raw_path)
    if name_match and name_match.group(1) not in params:
        return []  # параметр не передан — секция про кадры не относится к этому рендеру

    where = f"секция «{section.get('заголовок')}»"
    rel_path = _resolve(raw_path, params, where)
    lines = [_section_title(section), ""]

    folder = Path(workspace) / rel_path
    images = []
    if folder.is_dir():
        images = sorted(p for p in folder.iterdir() if p.suffix.lower() in _IMAGE_EXTS)

    if not images:
        lines.append("_Нет кадров._")
        lines.append("")
        return lines

    for img in images:
        caption = img.stem
        lines.append(f"![{caption}]({rel_path}/{img.name})")
    lines.append("")
    return lines


def _text_section_md(section: dict, workspace: Path, params: dict) -> list[str]:
    """Секция «тип: текст»: вставляет содержимое файла нарратива как есть (спека 05-b, редакция 2).

    Файл — зафиксированный вход рендера (та же байт-стабильность, что и у остальных секций):
    путь может нести плейсхолдер («{имя}», как у секции-кадров), поддержаны ###-подзаголовки и
    md-таблицы внутри файла — они не участвуют в автонумерации секций (нумеруются только секции
    конфига, см. render_markdown). Файла нет — секция скрывается, если «скрывать пустую: да»,
    иначе явная пометка «_Раздел не подготовлен._» (молчаливых пропаж нет, методика доказуемости).
    """
    raw_path = section.get("файл", "")
    name_match = _PLACEHOLDER.search(raw_path)
    if name_match and name_match.group(1) not in params:
        return []  # параметр не передан — секция про этот нарратив не относится к рендеру

    where = f"секция «{section.get('заголовок')}»"
    rel_path = _resolve(raw_path, params, where)
    full_path = Path(workspace) / rel_path

    if not full_path.is_file():
        if section.get("скрывать пустую"):
            return []
        lines = [_section_title(section), "", "_Раздел не подготовлен._", ""]
        return lines

    body = full_path.read_text(encoding="utf-8").rstrip("\n")
    lines = [_section_title(section), ""]
    lines += body.split("\n")
    lines.append("")
    return lines


def _signature_md(config: dict, total_rows: int) -> list[str]:
    """Подпись провенанса. Плейсхолдер «{N}» в конфиге заменяется числом строк документа."""
    template = config.get("подпись", "")
    text = template.replace("{N}", str(total_rows))
    return ["---", "", text, ""]


def render_markdown(document: str, workspace, documents_dir: Path = DOCUMENTS_DIR,
                     params: dict | None = None) -> str:
    """Собрать канонический md-документ из памяти рабочего пространства по конфигу.

    Байт-стабильно: одинаковая память + одинаковые параметры → одинаковый md (никаких дат/«сейчас»/
    случайного порядка). `params` — значения плейсхолдеров конфига (напр. {"источник": "SRC-MTG-01",
    "кадры": "Кадры/демо"}); плейсхолдер без параметра — RenderError с понятным текстом.
    """
    workspace = Path(workspace)
    config = load_config(document, documents_dir, workspace=workspace)
    params = params or {}
    rows_by_table = _rows_by_table(workspace)

    # схема нужна и для ленивой валидации проектного шаблона (ниже), и позже — для аугментации
    # выводимых обратных ссылок в проекцию (контракт: «выводимое: да, источник: TBL.поле»)
    from schema.model import load_schema
    schema = load_schema()

    if config.get("_источник_конфига") == "шаблон проекта":
        # ленивая валидация проектного шаблона (спека 06-f): та же проверка, что и у продуктовых
        # конфигов (проекция контракта), плюс уникальность литеральных номеров секций — раньше,
        # чем документ будет молча собран из битого шаблона
        template_path = _project_template_path(document, workspace)
        problems = sections_within_projection(config, schema) + _duplicate_section_numbers(config)
        if problems:
            raise RenderError(
                f"шаблон документа проекта {template_path}: {'; '.join(problems)}; "
                "исправьте шаблон или удалите его для отката к дефолту")

    sections = config.get("секции") or []
    anchor_cfg = (config.get("документ") or {}).get("якорь")
    if any(s.get("когда") for s in sections) and not anchor_cfg:
        raise RenderError(
            "конфиг документа: секции используют «когда», но не объявлен «документ.якорь» "
            "({таблица, поле}) — без якоря условные секции не могут определить свой тип встречи")
    if not anchor_cfg and any(
            isinstance(v, str) and _ANCHOR_PLACEHOLDER.match(v)
            for s in sections for v in (s.get("фильтр") or {}).get("значения") or []):
        raise RenderError(
            "конфиг документа: фильтр секции использует «{якорь:…}», но не объявлен «документ.якорь» "
            "({таблица, поле}) — без якоря плейсхолдер нечем подставить")

    # выводимые обратные ссылки (контракт: «выводимое: да, источник: TBL.поле») досчитываются
    # в проекцию — без этого секции, фильтрующие по ним (паспорт встречи), пусты (валидация Ф3)
    section_codes = {s.get("таблица") for s in sections if s.get("таблица")}
    if anchor_cfg and anchor_cfg.get("таблица"):
        section_codes.add(anchor_cfg["таблица"])   # якорная таблица тоже нуждается в аугментации
    rows_by_table = _augment_derived(rows_by_table, section_codes, schema)
    resolver = _make_resolver(rows_by_table, schema)   # «резолв: да» у колонки: код → имя
    anchor_row = _resolve_anchor_row(anchor_cfg, rows_by_table, params)

    lines: list[str] = []
    lines += _passport_md(config, rows_by_table)

    total_rows = 0
    auto_n = 0   # автонумерация ВИДИМЫХ секций («номер: авто») — скрытая пустая не дырявит счёт
    for section in sections:
        # условная секция («когда:», спека 06-e): якоря нет или значение не в списке — секция
        # пропускается ДО выборки строк, как если бы её не было в конфиге вовсе (номер/счётчик
        # не расходуются); безусловные секции («когда» не задан) идут как раньше
        когда = section.get("когда")
        if когда and (anchor_row is None
                      or not _row_matches_filter(anchor_row, когда.get("поле"),
                                                  {str(v) for v in (когда.get("значения") or [])})):
            continue
        if section.get("тип") == "кадры":
            frame_lines = _frames_section_md(section, workspace, params)
            if frame_lines and section.get("номер") == "авто":
                auto_n += 1
                frame_lines[0] = f"## {auto_n}. {section.get('заголовок', '')}"
            lines += frame_lines
            continue
        if section.get("тип") == "текст":
            text_lines = _text_section_md(section, workspace, params)
            if text_lines and section.get("номер") == "авто":
                auto_n += 1
                text_lines[0] = f"## {auto_n}. {section.get('заголовок', '')}"
            lines += text_lines
            continue
        if section.get("тип") == "процессы":
            code = section.get("таблица")
            tree_lines, shown = _process_tree_md(section, rows_by_table.get(code, []), params,
                                                  anchor_row=anchor_row)
            if tree_lines and section.get("номер") == "авто":
                auto_n += 1
                tree_lines[0] = f"## {auto_n}. {section.get('заголовок', '')}"
            total_rows += shown
            lines += tree_lines
            continue
        code = section.get("таблица")
        rows = rows_by_table.get(code, [])
        section_lines, shown = _section_md(section, rows, params, resolver=resolver, schema=schema,
                                            anchor_row=anchor_row)
        if section_lines and section.get("номер") == "авто":
            auto_n += 1
            section_lines[0] = f"## {auto_n}. {section.get('заголовок', '')}"
        total_rows += shown
        lines += section_lines

    lines += _signature_md(config, total_rows)

    # ровно один финальный перевод строки — без хвостовых пустых строк вариативной длины
    text = "\n".join(lines)
    while text.endswith("\n\n\n"):
        text = text[:-1]
    return text.rstrip("\n") + "\n"
