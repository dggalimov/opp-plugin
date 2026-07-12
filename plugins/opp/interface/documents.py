"""Раздел окна «Документы» (cap-render): список документов продукта, предпросмотр md→html,
кнопки «Пересобрать» (вызывает `capabilities.render.engine.render_markdown` и перезаписывает
md-канон `<проект>/Проектная память/Документы/<id>.md`, техслой) и «Собрать docx»
(`capabilities.render.docx.render_docx` поверх только что пересобранного md, в клиентский
`<проект>/Документы/` под человеческим именем по формуле конфига, если она задана — спека 08 §8;
та же точка рендера, что и `cli.py::cmd_render`, синхронно).

MVP-граница (спека 05-a-render): показ и пересборка md; docx — отдельной кнопкой, только запись
файла (открытие — средствами ОС пользователя, не браузера). Правка прозы документа с возвратом в
память — вне границы (память ≠ проза; обратный ход — только `./opp split` по согласованным ячейкам).
Оболочку (_wrap/_nav/тема) даёт `interface/server.py`, HTML-предпросмотр — `interface/md.py`.
"""

from __future__ import annotations
import html
from pathlib import Path

from capabilities.paths import docs_tech_dir
from capabilities.render.engine import DOCUMENTS_DIR, RenderError, load_config, render_markdown, resolve_output_name
from interface import md as md_render


def _list_documents() -> list[tuple[str, dict]]:
    """Документы продукта: id (папка в documents/) → конфиг. Устойчиво к битому конфигу (пропуск)."""
    out = []
    if not DOCUMENTS_DIR.is_dir():
        return out
    for d in sorted(p for p in DOCUMENTS_DIR.iterdir() if p.is_dir()):
        try:
            cfg = load_config(d.name)
        except Exception:  # noqa: BLE001
            continue
        out.append((d.name, cfg))
    return out


def _overview_html() -> str:
    docs = _list_documents()
    parts = ['<h1>Документы</h1>',
             '<p class="muted">Документы продукта — детерминированная проекция памяти проекта '
             '(<code>./opp render</code>). Правки согласованных ячеек возвращаются '
             'командой <code>./opp split</code>.</p>']
    if not docs:
        parts.append('<p class="muted">Конфигов документов не найдено.</p>')
        return "".join(parts)
    parts.append('<ul class="listing">')
    for doc_id, cfg in docs:
        title = (cfg.get("документ") or {}).get("название", doc_id)
        parts.append(f'<li><a href="/documents?doc={html.escape(doc_id)}">'
                     f'{html.escape(title)} <code>{html.escape(doc_id)}</code></a></li>')
    parts.append('</ul>')
    return "".join(parts)


_REBUILD_WIDGET = """<div class="editbar">
  <button id="rebuild" class="btn">Пересобрать</button>
  <button id="build-docx" class="btn">Собрать docx</button>
  <span id="status" class="muted"></span>
</div>
<script>
(function(){
  var st=document.getElementById('status');
  function run(btn, fileId, doneMsg){
    st.textContent=doneMsg; btn.disabled=true;
    fetch('/save',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'id='+encodeURIComponent(fileId)+'&content='}).then(function(r){return r.json();})
      .then(function(d){ st.textContent=d.message; btn.disabled=false; if(d.ok && fileId.indexOf('::docx')<0){ setTimeout(function(){location.reload();},400);} })
      .catch(function(e){ st.textContent='Ошибка: '+e; btn.disabled=false; });
  }
  document.getElementById('rebuild').addEventListener('click', function(){
    run(this, 'render:__DOC__', 'Пересобираю…');
  });
  document.getElementById('build-docx').addEventListener('click', function(){
    run(this, 'render:__DOC__::docx', 'Собираю docx…');
  });
})();
</script>"""


def _document_page(doc_id: str, project) -> str:
    try:
        cfg = load_config(doc_id, workspace=project)   # проектный шаблон (спека 06-f), если есть
    except FileNotFoundError:
        return ('<h1>Документы</h1><p class="muted">Документ не найден.</p>'
                '<p><a href="/documents">← к списку</a></p>')
    title = (cfg.get("документ") or {}).get("название", doc_id)
    parts = [f'<nav class="crumbs"><a href="/documents">Документы</a> / <span>{html.escape(title)}</span></nav>',
             f'<h1>{html.escape(title)} <code>{html.escape(doc_id)}</code></h1>']

    if project is None:
        parts.append('<p class="muted">Проект не открыт — предпросмотр недоступен.</p>')
        return "".join(parts)

    try:
        rendered_md = render_markdown(doc_id, project)
    except Exception as exc:  # noqa: BLE001
        parts.append(f'<p class="muted">Не удалось собрать документ: {html.escape(str(exc))}</p>')
        return "".join(parts)

    parts.append(_REBUILD_WIDGET.replace("__DOC__", html.escape(doc_id)))
    parts.append(f'<div class="md preview">{md_render.md_to_html(rendered_md)}</div>')
    return "".join(parts)


def render(query: dict, project) -> str:
    """Точка входа раздела: ?doc=<id> → предпросмотр документа, иначе список документов."""
    doc_id = (query.get("doc", [None]) or [None])[0]
    return _document_page(doc_id, project) if doc_id else _overview_html()


_DOCX_SUFFIX = "::docx"   # id.py «render:<doc>::docx» — та же кнопка «Собрать docx», обещанная шапкой


def _save(doc_id: str, _content: str, project):
    """POST /save handler (префикс render:): пересобрать md документа и перезаписать в проекте.

    Id с суффиксом «::docx» — кнопка «Собрать docx»: md пересобирается тем же путём (техслой,
    «Проектная память/Документы»), затем поверх него — docx-представление в клиентский
    «Документы» (тема — как в cli.py::cmd_render, без титула клиента/даты — их в окне не ввести;
    заголовок docx берётся из уже загруженного эффективного конфига, тем самым согласован с
    проектным шаблоном, если он есть; имя файла — `resolve_output_name`, спека 08 §8)."""
    if project is None:
        return False, "проект не открыт"
    want_docx = doc_id.endswith(_DOCX_SUFFIX)
    if want_docx:
        doc_id = doc_id[: -len(_DOCX_SUFFIX)]
    try:
        rendered_md = render_markdown(doc_id, project)
    except Exception as exc:  # noqa: BLE001
        return False, f"не собран: {exc}"
    tech_dir = docs_tech_dir(project)
    tech_dir.mkdir(parents=True, exist_ok=True)
    (tech_dir / f"{doc_id}.md").write_text(rendered_md, encoding="utf-8")
    if not want_docx:
        return True, "Пересобрано ✓"
    from capabilities.render.docx import render_docx
    cfg = load_config(doc_id, workspace=project)
    document_cfg = cfg.get("документ") or {}
    title = document_cfg.get("название", doc_id)
    # рабочие/рассылочные документы («документ.титул: нет», спека 08 §8) — без титульного листа
    # и «Содержания»; по умолчанию (ключ не задан) титул остаётся, как в cli.py::cmd_render
    титул = document_cfg.get("титул") != "нет"
    try:
        client_name = resolve_output_name(doc_id, project)
    except RenderError as exc:
        return False, f"имя файла: {exc}"
    out_dir = Path(project) / "Документы"
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_name = f"{client_name}.docx" if client_name else f"{doc_id}.docx"
    try:
        docx_path = render_docx(rendered_md, out_dir / docx_name,
                                 project=str(project), document_title=title, титул=титул)
    except Exception as exc:  # noqa: BLE001
        return False, f"docx не собран: {exc}"
    return True, f"Docx собран: {docx_path.name} ✓"


def register(register_section):
    """Саморегистрация раздела «Документы» в окне (cap-ui-decouple): окно нас не импортирует."""
    register_section("документы", "/documents", "Документы", render,
                     save_prefix="render:", save=_save)
