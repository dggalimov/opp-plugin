"""Каркас OPP: загрузка из данных и детерминированная отрисовка.

Источник истины — `framework.yaml` и `glossary.yaml`. Человекочитаемое `framework.md` и раздел
«Каркас» в окне — проекции этих данных. Те же данные → тот же результат.
"""

from __future__ import annotations
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAMEWORK_YAML = HERE / "framework.yaml"
GLOSSARY_YAML = HERE / "glossary.yaml"
FRAMEWORK_MD = HERE / "framework.md"

_LEVEL_FIELDS = ("номер", "полоса", "название", "что_в_нём", "что_выясняем",
                 "дефекты", "перекрёстные_сверки", "акцент_источника")
_FIELD_LABELS = {
    "что_в_нём": "Что в нём",
    "что_выясняем": "Что выясняем",
    "дефекты": "Дефекты",
    "перекрёстные_сверки": "Перекрёстные сверки",
    "акцент_источника": "Акцент источника",
}


def _load(path: Path):
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_framework() -> dict:
    return _load(FRAMEWORK_YAML)


def load_glossary() -> list:
    return _load(GLOSSARY_YAML).get("термины", [])


def validate_framework(fw=None, glossary=None) -> list[str]:
    """Проверить целостность каркаса. Пустой список — всё в порядке."""
    problems: list[str] = []
    try:
        fw = fw if fw is not None else load_framework()
        glossary = glossary if glossary is not None else load_glossary()
    except Exception as exc:  # nет PyYAML или битый файл
        return [f"каркас не читается: {exc}"]

    levels = fw.get("уровни", [])
    if len(levels) != 11:
        problems.append(f"ожидалось 11 уровней, найдено {len(levels)}")
    numbers = []
    for i, lvl in enumerate(levels, start=1):
        for field in _LEVEL_FIELDS:
            if not lvl.get(field):
                problems.append(f"уровень №{lvl.get('номер', i)}: пустое поле «{field}»")
        numbers.append(lvl.get("номер"))
    if numbers and sorted(n for n in numbers if isinstance(n, int)) != list(range(1, 12)):
        problems.append(f"номера уровней должны быть 1..11, получено {numbers}")
    if "оси" not in fw:
        problems.append("не заданы оси (уровень каркаса / глубина процесса)")
    if "полосы" not in fw:
        problems.append("не заданы полосы (Бизнес / ИТ)")
    if not glossary:
        problems.append("пустой глоссарий")
    return problems


def render_markdown(fw=None, glossary=None) -> str:
    fw = fw if fw is not None else load_framework()
    glossary = glossary if glossary is not None else load_glossary()
    out: list[str] = []
    out.append("# Каркас OPP — 11 уровней\n")
    out.append("> Сгенерировано из `framework.yaml`. Руками не править — правьте данные.\n")

    oси = fw.get("оси", {})
    out.append("## Оси\n")
    for key, ax in oси.items():
        rng = ax.get("диапазон")
        out.append(f"- **{key.replace('_', ' ')}** ({rng[0]}–{rng[1]}): {ax.get('смысл')}")
    out.append("")

    by_band: dict[str, list] = {}
    for lvl in fw.get("уровни", []):
        by_band.setdefault(lvl["полоса"], []).append(lvl)
    for band in by_band:
        out.append(f"## Полоса «{band}»\n")
        for lvl in by_band[band]:
            out.append(f"### {lvl['номер']}. {lvl['название']}")
            for field in ("что_в_нём", "что_выясняем", "дефекты", "перекрёстные_сверки"):
                out.append(f"- **{_FIELD_LABELS[field]}:** {lvl[field]}")
            src = ", ".join(lvl.get("акцент_источника", []))
            out.append(f"- **{_FIELD_LABELS['акцент_источника']}:** {src}")
            out.append("")

    out.append("## Глоссарий\n")
    for item in glossary:
        out.append(f"- **{item['термин']}** — {item['определение']}")
    out.append("")
    return "\n".join(out)


def write_markdown() -> Path:
    FRAMEWORK_MD.write_text(render_markdown(), encoding="utf-8")
    return FRAMEWORK_MD


_TABLE_COLS = (("что_в_нём", "Что в нём"), ("что_выясняем", "Что выясняем"),
               ("дефекты", "Дефекты"), ("перекрёстные_сверки", "Перекрёстные сверки"))


def render_framework_html() -> str:
    """Внутренний HTML страницы «Каркас» для окна — таблицами."""
    fw = load_framework()
    glossary = load_glossary()
    parts: list[str] = []

    parts.append('<p class="muted">Общая «линза» продукта. Перекрёстные сверки — рабочий чек-лист '
                 'для поиска проблем на аудите (расхождение = проблема / гипотеза / открытый вопрос).</p>')

    parts.append('<div class="axes">')
    for key, ax in fw.get("оси", {}).items():
        rng = ax.get("диапазон")
        parts.append(f'<div><b>{html.escape(key.replace("_", " "))}</b> '
                     f'({rng[0]}–{rng[1]}): {html.escape(ax.get("смысл", ""))}</div>')
    parts.append('</div>')

    by_band: dict[str, list] = {}
    for lvl in fw.get("уровни", []):
        by_band.setdefault(lvl["полоса"], []).append(lvl)

    for band, levels in by_band.items():
        parts.append(f'<h2 class="band">Полоса «{html.escape(band)}»</h2>')
        parts.append('<div class="tablewrap"><table class="fw"><thead><tr><th>Уровень</th>')
        parts.extend(f'<th>{label}</th>' for _, label in _TABLE_COLS)
        parts.append('</tr></thead><tbody>')
        for lvl in levels:
            src = ", ".join(lvl.get("акцент_источника", []))
            parts.append('<tr>')
            parts.append(f'<td><b>{lvl["номер"]}. {html.escape(lvl["название"])}</b>'
                         f'<div class="src">Источники: {html.escape(src)}</div></td>')
            for field, _label in _TABLE_COLS:
                cls = ' class="checks"' if field == "перекрёстные_сверки" else ''
                parts.append(f'<td{cls}>{html.escape(lvl[field])}</td>')
            parts.append('</tr>')
        parts.append('</tbody></table></div>')

    parts.append('<h2 class="band">Глоссарий</h2>')
    parts.append('<div class="tablewrap"><table class="fw"><thead><tr>'
                 '<th>Термин</th><th>Определение</th></tr></thead><tbody>')
    for item in glossary:
        parts.append(f'<tr><td><b>{html.escape(item["термин"])}</b></td>'
                     f'<td>{html.escape(item["определение"])}</td></tr>')
    parts.append('</tbody></table></div>')
    return "\n".join(parts)


if __name__ == "__main__":
    problems = validate_framework()
    if problems:
        for p in problems:
            print("ОШИБКА:", p)
        raise SystemExit(1)
    path = write_markdown()
    print(f"Описание каркаса сгенерировано: {path}")
