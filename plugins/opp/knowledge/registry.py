"""Каталог баз знаний для окна и запросов — ВИД над единым источником (plan/03.yaml).

Отдельного файла-реестра БЗ больше нет: данные живут в таблице элементов (plan/), сюда тянутся. Здесь —
представление «Базы знаний» в окне, счётчики и способы сборки (build-types.yaml).
"""

from __future__ import annotations
import html
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_TYPES_YAML = HERE / "build-types.yaml"

_REQUIRED = ("id", "название", "тип", "роль", "статус", "домен")
_ROLE_ORDER = ["навигатор", "доменная-структура", "доменная-методика", "методическая"]
_ROLE_TITLE = {
    "навигатор": "Навигатор",
    "доменная-структура": "Доменные — структура",
    "доменная-методика": "Доменные — методика",
    "методическая": "Методические / платформа",
}


def load_registry() -> dict:
    """Каталог БЗ из единого источника (plan/03.yaml) в привычной форме {типы, роли, статусы, базы}."""
    from plan import kb_elements, load_index
    return {
        "типы": ["индексная", "семантическая", "плоская", "шаблоны", "навигатор"],
        "роли": _ROLE_ORDER,
        "статусы": load_index().get("статусы", []),
        "базы": [{"id": k["id"], "название": k["название"], "тип": k["технология"], "роль": k["роль"],
                  "домен": k["домен"], "источник": k["источник"], "привязка": k["привязка"],
                  "статус": k["статус"]} for k in kb_elements()],
    }


def validate_registry(reg=None) -> list[str]:
    """Проверить реестр БЗ. Пустой список — всё в порядке."""
    problems: list[str] = []
    try:
        reg = reg if reg is not None else load_registry()
    except Exception as exc:  # noqa: BLE001
        return [f"реестр БЗ не читается: {exc}"]

    типы = set(reg.get("типы", []))
    роли = set(reg.get("роли", []))
    статусы = set(reg.get("статусы", []))
    seen: set = set()
    for b in reg.get("базы", []):
        bid = b.get("id")
        for f in _REQUIRED:
            if not b.get(f):
                problems.append(f"БЗ {bid or '?'}: пустое поле «{f}»")
        if bid in seen:
            problems.append(f"дубль id: {bid}")
        seen.add(bid)
        if b.get("тип") not in типы:
            problems.append(f"БЗ {bid}: неизвестный тип «{b.get('тип')}»")
        if b.get("роль") not in роли:
            problems.append(f"БЗ {bid}: неизвестная роль «{b.get('роль')}»")
        if b.get("статус") not in статусы:
            problems.append(f"БЗ {bid}: неизвестный статус «{b.get('статус')}»")
    return problems


def counts(reg=None):
    reg = reg if reg is not None else load_registry()
    c = Counter(b.get("статус") for b in reg.get("базы", []))
    return dict(c), len(reg.get("базы", []))


def load_build_types() -> list:
    import yaml
    return yaml.safe_load(BUILD_TYPES_YAML.read_text(encoding="utf-8")).get("типы", [])


def render_html() -> str:
    """Внутренний HTML раздела «Базы знаний» для окна."""
    reg = load_registry()
    by_status, total = counts(reg)
    badges = " · ".join(f"{s}: {n}" for s, n in by_status.items())
    parts: list[str] = [
        f'<p class="muted">Всего баз знаний: {total} ({html.escape(badges)}). '
        f'Поверхность масштабирования — собираем по одной через навык.</p>',
        '<p class="muted">Движок доступа — MCP <code>opp-knowledge</code> — '
        'разрабатывается параллельно (отдельно); здесь — каталог самих баз.</p>',
    ]

    groups: dict[str, list] = {}
    for b in reg.get("базы", []):
        groups.setdefault(b.get("роль"), []).append(b)

    for role in _ROLE_ORDER:
        items = groups.get(role, [])
        if not items:
            continue
        parts.append(f'<h2 class="band">{_ROLE_TITLE.get(role, role)} ({len(items)})</h2>')
        parts.append('<div class="tablewrap"><table class="fw"><thead><tr>'
                     '<th>id</th><th>Название</th><th>Тип</th><th>Домен</th>'
                     '<th>Источник</th><th>Привязка</th><th>Статус</th>'
                     '</tr></thead><tbody>')
        for b in items:
            st = b.get("статус", "")
            parts.append(
                "<tr>"
                f'<td><code>{html.escape(b.get("id", ""))}</code></td>'
                f'<td>{html.escape(b.get("название", ""))}</td>'
                f'<td>{html.escape(b.get("тип", ""))}</td>'
                f'<td>{html.escape(b.get("домен", ""))}</td>'
                f'<td>{html.escape(b.get("источник", ""))}</td>'
                f'<td>{html.escape(b.get("привязка", ""))}</td>'
                f'<td><span class="st st-{html.escape(st)}">{html.escape(st)}</span></td>'
                "</tr>"
            )
        parts.append('</tbody></table></div>')

    try:
        бт = load_build_types()
    except Exception:  # noqa: BLE001
        бт = []
    if бт:
        parts.append('<h2 class="band">Как собрать БЗ (по типам)</h2>')
        parts.append('<div class="tablewrap"><table class="fw"><thead><tr>'
                     '<th>Тип</th><th>Инструмент</th><th>Инструкция</th><th>Артефакт</th>'
                     '</tr></thead><tbody>')
        for t in бт:
            parts.append(
                "<tr>"
                f'<td>{html.escape(t.get("тип", ""))}</td>'
                f'<td>{html.escape(t.get("инструмент", ""))}</td>'
                f'<td>{html.escape(t.get("инструкция", ""))}</td>'
                f'<td><code>{html.escape(t.get("артефакт", ""))}</code></td>'
                "</tr>"
            )
        parts.append('</tbody></table></div>')

    return "\n".join(parts)
