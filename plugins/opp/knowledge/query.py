"""Единый интерфейс запроса к базам знаний OPP.

Операции обращаются к БЗ по `id`; технология (индексная/семантическая/плоская/шаблоны/навигатор)
спрятана за этим интерфейсом. Плоские БЗ, шаблоны и навигатор читаются напрямую из
`knowledge/bases/<id>/`. Тяжёлые бэкенды (индексная/семантическая) обслуживает MCP-сервер
`opp-knowledge` (Фазы 1–2 приняты; здесь — честная переадресация, маршрутизации нет намеренно).

Доказуемость: ответ несёт «статус» элемента; непринятая БЗ (статус вне «готово»/«проверка»)
не выдаётся как знание — «найдено: False» с пояснением (заготовка ≠ знание).

Это внутрипродуктовый читатель (окно, ./opp verify) без внешних зависимостей. Агент-контрактный
единый интерфейс на все типы — MCP `opp-knowledge`; оба читают одни артефакты `bases/`, дублирования
правды нет (см. decisions/0015).
"""

from __future__ import annotations
from pathlib import Path

from knowledge.registry import load_registry

HERE = Path(__file__).resolve().parent
BASES = HERE / "bases"

_DIRECT = {"плоская", "шаблоны", "навигатор"}   # читаются напрямую из поставки
_VIA_MCP = {"индексная", "семантическая"}       # обслуживает MCP opp-knowledge


class KBNotFound(Exception):
    pass


def _kb(kb_id: str) -> dict:
    for b in load_registry().get("базы", []):
        if b.get("id") == kb_id:
            return b
    raise KBNotFound(kb_id)


def list_kb(роль=None, тип=None, статус=None) -> list[dict]:
    out = []
    for b in load_registry().get("базы", []):
        if роль and b.get("роль") != роль:
            continue
        if тип and b.get("тип") != тип:
            continue
        if статус and b.get("статус") != статус:
            continue
        out.append(b)
    return out


# Статусы, при которых контент БЗ — принятое знание, а не заготовка.
_KNOWLEDGE = {"готово", "проверка"}


def query(kb_id: str, text: str = "", top_k: int = 5) -> dict:
    """Единый запрос к БЗ по id. Возвращает результат либо честную заглушку."""
    kb = _kb(kb_id)
    тип, статус = kb.get("тип"), kb.get("статус", "")
    if тип in _DIRECT:
        base = BASES / kb_id
        files = sorted(base.glob("*.md")) if base.is_dir() else []
        if files and статус not in _KNOWLEDGE:
            return {"kb": kb_id, "тип": тип, "статус": статус, "найдено": False,
                    "сообщение": f"заготовка: БЗ в статусе «{статус}» — не принятое знание "
                                 f"(доказуемость); файлы существуют, но не выдаются"}
        if files:
            content = "\n\n".join(f.read_text(encoding="utf-8") for f in files)
            return {"kb": kb_id, "тип": тип, "статус": статус, "найдено": True, "контент": content}
        return {"kb": kb_id, "тип": тип, "статус": статус, "найдено": False,
                "сообщение": "БЗ не собрана (нет knowledge/bases/<id>/)"}
    if тип in _VIA_MCP:
        return {"kb": kb_id, "тип": тип, "статус": статус, "найдено": False,
                "сообщение": "Запрос обслуживает MCP opp-knowledge (kb_query; Фазы 1–2 приняты). "
                             "См. knowledge/mcp-development-plan.md"}
    return {"kb": kb_id, "тип": тип, "статус": статус, "найдено": False,
            "сообщение": f"неизвестный тип: {тип}"}
