"""Локальное окно в браузере — окно проекта для пользователя.

Разделы (10): «План», «Проект» (папка проекта), «Каркас» (11 уровней), «Источники», «Профили»,
«Базы знаний», «Таблицы фактов», «Паспорт», «Правила», «Оформление». Паспорт, правила, оформление,
инструкции таблиц и профили можно править прямо в окне и сохранять (POST /save — только с localhost-
origin). Цвет окна берётся из активной темы (по умолчанию — «Первый Бит»). Работает офлайн, на
стандартной библиотеке Python; bind — строго 127.0.0.1.
"""

from __future__ import annotations
import html
import json
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interface import md

_HIDDEN_NAMES = {".venv", "__pycache__", "node_modules"}
_TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".csv", ".log", ".ini", ".cfg", ".toml"}
_MAX_VIEW_BYTES = 200_000

# Редактируемые в окне файлы проекта: id → (имя файла, заголовок раздела)
_EDITABLE = {
    "passport": ("Паспорт проекта.md", "Паспорт"),
    "rules": ("Правила проекта.md", "Правила"),
    "style": ("Оформление.yaml", "Оформление"),
}

_PROJECT: Path | None = None  # корень проекта пользователя

# Реестр саморегистрируемых разделов-плагинов окна. server.py их НЕ импортирует поимённо — раздел
# объявляет себя сам через register(register_section); server находит модули автодискавери (конец файла).
_SECTIONS: list = []


def register_section(key, href, label, page, save_prefix=None, save=None) -> None:
    """Регистрация раздела: page(query, project) -> inner html; save(code, content, project) -> (ok, msg)."""
    _SECTIONS[:] = [s for s in _SECTIONS if s["key"] != key]   # идемпотентно
    _SECTIONS.append({"key": key, "href": href, "label": label,
                      "page": page, "save_prefix": save_prefix, "save": save})


# --- общая обвязка ---------------------------------------------------------

def _palette() -> dict:
    try:
        from reference import theme as theme_mod
        return theme_mod.active_palette(_PROJECT)
    except Exception:
        return {"accent": "#E4007E", "secondary": "#12A5A5",
                "text": "#1A1A1A", "bg": "#FFFFFF", "block": "#F4F4F4"}


def _nav(active: str) -> str:
    tabs = [("план", "/plan", "План"),
            ("проект", "/", "Проект"), ("каркас", "/framework", "Каркас"),
            ("источники", "/sources", "Источники"), ("профили", "/profiles", "Профили"),
            ("знания", "/knowledge", "Базы знаний"),
            ("passport", "/passport", "Паспорт"), ("rules", "/rules", "Правила"),
            ("style", "/style", "Оформление")]
    tabs += [(s["key"], s["href"], s["label"]) for s in _SECTIONS]
    items = []
    for key, href, label in tabs:
        cls = "tab active" if key == active else "tab"
        items.append(f'<a class="{cls}" href="{href}">{label}</a>')
    return '<nav class="tabs">' + "".join(items) + "</nav>"


def _wrap(inner: str, active: str = "проект") -> str:
    pal = _palette()
    project = html.escape(_PROJECT.name if _PROJECT else "Проект")
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{project} — OPP</title>
<style>
  :root {{ --accent: {pal['accent']}; --secondary: {pal['secondary']}; --text: {pal['text']}; --bg: {pal['bg']}; --block: {pal['block']}; }}
  body {{ font-family: Arial, Helvetica, system-ui, sans-serif; margin: 0; color: var(--text); background: var(--bg); }}
  header {{ background: var(--bg); border-bottom: 1px solid #e6e6e6; padding: 14px 28px 0; }}
  header h1.app {{ margin: 0 0 8px; font-size: 18px; font-weight: 700; }}
  nav.tabs {{ display: flex; gap: 2px; flex-wrap: wrap; }}
  nav.tabs .tab {{ padding: 8px 16px; text-decoration: none; color: #777; font-size: 14px; border-bottom: 2px solid transparent; }}
  nav.tabs .tab.active {{ color: var(--text); font-weight: 600; border-bottom-color: var(--accent); }}
  nav.tabs .tab:hover {{ color: var(--accent); }}
  main {{ max-width: 940px; margin: 0 auto; padding: 22px 28px; }}
  main h1 {{ font-size: 20px; margin: 0 0 6px; font-weight: 700; }}
  .crumbs {{ font-size: 14px; margin-bottom: 16px; color: #777; }}
  .crumbs a {{ color: var(--accent); text-decoration: none; }}
  .crumbs a:hover {{ text-decoration: underline; }}
  ul.listing {{ list-style: none; margin: 0; padding: 0; }}
  ul.listing a {{ display: block; padding: 9px 12px; border-bottom: 1px solid #eee; text-decoration: none; color: var(--text); font-size: 15px; }}
  ul.listing a:hover {{ background: var(--block); }}
  ul.listing a.dir {{ font-weight: 600; }}
  pre.filecontent {{ background: #fff; border: 1px solid #e6e6e6; border-radius: 8px; padding: 16px; font-size: 13.5px; white-space: pre-wrap; overflow-x: auto; }}
  .muted {{ color: #777; font-size: 14px; }}
  .axes {{ background: var(--block); border: 1px solid #e6e6e6; border-radius: 8px; padding: 12px 16px; margin: 12px 0 20px; font-size: 13.5px; }}
  .axes div {{ margin: 3px 0; }}
  h2.band {{ font-size: 15px; margin: 26px 0 10px; color: var(--accent); }}
  section.level {{ background: #fff; border: 1px solid #e6e6e6; border-radius: 10px; padding: 14px 18px; margin: 0 0 12px; }}
  section.level h3 {{ margin: 0 0 8px; font-size: 15.5px; color: var(--accent); }}
  section.level p {{ margin: 6px 0; font-size: 13.5px; line-height: 1.45; }}
  section.level p.checks {{ background: var(--block); border-left: 3px solid var(--accent); padding: 8px 10px; border-radius: 4px; }}
  .lbl {{ font-weight: 600; color: #444; }}
  dl.glossary dt {{ font-weight: 600; margin-top: 10px; }}
  dl.glossary dd {{ margin: 2px 0 0; color: #333; font-size: 13.5px; }}
  textarea#editor {{ width: 100%; min-height: 440px; box-sizing: border-box; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; line-height: 1.5; padding: 12px; border: 1px solid #ddd; border-radius: 8px; }}
  .editbar {{ margin-top: 12px; display: flex; align-items: center; gap: 12px; }}
  .btn {{ background: var(--accent); color: #fff; border: 0; border-radius: 8px; padding: 9px 18px; font-size: 14px; cursor: pointer; }}
  .btn:hover {{ filter: brightness(0.92); }}
  .btn:disabled {{ opacity: .6; cursor: default; }}
  .editor-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }}
  @media (max-width: 760px) {{ .editor-grid {{ grid-template-columns: 1fr; }} }}
  .preview {{ background: #fff; border: 1px solid #e6e6e6; border-radius: 8px; padding: 14px 18px; min-height: 440px; overflow: auto; }}
  .md h1 {{ font-size: 19px; margin: 0 0 8px; }}
  .md h2 {{ font-size: 15px; color: var(--accent); margin: 16px 0 6px; }}
  .md h3 {{ font-size: 14px; color: var(--accent); margin: 12px 0 4px; }}
  .md p {{ font-size: 13.5px; line-height: 1.5; margin: 6px 0; }}
  .md ul, .md ol {{ margin: 6px 0 6px 22px; font-size: 13.5px; line-height: 1.5; }}
  .md code {{ background: var(--block); padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }}
  .md blockquote {{ border-left: 3px solid var(--accent); margin: 8px 0; padding: 4px 12px; color: #555; background: var(--block); }}
  .md a {{ color: var(--accent); }}
  .md hr {{ border: 0; border-top: 1px solid #e0e0e0; margin: 12px 0; }}
  .tablewrap {{ overflow-x: auto; }}
  table.fw, .md table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin: 8px 0 14px; }}
  table.fw th, table.fw td, .md th, .md td {{ border: 1px solid #e0e0e0; padding: 7px 9px; text-align: left; vertical-align: top; }}
  table.fw th, .md th {{ background: var(--block); color: var(--accent); font-weight: 600; }}
  table.fw td.checks {{ background: var(--block); }}
  .src {{ color: #888; font-size: 12px; margin-top: 3px; }}
  td code {{ font-size: 12px; color: #555; }}
  .st {{ font-size: 12px; padding: 1px 8px; border-radius: 10px; white-space: nowrap; }}
  .st-план {{ background: #eee; color: #777; }}
  .st-сборка {{ background: #ffe9f4; color: var(--accent); }}
  .st-готова {{ background: #e7f6ec; color: #2ea44f; }}
</style></head>
<body>
  <header>
    <h1 class="app">{project} — OPP</h1>
    {_nav(active)}
  </header>
  <main>{inner}</main>
</body></html>"""


# --- раздел «Проект» (браузер папки) --------------------------------------

def _hidden(name: str) -> bool:
    return name.startswith(".") or name in _HIDDEN_NAMES


def _safe_target(rel: str):
    assert _PROJECT is not None
    target = (_PROJECT / rel).resolve()
    if target == _PROJECT or _PROJECT in target.parents:
        return target
    return None


def _child(rel: str, name: str) -> str:
    return f"{rel}/{name}" if rel else name


def _breadcrumb(rel: str, is_file: bool = False) -> str:
    parts = [p for p in rel.split("/") if p]
    crumbs = ['<a href="/?path=">Проект</a>']
    acc = ""
    for i, part in enumerate(parts):
        acc = _child(acc, part)
        label = html.escape(part)
        if is_file and i == len(parts) - 1:
            crumbs.append(f"<span>{label}</span>")
        else:
            crumbs.append(f'<a href="/?path={urllib.parse.quote(acc)}">{label}</a>')
    return '<nav class="crumbs">' + " / ".join(crumbs) + "</nav>"


def _render_dir(target: Path, rel: str) -> str:
    try:
        entries = [p for p in target.iterdir() if not _hidden(p.name)]
    except OSError:
        return '<p class="muted">Не удалось открыть папку.</p>'
    entries.sort(key=lambda p: (p.is_file(), p.name.lower()))
    if not entries:
        return '<p class="muted">Папка пуста.</p>'
    rows = ['<ul class="listing">']
    for p in entries:
        link = urllib.parse.quote(_child(rel, p.name))
        name = html.escape(p.name)
        if p.is_dir():
            rows.append(f'<li><a class="dir" href="/?path={link}">📁 {name}</a></li>')
        else:
            rows.append(f'<li><a class="file" href="/?file={link}">📄 {name}</a></li>')
    rows.append("</ul>")
    return "".join(rows)


def _render_file(target: Path, rel: str) -> str:
    size = target.stat().st_size
    if target.suffix.lower() in _TEXT_SUFFIXES and size <= _MAX_VIEW_BYTES:
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return '<p class="muted">Не удалось прочитать файл как текст.</p>'
        if target.suffix.lower() == ".md":
            return f'<div class="md">{md.md_to_html(text)}</div>'
        return f'<pre class="filecontent">{html.escape(text)}</pre>'
    return (f'<p class="muted">Содержимое не показывается '
            f'(не текстовый файл или слишком большой, {size} байт).</p>')


def _project_page(query: dict) -> str:
    rel_file = query.get("file", [None])[0]
    if rel_file is not None:
        rel_file = urllib.parse.unquote(rel_file)
        target = _safe_target(rel_file)
        if target and target.is_file():
            return _wrap(_breadcrumb(rel_file, is_file=True) + _render_file(target, rel_file), "проект")
        return _wrap('<p class="muted">Файл не найден.</p>' + _breadcrumb(""), "проект")

    rel_dir = urllib.parse.unquote(query.get("path", [""])[0])
    target = _safe_target(rel_dir)
    if target and target.is_dir():
        return _wrap(_breadcrumb(rel_dir) + _render_dir(target, rel_dir), "проект")
    return _wrap('<p class="muted">Папка не найдена.</p>' + _breadcrumb(""), "проект")


def _page_for(query: dict) -> str:  # alias для тестов
    return _project_page(query)


# --- раздел «Каркас» -------------------------------------------------------

def _framework_page() -> str:
    try:
        from reference import framework
        inner = '<h1>Каркас — 11 уровней</h1>' + framework.render_framework_html()
    except ImportError:
        inner = ('<p class="muted">Для раздела «Каркас» нужна библиотека PyYAML. '
                 'Установите: ./.venv/bin/python -m pip install pyyaml</p>')
    except Exception as exc:  # noqa: BLE001
        inner = f'<p class="muted">Не удалось показать каркас: {html.escape(str(exc))}</p>'
    return _wrap(inner, "каркас")


def _plan_page() -> str:
    try:
        import plan
        inner = '<h1>План и компоненты</h1>' + plan.render_html()
    except ImportError:
        inner = ('<p class="muted">Для раздела нужна библиотека PyYAML. '
                 'Установите: ./.venv/bin/python -m pip install pyyaml</p>')
    except Exception as exc:  # noqa: BLE001
        inner = f'<p class="muted">Не удалось показать план: {html.escape(str(exc))}</p>'
    return _wrap(inner, "план")


def _sources_page() -> str:
    try:
        from capabilities.extract import sources
        inner = '<h1>Источники</h1>' + sources.render_html()
    except ImportError:
        inner = ('<p class="muted">Для раздела нужна библиотека PyYAML. '
                 'Установите: ./.venv/bin/python -m pip install pyyaml</p>')
    except Exception as exc:  # noqa: BLE001
        inner = f'<p class="muted">Не удалось показать источники: {html.escape(str(exc))}</p>'
    return _wrap(inner, "источники")


def _knowledge_page() -> str:
    try:
        from knowledge import registry
        inner = '<h1>Базы знаний</h1>' + registry.render_html()
    except ImportError:
        inner = ('<p class="muted">Для раздела нужна библиотека PyYAML. '
                 'Установите: ./.venv/bin/python -m pip install pyyaml</p>')
    except Exception as exc:  # noqa: BLE001
        inner = f'<p class="muted">Не удалось показать реестр БЗ: {html.escape(str(exc))}</p>'
    return _wrap(inner, "знания")


# --- разделы-редакторы (Паспорт / Правила / Оформление) --------------------

_MD_EDITOR_TEMPLATE = """<h1>__TITLE__</h1>
<p class="muted">__FILE__ — слева правьте, справа предпросмотр с оформлением. Нажмите «Сохранить».</p>
<div class="editor-grid">
  <textarea id="editor" spellcheck="false">__CONTENT__</textarea>
  <div id="preview" class="md preview"></div>
</div>
<div class="editbar"><button id="save" class="btn">Сохранить</button> <span id="status" class="muted"></span></div>
<script>
(function(){
  var ta=document.getElementById('editor'), pv=document.getElementById('preview'),
      btn=document.getElementById('save'), st=document.getElementById('status'), t=null;
  function render(){
    fetch('/render',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'content='+encodeURIComponent(ta.value)})
      .then(function(r){return r.text();}).then(function(h){pv.innerHTML=h;});
  }
  ta.addEventListener('input', function(){ clearTimeout(t); t=setTimeout(render,300); });
  btn.addEventListener('click', function(){
    btn.disabled=true; st.textContent='Сохраняю…';
    fetch('/save',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'id=__ID__&content='+encodeURIComponent(ta.value)})
      .then(function(r){return r.json();})
      .then(function(d){ st.textContent=d.message; btn.disabled=false; })
      .catch(function(e){ st.textContent='Ошибка: '+e; btn.disabled=false; });
  });
  render();
})();
</script>"""

_YAML_EDITOR_TEMPLATE = """<h1>__TITLE__</h1>
<p class="muted">__FILE__ — правьте прямо здесь и нажмите «Сохранить».__HINT__</p>
<textarea id="editor" spellcheck="false">__CONTENT__</textarea>
<div class="editbar"><button id="save" class="btn">Сохранить</button> <span id="status" class="muted"></span></div>
<script>
(function(){
  var ta=document.getElementById('editor'), btn=document.getElementById('save'), st=document.getElementById('status');
  btn.addEventListener('click', function(){
    btn.disabled=true; st.textContent='Сохраняю…';
    fetch('/save',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'id=__ID__&content='+encodeURIComponent(ta.value)})
      .then(function(r){return r.json();})
      .then(function(d){ st.textContent=d.message; btn.disabled=false; if(d.ok && '__ID__'==='style'){ setTimeout(function(){location.reload();},700);} })
      .catch(function(e){ st.textContent='Ошибка: '+e; btn.disabled=false; });
  });
})();
</script>"""


def _editor_page(file_id: str) -> str:
    filename, title = _EDITABLE[file_id]
    content = ""
    if _PROJECT is not None:
        target = _PROJECT / filename
        if target.is_file():
            try:
                content = target.read_text(encoding="utf-8")
            except OSError:
                content = ""
    is_md = file_id in ("passport", "rules")
    template = _MD_EDITOR_TEMPLATE if is_md else _YAML_EDITOR_TEMPLATE
    hint = " Это файл YAML — соблюдайте формат." if file_id == "style" else ""
    body = (template
            .replace("__TITLE__", html.escape(title))
            .replace("__FILE__", html.escape(filename))
            .replace("__HINT__", hint)
            .replace("__CONTENT__", html.escape(content))
            .replace("__ID__", file_id))
    return _wrap(body, file_id)


def _profiles_list_page() -> str:
    from capabilities.extract import profiles as prof
    rows = ['<p class="muted">Профили сбора по конфигурациям. Коробка — предзаполнено по известным '
            'конфигурациям; правка сохраняется как переопределение проекта '
            '(<code>Источники/профили/&lt;id&gt;.yaml</code>).</p>',
            '<div class="tablewrap"><table class="fw"><thead><tr>'
            '<th>Конфигурация</th><th>id</th><th>Источник</th><th></th></tr></thead><tbody>']
    for cid in prof.list_profiles():
        p = prof.load_profile(cid, _PROJECT) or {}
        name = html.escape(str(p.get("конфигурация", cid)))
        rows.append(f'<tr><td>{name}</td><td><code>{html.escape(cid)}</code></td>'
                    f'<td>{html.escape(prof.profile_source(cid, _PROJECT))}</td>'
                    f'<td><a href="/profile?id={urllib.parse.quote(cid)}">Править</a></td></tr>')
    rows.append('</tbody></table></div>')
    return _wrap('<h1>Профили сбора</h1>' + "".join(rows), "профили")


def _profile_editor_page(config_id: str) -> str:
    from capabilities.extract import profiles as prof
    if config_id not in prof.list_profiles():
        return _wrap('<h1>Профили сбора</h1><p class="muted">Профиль не найден.</p>', "профили")
    body = (_YAML_EDITOR_TEMPLATE
            .replace("__TITLE__", html.escape(f"Профиль: {config_id}"))
            .replace("__FILE__", html.escape(f"Источники/профили/{config_id}.yaml (правка → проект)"))
            .replace("__HINT__", " Это файл YAML — соблюдайте формат.")
            .replace("__CONTENT__", html.escape(prof.read_profile_text(config_id, _PROJECT)))
            .replace("__ID__", f"profile:{config_id}"))
    return _wrap(body, "профили")


def _save_file(file_id: str, content: str) -> tuple[bool, str]:
    if _PROJECT is None:
        return False, "проект не открыт"
    for _s in _SECTIONS:
        if _s.get("save_prefix") and _s.get("save") and file_id.startswith(_s["save_prefix"]):
            return _s["save"](file_id[len(_s["save_prefix"]):], content, _PROJECT)
    if file_id.startswith("profile:"):
        from capabilities.extract import profiles as prof
        cid = file_id[len("profile:"):]
        if cid not in prof.list_profiles():
            return False, "неизвестный профиль"
        try:
            import yaml
            yaml.safe_load(content)
        except Exception as exc:  # noqa: BLE001
            return False, f"не сохранено: ошибка в YAML ({exc})"
        prof.save_profile_text(cid, content, _PROJECT)
        return True, "Сохранено в проект ✓"
    if file_id not in _EDITABLE:
        return False, "неизвестный файл"
    filename, _title = _EDITABLE[file_id]
    target = (_PROJECT / filename).resolve()
    if target.parent != _PROJECT:
        return False, "недопустимый путь"
    if file_id == "style":
        try:
            import yaml
            data = yaml.safe_load(content)
        except Exception as exc:  # noqa: BLE001
            return False, f"не сохранено: ошибка в YAML ({exc})"
        try:
            from reference import theme as theme_mod
            problems = theme_mod.validate_theme(data)
        except Exception:
            problems = []
        if problems:
            return False, "не сохранено: " + "; ".join(problems)
    try:
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return False, f"не сохранено: {exc}"
    return True, "Сохранено ✓"


# --- HTTP ------------------------------------------------------------------

def _origin_allowed(origin) -> bool:
    """Пишущие запросы — только со своего окна (или без Origin: curl/формы same-origin).

    Защита от CSRF: чужая страница в браузере пользователя может слать simple-POST
    на 127.0.0.1 без preflight; сверяем Origin с localhost."""
    if not origin:
        return True
    host = urllib.parse.urlparse(origin).hostname
    return host in ("127.0.0.1", "localhost", "::1")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/plan":
            self._send(200, _plan_page().encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/framework":
            self._send(200, _framework_page().encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/sources":
            self._send(200, _sources_page().encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/knowledge":
            self._send(200, _knowledge_page().encode("utf-8"), "text/html; charset=utf-8")
        elif any(path == s["href"] for s in _SECTIONS):
            section = next(s for s in _SECTIONS if s["href"] == path)
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                inner = section["page"](query, _PROJECT)
            except Exception as exc:  # noqa: BLE001
                inner = f'<p class="muted">Раздел недоступен: {html.escape(str(exc))}</p>'
            self._send(200, _wrap(inner, section["key"]).encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/profiles":
            self._send(200, _profiles_list_page().encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/profile":
            cid = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id", [""])[0]
            self._send(200, _profile_editor_page(cid).encode("utf-8"), "text/html; charset=utf-8")
        elif path in ("/passport", "/rules", "/style"):
            self._send(200, _editor_page(path[1:]).encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
            self._send(200, _project_page(query).encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if not _origin_allowed(self.headers.get("Origin")):
            self._send(403, "запрос с чужого origin отклонён".encode("utf-8"),
                       "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)

        if path == "/render":
            rendered = md.md_to_html(form.get("content", [""])[0])
            self._send(200, rendered.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/save":
            ok, msg = _save_file(form.get("id", [""])[0], form.get("content", [""])[0])
            body = json.dumps({"ok": ok, "message": msg}, ensure_ascii=False).encode("utf-8")
            self._send(200 if ok else 400, body, "application/json; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *args) -> None:
        return


def serve(project_path, port: int = 8765, open_browser: bool = True) -> None:
    global _PROJECT
    _PROJECT = Path(project_path).resolve()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Окно проекта открыто: {url}")
    print(f"Проект: {_PROJECT}")
    print("Разделы: План · Проект · Каркас · Источники · Профили · Знания · Таблицы · "
          "Паспорт · Правила · Оформление. Остановить — Ctrl+C.")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        server.server_close()


def _load_sections() -> None:
    """Автодискавери разделов-плагинов: модули interface/*.py с функцией register(register_section) сами
    регистрируют свои разделы. server.py не импортирует их поимённо — только сканирует пакет interface."""
    import importlib
    import pkgutil
    import interface as _pkg
    for info in pkgutil.iter_modules(_pkg.__path__):
        if info.name in ("server", "md"):
            continue
        try:
            mod = importlib.import_module(f"interface.{info.name}")
            hook = getattr(mod, "register", None)
            if callable(hook):
                hook(register_section)
        except Exception:  # noqa: BLE001
            pass


_load_sections()
