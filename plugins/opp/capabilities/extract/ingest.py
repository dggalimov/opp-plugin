"""Единый канал приёма источников (бронза): классификация → конвертация → кодификация → реестр-индекс.

Каждый вход превращается в кодифицированный узел `SRC-*.md` (шапка + полный markdown + секция «Фокус»).
Ничего не теряется: нечитаемое получает узел с `readable: false` и подсказкой. Реестр материалов —
производный индекс, генерируется из шапок узлов.
"""

from __future__ import annotations
import hashlib
import re
from pathlib import Path

from capabilities import paths
from capabilities.extract import convert

_KIND_LABEL = {"SRC-MAT": "документ", "SRC-REC": "запись встречи",
               "SRC-CFG": "срез конфигурации", "SRC-DAT": "срез данных",
               "SRC-LOG": "журнал регистрации", "SRC-COM": "карточка компании",
               "SRC-WEB": "веб-источник"}
_CHANNEL = {"SRC-MAT": "Документы", "SRC-REC": "Интервью",
            "SRC-CFG": "База данных", "SRC-DAT": "База данных",
            "SRC-LOG": "База данных", "SRC-COM": "Публичные",
            "SRC-WEB": "Ссылки"}

_CLOUD_HOSTS = ("disk.yandex", "yadi.sk", "drive.google", "dropbox.com",
                "cloud.mail.ru", "onedrive", "1drv.ms")
_FILE_EXT = re.compile(r"\.(docx?|xlsx?|xlsm|xlsb|pptx?|pdf|zip|csv|tsv|json|xml|dbf|drawio|"
                       r"vsdx|mpp|mpx|mxl|mp4|mov|avi|mkv|mp3|wav|m4a|jpe?g|png)$", re.I)


def _is_cloud_file(url: str) -> bool:
    """Ссылка ведёт на файл/облако (скачать) — в отличие от обычной веб-страницы."""
    if any(h in url.lower() for h in _CLOUD_HOSTS):
        return True
    return bool(_FILE_EXT.search(url.split("?")[0]))


def classify(path) -> str:
    """Определить тип источника по содержимому/расширению (бронза: документ или запись)."""
    if Path(path).suffix.lower() in convert.MEDIA:
        return "SRC-REC"
    return "SRC-MAT"


def _next_code(workspace, kind: str) -> str:
    src = paths.sources_dir(workspace)
    n = 0
    if src.is_dir():
        for f in src.rglob(f"{kind}-*.md"):
            m = re.match(rf"{re.escape(kind)}-(\d+)", f.stem)
            if m:
                n = max(n, int(m.group(1)))
    return f"{kind}-{n + 1:03d}"


def _sha256_file(path) -> str:
    """sha256 содержимого файла (hex) — идентичность содержимого для дедупа при ingest."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_index(workspace) -> dict:
    """Индекс уже принятых узлов-источников: {хеш → id} и {origin → (id, хеш|None)}.

    Строится сканированием папки источников (paths.sources_dir) — как _next_code. Используется codify*() ДО
    конвертации/транскрибации, чтобы повторный приём не дублировал узлы и не тратил Newton.
    """
    src = paths.sources_dir(workspace)
    by_hash, by_origin = {}, {}
    if src.is_dir():
        for f in src.rglob("SRC-*.md"):
            front, _ = _parse_front(f.read_text(encoding="utf-8", errors="replace"))
            node_id = front.get("id", f.stem)
            origin = front.get("origin")
            file_hash = front.get("хеш")
            if file_hash:
                by_hash[file_hash] = node_id
            if origin:
                by_origin[origin] = (node_id, file_hash)
    return {"by_hash": by_hash, "by_origin": by_origin}


def _write_node(workspace, kind, title, origin, body, readable, extra=None, file_hash=None) -> dict:
    import yaml
    code = _next_code(workspace, kind)
    folder = paths.sources_dir(workspace) / _CHANNEL.get(kind, "Документы")
    folder.mkdir(parents=True, exist_ok=True)
    front = {"id": code, "kind": _KIND_LABEL.get(kind, kind), "title": title,
             "origin": str(origin), "readable": readable, "ключ_базы": None}
    if file_hash is not None:
        front["хеш"] = file_hash
    if extra:
        front.update(extra)
    text = ("---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + "---\n\n"
            + (body or "_Контент не извлечён_") + "\n\n## Фокус\n_(заполняется при анализе)_\n")
    out = folder / f"{code}.md"
    out.write_text(text, encoding="utf-8")
    return {"code": code, "file": out, "readable": readable}


def codify(workspace, src_path, origin=None, index=None) -> dict:
    """Превратить один файл в кодифицированный узел SRC-*. origin — что записать в происхождение
    (для скачанных из облака — исходная ссылка, а не временный путь).

    Идемпотентно: хеш содержимого файла сверяется с индексом ДО классификации/транскрибации —
    повторный медиа-файл не вызывает meetings.transcribe (Newton — платный). Совпал хеш → пропуск
    (`{"skip": True, ...}`). Хеш новый, но origin уже встречался → новый узел с пометкой
    «обновлённая версия <старый id>» (обновления не теряются молча).
    """
    origin = origin if origin is not None else src_path
    origin_str = str(origin)
    if index is None:
        index = _build_index(workspace)

    file_hash = _sha256_file(src_path)
    existing_id = index["by_hash"].get(file_hash)
    if existing_id is not None:
        return {"skip": True, "id": existing_id, "source": origin_str}

    updated_from = None
    existing_origin = index["by_origin"].get(origin_str)
    if existing_origin is not None and existing_origin[1] != file_hash:
        updated_from = existing_origin[0]

    kind = classify(src_path)
    if kind == "SRC-REC":
        from capabilities.extract import meetings
        text, readable, note = meetings.transcribe(src_path)
        extra = {"тип_встречи": meetings.detect_type(text)} if readable else {}
        body = text if readable else f"_Контент не извлечён: {note}_"
        res = _write_node(workspace, kind, Path(src_path).name, origin, body, readable, extra,
                          file_hash=file_hash)
        res["note"] = "" if readable else note
    else:
        md, readable, note = convert.to_markdown(src_path)
        body = md if readable else f"_Контент не извлечён: {note}_"
        res = _write_node(workspace, kind, Path(src_path).name, origin, body, readable,
                          file_hash=file_hash)
        res["note"] = "" if readable else note

    res["source"] = origin_str
    if updated_from is not None:
        res["updated_from"] = updated_from
        res["note"] = (res["note"] + "; " if res["note"] else "") + f"обновлённая версия {updated_from}"

    index["by_hash"][file_hash] = res["code"]
    index["by_origin"][origin_str] = (res["code"], file_hash)
    return res


def _next_base_key(workspace) -> str:
    src = paths.sources_dir(workspace)
    keys = set()
    if src.is_dir():
        for f in src.rglob("SRC-*.md"):
            front, _ = _parse_front(f.read_text(encoding="utf-8", errors="replace"))
            if front.get("ключ_базы"):
                keys.add(front["ключ_базы"])
    return f"БАЗА-{len(keys) + 1:03d}"


def codify_config(workspace, cfg_root, index=None) -> dict:
    """Кодифицировать выгрузку конфигурации 1С как SRC-CFG (с ключом базы).

    Дедуп по origin (путь к выгрузке) — папку не хешируем; повтор той же выгрузки → пропуск."""
    if index is None:
        index = _build_index(workspace)
    origin_str = str(cfg_root)
    existing = index["by_origin"].get(origin_str)
    if existing is not None:
        return {"skip": True, "id": existing[0], "source": origin_str}

    from capabilities.extract import config
    parsed = config.parse_config_dump(cfg_root)
    readable = parsed is not None
    body = config.render_markdown(parsed) if readable else "_Не удалось разобрать выгрузку конфигурации_"
    title = (parsed.get("name") if readable else None) or Path(cfg_root).name
    res = _write_node(workspace, "SRC-CFG", title, cfg_root, body, readable,
                      {"ключ_базы": _next_base_key(workspace)})
    res["note"] = "" if readable else "не разобрана конфигурация"
    res["source"] = origin_str
    index["by_origin"][origin_str] = (res["code"], None)
    return res


def codify_link(workspace, url, index=None) -> dict:
    """Кодифицировать содержимое по ссылке как SRC-WEB.

    Дедуп по origin-URL — без хеша (контент динамический); повтор той же ссылки → пропуск."""
    if index is None:
        index = _build_index(workspace)
    existing = index["by_origin"].get(url)
    if existing is not None:
        return {"skip": True, "id": existing[0], "source": url}

    md, readable, note = convert.fetch_url(url)
    body = md if readable else f"_Контент не получен: {note}_"
    res = _write_node(workspace, "SRC-WEB", url, url, body, readable)
    res["note"] = "" if readable else note
    res["source"] = url
    index["by_origin"][url] = (res["code"], None)
    return res


def codify_collected(workspace, kind, title, body, base_key=None) -> dict:
    """Записать узел, собранный навыком: срез данных (SRC-DAT), журнал (SRC-LOG), карточка (SRC-COM).

    `base_key` связывает срезы вокруг одной базы (конфигурация + данные + журнал смотрятся совместно
    при наполнении каркаса — вместе с базой знаний по типовой конфигурации).
    """
    extra = {"ключ_базы": base_key} if base_key else None
    res = _write_node(workspace, kind, title, "сбор OPP", body, True, extra)
    res["note"] = ""
    build_manifest(workspace)
    return res


def ingest(source, workspace) -> dict:
    """Принять файл, папку или ссылку. Идемпотентно: дедуп по sha256 содержимого (CFG/WEB — по
    origin), сверка ДО транскрибации/конвертации — повторный приём не тратит Newton и не дублирует
    узлы. Возвращает {"создано": [...], "пропущено": [{"файл", "узел"}...],
    "обновления": [{"файл", "прежний", "новый"}...]}; обновляет реестр-индекс."""
    index = _build_index(workspace)
    result: dict = {"создано": [], "пропущено": [], "обновления": []}

    def _handle(res: dict) -> None:
        if res.get("skip"):
            result["пропущено"].append({"файл": res["source"], "узел": res["id"]})
            return
        result["создано"].append(res)
        if res.get("updated_from"):
            result["обновления"].append({"файл": res["source"], "прежний": res["updated_from"],
                                          "новый": res["code"]})

    s = str(source)
    if s.startswith(("http://", "https://")):
        if _is_cloud_file(s):
            try:
                local = convert.download_url(s, paths.sources_dir(workspace) / "_загрузки")
                _handle(codify(workspace, local, origin=s, index=index))
            except Exception as exc:  # noqa: BLE001 — не скачалось → сохраняем как ссылку
                res = codify_link(workspace, s, index=index)
                if not res.get("skip"):
                    res["note"] = f"не скачалось ({exc}); сохранено как ссылка"
                _handle(res)
        else:
            _handle(codify_link(workspace, s, index=index))
        build_manifest(workspace)
        return result

    src_path = Path(source)
    if not src_path.exists():
        # Несуществующий путь — ошибка, а не «принято 0»: иначе no-op перезаписывает реестр
        raise FileNotFoundError(f"Источник не найден: {src_path}")
    if src_path.is_dir():
        from capabilities.extract import config
        cfg_root = config.find_config_root(src_path)
        if cfg_root is not None:
            _handle(codify_config(workspace, cfg_root, index=index))
        else:
            for f in sorted(src_path.rglob("*")):
                if f.is_file() and not f.name.startswith(".") and not f.stem.startswith("SRC-"):
                    _handle(codify(workspace, f, index=index))
    elif src_path.is_file():
        _handle(codify(workspace, src_path, index=index))

    build_manifest(workspace)
    return result


def _parse_front(text: str):
    """Разобрать YAML-шапку построчно (устойчиво к «---» внутри значений, напр. в путях)."""
    import yaml
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                try:
                    return yaml.safe_load("".join(lines[1:i])) or {}, "".join(lines[i + 1:])
                except Exception:
                    return {}, text
    return {}, text


def _summary(body: str) -> str:
    for raw in body.splitlines():
        s = raw.replace("﻿", "").strip()
        if not s or s in ("{", "}", "[", "]"):
            continue
        if s.startswith(("```", "---")):
            continue
        # причина нечитаемости (_write_node оборачивает её курсивом) — не пропускать, а показать
        if s.startswith("_") and s.endswith("_") and "Контент не извлечён" in s:
            s = s.strip("_").strip()
            return (s[:117] + "…") if len(s) > 118 else s
        s = s.strip("|").strip()  # для табличных строк убрать рамку
        if s and not s.startswith(("#", "_", "<")):
            return (s[:117] + "…") if len(s) > 118 else s
    return "—"


def build_manifest(workspace) -> Path:
    """Сгенерировать производный реестр материалов из шапок узлов."""
    src = paths.sources_dir(workspace)
    rows = []
    if src.is_dir():
        for f in sorted(src.rglob("SRC-*.md")):
            front, body = _parse_front(f.read_text(encoding="utf-8", errors="replace"))
            rows.append((front.get("id", f.stem), front.get("kind", ""), front.get("title", ""),
                         _summary(body), "да" if front.get("readable") else "нет"))

    out = ["# Реестр материалов\n",
           "> Производный индекс сырого слоя. Генерируется автоматически — руками не правят.\n",
           "| Код | Тип | Название | Краткое содержание | Читаемо |", "|---|---|---|---|---|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "\\|") for x in r) + " |")
    if not rows:
        out.append("| — | — | — | пусто | — |")

    src.mkdir(parents=True, exist_ok=True)
    path = src / "реестр.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path
