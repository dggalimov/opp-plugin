"""Разбор XML-выгрузки конфигурации 1С → инвентарь объектов (бронза, SRC-CFG).

Основной путь среза конфигурации — выгрузка в файлы XML (виден весь код). Здесь — инвентарь: какие
объекты есть и сколько. Diff с типовой и доработки — это синтез (с доменной БЗ), не здесь.
"""

from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path

# Папка типа объектов в выгрузке (англ.) → русская подпись
_TYPE_LABEL = {
    "Subsystems": "Подсистемы",
    "CommonModules": "Общие модули",
    "Roles": "Роли",
    "ExchangePlans": "Планы обмена",
    "ChartsOfAccounts": "Планы счетов",
    "ChartsOfCharacteristicTypes": "Планы видов характеристик",
    "ChartsOfCalculationTypes": "Планы видов расчёта",
    "Catalogs": "Справочники",
    "Documents": "Документы",
    "DocumentJournals": "Журналы документов",
    "Enums": "Перечисления",
    "Reports": "Отчёты",
    "DataProcessors": "Обработки",
    "InformationRegisters": "Регистры сведений",
    "AccumulationRegisters": "Регистры накопления",
    "AccountingRegisters": "Регистры бухгалтерии",
    "CalculationRegisters": "Регистры расчёта",
    "BusinessProcesses": "Бизнес-процессы",
    "Tasks": "Задачи",
}


def find_config_root(path):
    """Папка, где лежит Configuration.xml (корень выгрузки), или None."""
    p = Path(path)
    if (p / "Configuration.xml").is_file():
        return p
    for f in p.rglob("Configuration.xml"):
        return f.parent
    return None


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _config_info(xml_path: Path) -> dict:
    res: dict = {}
    try:
        for _event, el in ET.iterparse(str(xml_path)):
            t = _local(el.tag).lower()
            if t in ("name", "vendor", "version") and t not in res and (el.text or "").strip():
                res[t] = el.text.strip()
            if len(res) >= 3:
                break
    except Exception:
        pass
    return res


def parse_config_dump(path) -> dict | None:
    root = find_config_root(path)
    if root is None:
        return None
    info = _config_info(root / "Configuration.xml")
    objects: dict[str, list[str]] = {}
    for folder, label in _TYPE_LABEL.items():
        d = root / folder
        if d.is_dir():
            names = sorted(p.stem for p in d.glob("*.xml"))
            if names:
                objects[label] = names
    return {"name": info.get("name", ""), "vendor": info.get("vendor", ""),
            "version": info.get("version", ""), "objects": objects}


def render_markdown(parsed: dict) -> str:
    out = ["# Срез конфигурации\n",
           f"- Конфигурация: {parsed.get('name') or '—'}",
           f"- Поставщик: {parsed.get('vendor') or '—'}",
           f"- Версия: {parsed.get('version') or '—'}\n",
           "## Инвентарь объектов\n", "| Тип объекта | Кол-во |", "|---|---|"]
    total = 0
    for label, names in parsed["objects"].items():
        out.append(f"| {label} | {len(names)} |")
        total += len(names)
    out.append(f"| **Всего** | **{total}** |\n")
    for label, names in parsed["objects"].items():
        out.append(f"### {label} ({len(names)})")
        out.append(", ".join(names) if names else "—")
        out.append("")
    return "\n".join(out)
