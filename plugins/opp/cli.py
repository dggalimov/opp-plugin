#!/usr/bin/env python3
"""Единая команда продукта OPP.

Подкоманды:
  verify      — самопроверка (12 блоков: компиляция, тесты, структурный контроль, целостность памяти,
                каркас, тема, реестр БЗ, источники, управляющий каталог, схема таблиц, отчуждаемость,
                выходные документы);
  ui          — открыть локальное окно в браузере;
  lint        — проверить рабочее пространство контролёром целостности;
  framework   — перегенерировать описание каркаса из данных;
  deploy      — развернуть рабочую папку проекта;
  status      — сводка управляющего каталога;
  ingest      — принять источники в проект (бронза);
  extract     — задание на извлечение строк таблицы из сырья проекта;
  triangulate — сверка источников/уровней → задание на синтез;
  prove       — отчёт по доказательствам ущерба: гейт ОБЭ + воспроизводимость EFF;
  requirements — отчёт по требованиям и покрытию проблем (TB);
  solutions   — отчёт по решениям (SOL) и покрытию требований;
  tobe        — отчёт по целевой картине по уровням (TLM, вычисляемая проекция из SOL);
  roadmap     — отчёт по дорожной карте (RM): наполнение волн и очерёдность;
  render      — собрать документ (md, опц. docx) из памяти проекта по конфигу;
  split       — вернуть правки согласованного документа обратно в память проекта.
"""

from __future__ import annotations
import argparse
import compileall
import io
import py_compile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from linter.structure import check_structure
from linter.run import lint_workspace
from reference.framework import validate_framework, write_markdown
from reference.theme import validate_theme, load_theme, DEFAULT_THEME
from knowledge.registry import validate_registry, counts as kb_counts
from capabilities.extract.sources import validate_sources
from schema.lint import lint_schema
from schema.model import load_schema
try:
    import plan  # dev-инструмент (управляющий каталог продукта); в поставке плагина отсутствует
except ModuleNotFoundError:
    plan = None

EMPTY_WS = ROOT / "examples" / "пустой-проект"
_COMPILE_TARGETS = ["linter", "interface", "reference", "capabilities", "knowledge",
                    "schema", "synthesis", "plan.py", "tests", "cli.py"]


def run_all_checks(root: Path) -> tuple[bool, list[str]]:
    """Прогнать все проверки. Возвращает (зелёно?, строки отчёта)."""
    root = Path(root)
    lines: list[str] = []
    ok = True

    # 1) Компиляция Python (синтаксис) — только наш код, без .venv
    compiled = True
    for target in _COMPILE_TARGETS:
        path = root / target
        if path.is_dir():
            if not compileall.compile_dir(str(path), quiet=1):
                compiled = False
        elif path.is_file():
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError:
                compiled = False
    lines.append("✓ Компиляция Python: без ошибок" if compiled
                 else "✗ Компиляция Python: есть синтаксические ошибки")
    ok = ok and compiled

    # 2) Тесты
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    if result.wasSuccessful():
        lines.append(f"✓ Тесты: пройдены ({result.testsRun})")
    else:
        ok = False
        lines.append(f"✗ Тесты: провал ({len(result.failures)} несоответствий, "
                     f"{len(result.errors)} сбоев)")

    # 3) Структурный контроль (нет устаревших шапок)
    sv = check_structure(root)
    if not sv:
        lines.append("✓ Структурный контроль: устаревших шапок нет")
    else:
        ok = False
        lines.append(f"✗ Структурный контроль: {len(sv)} нарушений")
        lines.extend(f"    {v}" for v in sv)

    # 4) Контролёр целостности памяти: уникальность кодов + замкнутость (cap-t-closure), на пустом проекте
    mv = lint_workspace(EMPTY_WS)
    if not mv:
        lines.append("✓ Контролёр целостности памяти (уникальность + замкнутость): без замечаний")
    else:
        ok = False
        lines.append(f"✗ Контролёр целостности: {len(mv)} нарушений")
        lines.extend(f"    {v}" for v in mv)

    # 5) Каркас (11 уровней)
    fw_problems = validate_framework()
    if not fw_problems:
        lines.append("✓ Каркас: 11 уровней, поля заполнены")
    else:
        ok = False
        lines.append(f"✗ Каркас: {len(fw_problems)} замечаний")
        lines.extend(f"    {p}" for p in fw_problems)

    # 6) Тема оформления по умолчанию
    try:
        theme_problems = validate_theme(load_theme(DEFAULT_THEME))
    except Exception as exc:  # noqa: BLE001
        theme_problems = [f"тема не читается: {exc}"]
    if not theme_problems:
        lines.append("✓ Тема оформления по умолчанию: валидна")
    else:
        ok = False
        lines.append(f"✗ Тема оформления: {len(theme_problems)} замечаний")
        lines.extend(f"    {p}" for p in theme_problems)

    # 7) Реестр баз знаний
    kb_problems = validate_registry()
    if not kb_problems:
        try:
            total = kb_counts()[1]
        except Exception:  # noqa: BLE001
            total = "?"
        lines.append(f"✓ Реестр БЗ: {total} баз, классификация в порядке")
    else:
        ok = False
        lines.append(f"✗ Реестр БЗ: {len(kb_problems)} замечаний")
        lines.extend(f"    {p}" for p in kb_problems)

    # 8) Архитектура источников
    src_problems = validate_sources()
    if not src_problems:
        lines.append("✓ Источники: архитектура зафиксирована")
    else:
        ok = False
        lines.append(f"✗ Источники: {len(src_problems)} замечаний")
        lines.extend(f"    {p}" for p in src_problems)

    # 9) Управляющий каталог (план + компоненты + стыки)
    plan_problems = plan.validate_plan()
    if not plan_problems:
        lines.append("✓ Управляющий каталог: целостен")
    else:
        ok = False
        lines.append(f"✗ Управляющий каталог: {len(plan_problems)} замечаний")
        lines.extend(f"    {p}" for p in plan_problems)

    # 10) Схема таблиц фактов (контракт silver): линтер контракта + якоря «где» из плана
    sc_problems = lint_schema()
    if not sc_problems:
        try:
            codes = set(load_schema().tables)
            sc_problems = plan.anchor_problems(codes)
            n = len(codes)
        except Exception:  # noqa: BLE001
            n = "?"
    if not sc_problems:
        lines.append(f"✓ Схема таблиц фактов: {n} таблиц, контракт валиден, якоря плана сходятся")
    else:
        ok = False
        lines.append(f"✗ Схема таблиц фактов: {len(sc_problems)} замечаний")
        lines.extend(f"    {v}" for v in sc_problems)

    # 11) Отчуждаемость (R17): фактические импорты ⊆ объявленным стыкам, код локализован по «где»
    mod_problems = plan.check_modularity(root)
    if not mod_problems:
        lines.append("✓ Отчуждаемость: импорты соответствуют объявленным стыкам, код локализован")
    else:
        ok = False
        lines.append(f"✗ Отчуждаемость: {len(mod_problems)} нарушений")
        lines.extend(f"    {p}" for p in mod_problems)

    # 12) Выходные документы (cap-render, doc-materials): конфиги секций ⊆ проекция контракта
    from capabilities.render.engine import load_config, sections_within_projection
    doc_problems: list = []
    documents_dir = root / "documents"
    if documents_dir.is_dir():
        try:
            doc_schema = load_schema()
        except Exception as exc:  # noqa: BLE001
            doc_schema = None
            doc_problems.append(f"схема не читается: {exc}")
        if doc_schema is not None:
            for doc_dir in sorted(p for p in documents_dir.iterdir() if p.is_dir()):
                try:
                    cfg = load_config(doc_dir.name, documents_dir)
                    doc_problems.extend(sections_within_projection(cfg, doc_schema))
                except Exception as exc:  # noqa: BLE001
                    doc_problems.append(f"{doc_dir.name}: конфиг не читается: {exc}")
    if not doc_problems:
        lines.append("✓ Выходные документы: конфиги секций согласованы с проекцией контракта")
    else:
        ok = False
        lines.append(f"✗ Выходные документы: {len(doc_problems)} замечаний")
        lines.extend(f"    {p}" for p in doc_problems)

    return ok, lines


def cmd_verify(args) -> int:
    if plan is None:
        print("Команда «verify» — самопроверка продукта при разработке; в поставке плагина недоступна (нет plan.py).")
        return 0
    ok, lines = run_all_checks(ROOT)
    print("\n".join(lines))
    print()
    print("РЕЗУЛЬТАТ: ЗЕЛЁНО ✓" if ok else "РЕЗУЛЬТАТ: КРАСНО ✗")
    return 0 if ok else 1


def cmd_ui(args) -> int:
    from interface.server import serve
    if args.path:
        target = Path(args.path).resolve()
    else:
        target = (ROOT / "examples" / "демо-проект").resolve()
    if not target.is_dir():
        print(f"Папка проекта не найдена: {target}")
        return 1
    serve(target, port=args.port)
    return 0


def cmd_lint(args) -> int:
    violations = lint_workspace(args.workspace)
    if not violations:
        print("✓ Без замечаний")
        return 0
    for v in violations:
        print(v)
    return 1


def cmd_framework(args) -> int:
    problems = validate_framework()
    if problems:
        for p in problems:
            print("ОШИБКА:", p)
        return 1
    path = write_markdown()
    print(f"Описание каркаса обновлено: {path}")
    return 0


def cmd_deploy(args) -> int:
    from capabilities.deploy import deploy_workspace
    channels = [c.strip() for c in args.channels.split(",")] if args.channels else None
    created = deploy_workspace(args.folder, channels=channels)
    print(f"Развёрнуто: {args.folder}")
    print(f"Создано элементов: {len(created)} (повтор не затирает заполненное)")
    return 0


def cmd_status(args) -> int:
    if plan is None:
        print("Команда «status» — сводка плана разработки продукта; в поставке плагина недоступна (нет plan.py).")
        return 0
    print(plan.status_text())
    return 0


def cmd_ingest(args) -> int:
    from capabilities.extract.ingest import ingest
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    try:
        result = ingest(args.source, ws)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    created, skipped, updated = result["создано"], result["пропущено"], result["обновления"]
    ok = sum(1 for c in created if c["readable"])
    skipped_ids = ", ".join(s["узел"] for s in skipped)
    tail = f" ({skipped_ids})" if skipped_ids else ""
    print(f"Принято новых: {len(created)} (распознано: {ok}, нечитаемых: {len(created) - ok}); "
          f"уже были: {len(skipped)}{tail}; обновлений: {len(updated)}")
    for c in created:
        flag = "✓" if c["readable"] else "✗"
        note = "" if c["readable"] else f"  — {c['note']}"
        print(f"  {flag} {c['code']}  {c['file'].name}{note}")
    for u in updated:
        print(f"  ~ обновление: {u['прежний']} → {u['новый']}  ({u['файл']})")
    print(f"Реестр: {ws / 'Источники' / 'реестр.md'}")
    return 0


def cmd_extract(args) -> int:
    import json
    from linter.model import MemoryLoadError
    from schema.extract import fill_request
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    try:
        req = fill_request(args.table, ws)
    except KeyError as exc:
        print(str(exc))
        return 1
    except MemoryLoadError as exc:
        print(f"Память проекта не читается: {exc}")
        return 1
    print(json.dumps(req, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_triangulate(args) -> int:
    import json
    from linter.model import MemoryLoadError
    from synthesis.triangulate import triangulate_request
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    try:
        req = triangulate_request(ws)
    except MemoryLoadError as exc:
        print(f"Память проекта не читается: {exc}")
        return 1
    print(json.dumps(req, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_prove(args) -> int:
    import json
    from linter.model import MemoryLoadError
    from synthesis.prove import prove_report
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    try:
        rep = prove_report(ws)
    except MemoryLoadError as exc:
        print(f"Память проекта не читается: {exc}")
        return 1
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_requirements(args) -> int:
    import json
    from linter.model import MemoryLoadError
    from synthesis.requirements import requirements_report
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    try:
        rep = requirements_report(ws)
    except MemoryLoadError as exc:
        print(f"Память проекта не читается: {exc}")
        return 1
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_solutions(args) -> int:
    import json
    from linter.model import MemoryLoadError
    from synthesis.solutions import solutions_report
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    try:
        rep = solutions_report(ws)
    except MemoryLoadError as exc:
        print(f"Память проекта не читается: {exc}")
        return 1
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_tobe(args) -> int:
    import json
    from linter.model import MemoryLoadError
    from synthesis.tobe import tobe_report
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    try:
        rep = tobe_report(ws)
    except MemoryLoadError as exc:
        print(f"Память проекта не читается: {exc}")
        return 1
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_roadmap(args) -> int:
    import json
    from linter.model import MemoryLoadError
    from synthesis.roadmap import roadmap_report
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    try:
        rep = roadmap_report(ws)
    except MemoryLoadError as exc:
        print(f"Память проекта не читается: {exc}")
        return 1
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_render(args) -> int:
    from capabilities.render.engine import render_markdown, load_config, RenderError
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1

    # параметры рендера: плейсхолдеры «{источник}»/«{кадры}»/«{встреча}» в конфиге секций
    # (спека 06-b/06-e); «--встреча» — свой параметр «Повестки встречи» (встреча ещё не проведена,
    # источника SRC у неё нет)
    params = {}
    if args.источник:
        params["источник"] = args.источник
    if args.кадры:
        params["кадры"] = args.кадры
    if args.встреча:
        params["встреча"] = args.встреча

    try:
        md = render_markdown(args.document, ws, params=params)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    except RenderError as exc:
        print(str(exc))
        return 1

    out_dir = ws / "Документы"
    out_dir.mkdir(parents=True, exist_ok=True)
    # параметризованный рендер — свой файл на значение (протоколы/повестки встреч не затирают друг друга)
    suffix = "".join(f"-{params[p]}" for p in ("источник", "встреча") if params.get(p))
    md_path = out_dir / f"{args.document}{suffix}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"Документ собран: {md_path}")

    if args.docx:
        from capabilities.render.docx import render_docx
        # тот же эффективный конфиг, что и у md выше (проектный шаблон, если есть, — спека 06-f):
        # без этого проектный шаблон менял бы заголовок md, а docx-титул расходился бы с ним
        cfg = load_config(args.document, workspace=ws)
        title = (cfg.get("документ") or {}).get("название", args.document)
        docx_path = render_docx(
            md, out_dir / f"{args.document}{suffix}.docx", project=str(ws), document_title=title,
            titul_client=args.титул_клиент, titul_date=args.титул_дата)
        print(f"Docx собран: {docx_path}")
    return 0


def cmd_split(args) -> int:
    from capabilities.render.split import apply_split
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    edited = Path(args.edited_file)
    if not edited.is_file():
        print(f"Файл не найден: {edited}")
        return 1
    problems = apply_split(args.document, edited, ws)
    if not problems:
        print("Правки применены, предупреждений нет.")
        return 0
    for p in problems:
        print(p)
    return 0 if all(getattr(p, "severity", "ERROR") == "WARN" for p in problems) else 1


def cmd_export(args) -> int:
    from capabilities.export.xlsx import export_workbook
    ws = Path(args.into).resolve()
    if not ws.is_dir():
        print(f"Папка проекта не найдена: {ws}")
        return 1
    out_path = export_workbook(ws)
    print(f"Книга собрана: {out_path}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="opp", description="OPP — единая команда продукта")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="самопроверка")
    p_verify.set_defaults(func=cmd_verify)

    p_ui = sub.add_parser("ui", help="открыть окно проекта в браузере")
    p_ui.add_argument("path", nargs="?", help="папка проекта (по умолчанию — демонстрационный проект)")
    p_ui.add_argument("--port", type=int, default=8765, help="порт (по умолчанию 8765)")
    p_ui.set_defaults(func=cmd_ui)

    p_lint = sub.add_parser("lint", help="проверить рабочее пространство")
    p_lint.add_argument("workspace", help="путь к рабочему пространству")
    p_lint.set_defaults(func=cmd_lint)

    p_fw = sub.add_parser("framework", help="перегенерировать описание каркаса из данных")
    p_fw.set_defaults(func=cmd_framework)

    p_deploy = sub.add_parser("deploy", help="развернуть рабочую папку проекта")
    p_deploy.add_argument("folder", help="папка проекта (создастся, если нет)")
    p_deploy.add_argument("--channels", default=None,
                          help="каналы через запятую: документы,база данных,интервью")
    p_deploy.set_defaults(func=cmd_deploy)

    p_status = sub.add_parser("status", help="сводка управляющего каталога (план/компоненты/стыки)")
    p_status.set_defaults(func=cmd_status)

    p_ingest = sub.add_parser("ingest", help="принять источники в проект (бронза)")
    p_ingest.add_argument("source", help="файл или папка с входными материалами")
    p_ingest.add_argument("--into", required=True, help="папка проекта")
    p_ingest.set_defaults(func=cmd_ingest)

    p_extract = sub.add_parser("extract", help="задание на извлечение строк таблицы из сырья проекта")
    p_extract.add_argument("table", help="код таблицы (REP, PRB, …)")
    p_extract.add_argument("--into", required=True, help="папка проекта")
    p_extract.set_defaults(func=cmd_extract)

    p_tri = sub.add_parser("triangulate", help="сверка источников/уровней → задание на синтез")
    p_tri.add_argument("--into", required=True, help="папка проекта")
    p_tri.set_defaults(func=cmd_triangulate)

    p_prove = sub.add_parser("prove", help="отчёт по доказательствам ущерба: гейт ОБЭ + воспроизводимость EFF")
    p_prove.add_argument("--into", required=True, help="папка проекта")
    p_prove.set_defaults(func=cmd_prove)

    p_req = sub.add_parser("requirements", help="отчёт по требованиям и покрытию проблем (TB)")
    p_req.add_argument("--into", required=True, help="папка проекта")
    p_req.set_defaults(func=cmd_requirements)

    p_sol = sub.add_parser("solutions", help="отчёт по решениям (SOL) и покрытию требований")
    p_sol.add_argument("--into", required=True, help="папка проекта")
    p_sol.set_defaults(func=cmd_solutions)

    p_tobe = sub.add_parser("tobe", help="отчёт по целевой картине по уровням (TLM, вычисляемая проекция)")
    p_tobe.add_argument("--into", required=True, help="папка проекта")
    p_tobe.set_defaults(func=cmd_tobe)

    p_rm = sub.add_parser("roadmap", help="отчёт по дорожной карте (RM): наполнение волн и очерёдность")
    p_rm.add_argument("--into", required=True, help="папка проекта")
    p_rm.set_defaults(func=cmd_roadmap)

    p_render = sub.add_parser("render", help="собрать документ из памяти проекта по конфигу (документ → md, опц. docx)")
    p_render.add_argument("document", help="id документа (папка в documents/, напр. materials)")
    p_render.add_argument("--into", required=True, help="папка проекта")
    p_render.add_argument("--источник", default=None, help="код источника — параметр фильтров секций документа (напр. протокол встречи)")
    p_render.add_argument("--кадры", default=None, help="относительный (от --into) путь к папке с кадрами демонстрации — параметр секции «кадры»")
    p_render.add_argument("--встреча", default=None, help="код встречи (MTG) — параметр фильтров документа «Повестка встречи»")
    p_render.add_argument("--docx", action="store_true", help="дополнительно собрать docx-представление")
    p_render.add_argument("--титул-клиент", default=None, help="докс: имя клиента на титульном листе (опционально, влияет только на docx)")
    p_render.add_argument("--титул-дата", default=None, help="докс: дата на титульном листе (опционально, влияет только на docx)")
    p_render.set_defaults(func=cmd_render)

    p_split = sub.add_parser("split", help="вернуть правки согласованного документа обратно в память проекта")
    p_split.add_argument("document", help="id документа (папка в documents/, напр. materials)")
    p_split.add_argument("edited_file", help="путь к правленому md-файлу")
    p_split.add_argument("--into", required=True, help="папка проекта")
    p_split.set_defaults(func=cmd_split)

    p_export = sub.add_parser("export", help="экспорт памяти проекта в xlsx (представление, руками не правится)")
    p_export.add_argument("--into", required=True, help="папка проекта")
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
