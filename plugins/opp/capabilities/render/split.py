"""cap-render / split — обратный ход рендера: правленый md → правки ячеек → память проекта.

Симметрия с engine.py (методика «правь-и-верни», спека 05-a-render): пользователь получает
канонический md (или docx → руками сверяет с md), правит СОГЛАСОВАННЫЕ ячейки таблиц, split
разбирает правленый md обратно по тому же конфигу документа и отдаёт правки в `schema.extract.
write_rows` (слияние + история) — так же, как это делают навыки-экстракторы.

Границы (доказуемость: память ≠ проза, спека):
- редактируемые колонки — ТОЛЬКО те, что в конфиге документа помечены «редактируемо: да»
  (для протокола материалов: MAT.статус разбора, MAT.примечание, SRC.надёжность,
  OQ.статус закрытия, OQ.резолюция — согласовано спекой);
- правка нередактируемой ЯЧЕЙКИ — предупреждение, сама ячейка в память не идёт (легитимные
  правки соседних ячеек при этом применяются); изменённая СТРУКТУРА (число таблиц/строк,
  заголовки) — предупреждение и отказ на уровне секции/документа целиком: базовая линия
  сравнения потеряна, ни одна правка не применяется.

Блоки-картинки («![подпись](путь)», секция «тип: кадры» — спека 06-b) split не структурная правка:
`_table_blocks` берёт из разбора md только блоки `table`, поэтому картинки не входят ни в базовую
линию сравнения, ни в правленый md — split их просто не видит (не нужно отдельного игнор-правила).
"""

from __future__ import annotations
from pathlib import Path

from linter.violation import Violation
from schema.extract import write_rows
from .engine import load_config, DOCUMENTS_DIR
from .docx import _parse_blocks  # переиспользуем разбор md → блоки (симметрия с docx.py)


def _editable_fields(section: dict) -> set:
    return {c["поле"] for c in (section.get("колонки") or []) if c.get("редактируемо")}


def _table_blocks(blocks: list[dict]) -> list[dict]:
    return [b for b in blocks if b["type"] == "table"]


def _row_by_key(rows: list[dict], key_field: str, key_value: str) -> dict | None:
    for r in rows:
        if str(r.get(key_field)) == str(key_value):
            return r
    return None


def split_document(document: str, edited_md_path, workspace,
                    documents_dir: Path = DOCUMENTS_DIR) -> tuple[list[dict], list]:
    """Разобрать правленый md документа и вернуть строки-правки по таблицам + предупреждения.

    Возвращает (patches, warnings): `patches` — [{«таблица»: код, «строки»: [...]}] готовые к
    `schema.extract.write_rows`; `warnings` — список `linter.Violation` (severity=WARN) на
    нередактируемые/структурные правки — они НЕ применяются (в память не идут).
    """
    workspace = Path(workspace)
    # workspace передаётся в load_config — та же точка резолва проектного шаблона (спека 06-f),
    # что и у _render_canon_blocks ниже (через render_markdown): один эффективный конфиг на обе
    # стороны сравнения, иначе базовая линия и правленый md были бы разобраны по разным секциям
    config = load_config(document, documents_dir, workspace=workspace)
    edited_text = Path(edited_md_path).read_text(encoding="utf-8")

    canon_blocks = _table_blocks(_render_canon_blocks(document, workspace, documents_dir))
    edited_blocks = _table_blocks(_parse_blocks(edited_text))

    sections = config.get("секции") or []
    warnings: list = []
    patches: list[dict] = []

    if len(canon_blocks) != len(edited_blocks):
        message = "структура документа изменена (число таблиц не совпадает) — правки не применены"
        if config.get("_источник_конфига") == "шаблон проекта":
            # смена шаблона проекта между рендером и split — частая причина расхождения структуры
            # (спека 06-f); понятная подсказка вместо голого «структура изменена»
            message += ("; возможно, шаблон документа менялся после рендера — пересоберите "
                        "документ и перенесите правки заново")
        warnings.append(Violation(where=document, message=message, severity="WARN"))
        return [], warnings

    for section, canon_tbl, edited_tbl in zip(sections, canon_blocks, edited_blocks):
        code = section.get("таблица")
        columns = section.get("колонки") or []
        key_field = section.get("ключ") or (columns[0]["поле"] if columns else None)
        editable = _editable_fields(section)
        header_to_field = {c.get("заголовок", c["поле"]): c["поле"] for c in columns}

        if edited_tbl["header"] != canon_tbl["header"]:
            warnings.append(Violation(where=f"{document}#{code}",
                message="заголовки таблицы изменены — секция не применена", severity="WARN"))
            continue
        if len(edited_tbl["rows"]) != len(canon_tbl["rows"]):
            warnings.append(Violation(where=f"{document}#{code}",
                message="число строк изменено (добавление/удаление не поддержано split) — "
                        "секция не применена", severity="WARN"))
            continue

        # индекс: позиция ключевой колонки
        try:
            key_pos = canon_tbl["header"].index(
                next(c.get("заголовок", c["поле"]) for c in columns if c["поле"] == key_field))
        except StopIteration:
            key_pos = 0

        section_patch_rows: list[dict] = []
        for canon_row, edited_row in zip(canon_tbl["rows"], edited_tbl["rows"]):
            key_value = canon_row[key_pos] if key_pos < len(canon_row) else None
            row_changes: dict = {}
            row_ok = True
            for pos, header in enumerate(canon_tbl["header"]):
                field = header_to_field.get(header)
                old_val = canon_row[pos] if pos < len(canon_row) else ""
                new_val = edited_row[pos] if pos < len(edited_row) else ""
                if old_val == new_val:
                    continue
                if field in editable:
                    row_changes[field] = new_val
                else:
                    warnings.append(Violation(
                        where=f"{document}#{code}[{key_value}].{field}",
                        message="правка нередактируемой колонки — предупреждение, "
                                "в память не идёт (эта ячейка не применена)",
                        severity="WARN"))
                    row_ok = False
            if row_changes and row_ok:
                row_changes[key_field] = key_value
                section_patch_rows.append(row_changes)
            elif row_changes and not row_ok:
                # смешанная строка: применяем ТОЛЬКО легитимные поля этой строки —
                # нередактируемая правка в той же строке уже отмечена предупреждением выше,
                # но легитимная правка соседней ячейки не должна из-за неё пропадать.
                legit = {k: v for k, v in row_changes.items() if k in editable}
                if legit:
                    legit[key_field] = key_value
                    section_patch_rows.append(legit)

        if section_patch_rows:
            patches.append({"таблица": code, "строки": section_patch_rows})

    return patches, warnings


def _render_canon_blocks(document: str, workspace: Path, documents_dir: Path) -> list[dict]:
    """Блоки канонического (текущего) md — базовая линия сравнения для split."""
    from .engine import render_markdown
    canon_md = render_markdown(document, workspace, documents_dir)
    return _parse_blocks(canon_md)


def apply_split(document: str, edited_md_path, workspace,
                 documents_dir: Path = DOCUMENTS_DIR) -> list:
    """Разобрать правленый md и записать легитимные правки в память (write_rows: слияние+история).

    Возвращает список `linter.Violation`: WARN на непринятые правки (структура/нередактируемое)
    и, если запись какой-либо секции отклонена контрактом, — сами ERROR-нарушения write_rows.
    """
    patches, warnings = split_document(document, edited_md_path, workspace, documents_dir)
    problems: list = list(warnings)
    for patch in patches:
        problems.extend(write_rows(patch["таблица"], patch["строки"], workspace))
    return problems
