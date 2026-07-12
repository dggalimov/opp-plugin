"""Профили сбора данных по конфигурациям: что тянуть из базы для аудита (осмысленно, не дамп).

Хранение в двух местах:
- **Коробка** — `capabilities/extract/profiles/<config>.yaml` (предзаполнено по известным конфигурациям).
- **Проект** — `<проект>/Проектная память/Источники/профили/<config>.yaml` (переопределение,
  правится в окне; ЗР-0027 п.7 — техслой источников целиком под «Проектной памятью»).

Действует переопределение проекта, иначе коробка. Привязка к доменной БЗ структуры — поле `база_знаний`.
"""

from __future__ import annotations
from pathlib import Path

from capabilities import paths

HERE = Path(__file__).resolve().parent
PROFILES_DIR = HERE / "profiles"
PROJECT_SUBDIR_NAME = "профили"


def box_path(config_id: str) -> Path:
    return PROFILES_DIR / f"{config_id}.yaml"


def project_path(project, config_id: str) -> Path:
    return paths.sources_dir(project) / PROJECT_SUBDIR_NAME / f"{config_id}.yaml"


def list_profiles() -> list[str]:
    """Идентификаторы профилей коробки (без шаблона)."""
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def load_profile(config_id: str, project=None):
    """Профиль как данные: переопределение проекта, иначе коробка. None — если нет."""
    import yaml
    if project:
        pp = project_path(project, config_id)
        if pp.is_file():
            return yaml.safe_load(pp.read_text(encoding="utf-8"))
    box = box_path(config_id)
    return yaml.safe_load(box.read_text(encoding="utf-8")) if box.is_file() else None


def profile_source(config_id: str, project=None) -> str:
    """Откуда берётся профиль: «проект» (переопределён), «коробка» или «нет»."""
    if project and project_path(project, config_id).is_file():
        return "проект"
    return "коробка" if box_path(config_id).is_file() else "нет"


def read_profile_text(config_id: str, project=None) -> str:
    """Текст профиля для правки: переопределение проекта, иначе коробка."""
    if project:
        pp = project_path(project, config_id)
        if pp.is_file():
            return pp.read_text(encoding="utf-8")
    box = box_path(config_id)
    return box.read_text(encoding="utf-8") if box.is_file() else ""


def save_profile_text(config_id: str, text: str, project) -> Path:
    """Сохранить правку профиля как переопределение проекта (коробку не трогаем)."""
    pp = project_path(project, config_id)
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(text, encoding="utf-8")
    return pp
