"""Архитектура источников (бронза): загрузка, проверка, отрисовка для окна.

Архитектура зафиксирована — типы источников, адаптеры форматов, типы встреч; конвейер обработки
(приём, конвертация, транскрибация, извлечение из базы) реализован (компонент 02 — готово).
Списки «готово/в плане» для окна выводятся из единого источника (plan/02.yaml), не хардкодятся.
"""

from __future__ import annotations
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent
TYPES_YAML = HERE / "source-types.yaml"
ADAPTERS_YAML = HERE / "adapters.yaml"
MEETINGS_YAML = HERE / "meeting-types.yaml"

def plan_items() -> tuple[list, list]:
    """«Готово» / «в плане» — вывод из единого источника (plan/02.yaml). Профили — одной строкой."""
    import plan as plan_mod
    done, ahead = [], []
    profiles = 0
    for e in plan_mod.load_component("02"):
        if e.get("тип") == "профиль":
            profiles += 1 if e.get("статус") == "готово" else 0
            continue
        (done if e.get("статус") == "готово" else ahead).append(str(e.get("задача", "")))
    if profiles:
        done.append(f"Профили сбора данных на конфигурацию: {profiles}")
    return done, ahead


def _load(path: Path):
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_types() -> list:
    return _load(TYPES_YAML).get("типы", [])


def load_adapters() -> list:
    return _load(ADAPTERS_YAML).get("группы", [])


def load_meeting_types() -> list:
    return _load(MEETINGS_YAML).get("типы", [])


def validate_sources() -> list[str]:
    """Проверить архитектуру источников. Пустой список — всё в порядке."""
    problems: list[str] = []
    try:
        types = load_types()
        adapters = load_adapters()
        meetings = load_meeting_types()
    except Exception as exc:  # noqa: BLE001
        return [f"архитектура источников не читается: {exc}"]

    if not types:
        problems.append("нет типов источников")
    seen = set()
    for t in types:
        for f in ("код", "название", "канал", "инструкция"):
            if not t.get(f):
                problems.append(f"тип {t.get('код', '?')}: пустое поле «{f}»")
        if t.get("код") in seen:
            problems.append(f"дубль кода: {t.get('код')}")
        seen.add(t.get("код"))
    if not adapters:
        problems.append("нет адаптеров форматов")
    if not meetings:
        problems.append("нет типов встреч")
    return problems


def render_html() -> str:
    """Внутренний HTML раздела «Источники» для окна."""
    from capabilities.extract import convert
    types = load_types()
    meetings = load_meeting_types()
    parts: list[str] = [
        '<p class="muted">Источники — «бронза», сырьё для всей памяти. Единый канал приёма '
        '<code>opp ingest</code> уже работает (документы → markdown-узлы + реестр-индекс). '
        'Записи встреч, извлечение из базы и профили — следующие шаги (см. ниже).</p>'
    ]

    parts.append('<h2 class="band">Типы источников</h2>')
    parts.append('<div class="tablewrap"><table class="fw"><thead><tr>'
                 '<th>Код</th><th>Что это</th><th>Канал</th><th>Инструменты</th><th>Инструкция</th>'
                 '</tr></thead><tbody>')
    for t in types:
        parts.append(
            "<tr>"
            f'<td><code>{html.escape(t.get("код", ""))}</code></td>'
            f'<td>{html.escape(t.get("название", ""))}</td>'
            f'<td>{html.escape(t.get("канал", ""))}</td>'
            f'<td>{html.escape(t.get("инструменты", ""))}</td>'
            f'<td>{html.escape(t.get("инструкция", ""))}</td>'
            "</tr>"
        )
    parts.append('</tbody></table></div>')

    parts.append('<h2 class="band">Адаптеры форматов (статус на этой машине)</h2>')
    parts.append('<div class="tablewrap"><table class="fw"><thead><tr>'
                 '<th>Группа</th><th>Форматы</th><th>Статус</th></tr></thead><tbody>')
    for a in convert.adapter_status():
        st = a.get("статус", "")
        pill = "st-готова" if "работает" in st else "st-план"
        parts.append(
            "<tr>"
            f'<td>{html.escape(a.get("группа", ""))}</td>'
            f'<td>{html.escape(a.get("форматы", ""))}</td>'
            f'<td><span class="st {pill}">{html.escape(st)}</span></td>'
            "</tr>"
        )
    parts.append('</tbody></table></div>')

    parts.append('<h2 class="band">Типы встреч</h2>')
    parts.append('<div class="tablewrap"><table class="fw"><thead><tr>'
                 '<th>Тип</th><th>Фокус</th></tr></thead><tbody>')
    for m in meetings:
        parts.append(
            "<tr>"
            f'<td>{html.escape(m.get("тип", ""))}</td>'
            f'<td>{html.escape(m.get("фокус", ""))}</td>'
            "</tr>"
        )
    parts.append('</tbody></table></div>')

    done_items, ahead_items = plan_items()
    parts.append('<h2 class="band">Готово (из плана, комп. 02)</h2>')
    parts.append('<ul>')
    for item in done_items:
        parts.append(f'<li><span class="st st-готова">готово</span> {html.escape(item)}</li>')
    parts.append('</ul>')

    if ahead_items:
        parts.append('<h2 class="band">В плане сборки (дальше)</h2>')
        parts.append('<ul>')
        for item in ahead_items:
            parts.append(f'<li><span class="st st-план">план</span> {html.escape(item)}</li>')
        parts.append('</ul>')

    return "\n".join(parts)
