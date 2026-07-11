"""Раздел окна «Таблицы фактов» (ui-facttables): обзор 39 таблиц по уровням + паспорт (read-only) +
строки проекта из memory/<КОД>.yaml + редактор эффективной инструкции с откатом.

MVP-граница: только просмотр строк и правка инструкций заполнения (ввод/правка фактов и навигация по
рёбрам — отдельные элементы). Поверх: schema.model (контракт 39 таблиц), schema.instructions (cap-instr:
read/save/revert), память проекта (устойчиво к отсутствию). Оболочку (_wrap/_nav/тема) даёт server.py.
"""

from __future__ import annotations
import html
from pathlib import Path

from schema.model import load_schema, targets_of
from schema.instructions import read_instruction


# --- обзор -----------------------------------------------------------------

def _table_link(code, tab) -> str:
    return (f'<li><a href="/facttables?table={html.escape(code)}">'
            f'{html.escape(tab.title)} <code>{html.escape(code)}</code>'
            f'<span class="muted"> · {html.escape(tab.group)} · {html.escape(tab.kind)}</span></a></li>')


def render_overview() -> str:
    """Обзор всех таблиц: по 11 уровням каркаса + внеуровневые группы (вход · осмысление · TO-BE)."""
    schema = load_schema()
    by_level: dict = {}
    rest: list = []
    for code, tab in schema.tables.items():
        (by_level.setdefault(tab.level, []) if isinstance(tab.level, int) else rest).append((code, tab))

    parts = ['<h1>Таблицы фактов</h1>',
             f'<p class="muted">Контракт схемы памяти — {len(schema.tables)} таблиц. '
             'Здесь: просмотр паспорта и строк проекта, правка инструкций заполнения.</p>',
             '<h2 class="band">По уровням каркаса</h2>']
    for lvl in range(1, 12):
        items = by_level.get(lvl)
        if not items:
            continue
        parts.append(f'<section class="level"><h3>Уровень {lvl}</h3><ul class="listing">')
        parts += [_table_link(c, t) for c, t in sorted(items)]
        parts.append('</ul></section>')
    if rest:
        parts.append('<h2 class="band">Вне уровней (вход · осмысление · TO-BE)</h2><ul class="listing">')
        parts += [_table_link(c, t) for c, t in sorted(rest, key=lambda x: (x[1].group, x[0]))]
        parts.append('</ul>')
    return "".join(parts)


# --- паспорт (read-only) ---------------------------------------------------

def _fmt(v) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, list):
        return "; ".join(_fmt(x) for x in v)
    return html.escape(str(v))


def _passport_html(tab) -> str:
    p = [f'<h2 class="band">Паспорт (только чтение)</h2>',
         '<div class="axes">',
         f'<div><span class="lbl">Группа:</span> {_fmt(tab.group)}</div>',
         f'<div><span class="lbl">Тип:</span> {_fmt(tab.kind)}</div>',
         f'<div><span class="lbl">Уровень каркаса:</span> {_fmt(tab.level)}</div>',
         f'<div><span class="lbl">Покрытие методикой:</span> {_fmt(tab.coverage)}</div>',
         '</div>']
    # поля
    p.append('<h3 class="band">Поля</h3><div class="tablewrap"><table class="fw"><thead><tr>'
             '<th>Имя</th><th>Вид</th><th>Обяз.</th><th>Словарь / цель</th></tr></thead><tbody>')
    for f in tab.fields:
        sl = _fmt(f.enum) if f.enum else ("→ " + _fmt(f.target) if f.target is not None else "—")
        p.append(f'<tr><td>{_fmt(f.name)}</td><td>{_fmt(f.kind)}</td>'
                 f'<td>{_fmt(f.required)}</td><td>{sl}</td></tr>')
    p.append('</tbody></table></div>')
    # связи
    if tab.edges:
        p.append('<h3 class="band">Связи</h3><div class="tablewrap"><table class="fw"><thead><tr>'
                 '<th>С таблицей</th><th>Через поле</th><th>Кардинальность</th><th>Смысл</th>'
                 '</tr></thead><tbody>')
        for e in tab.edges:
            p.append(f'<tr><td>{_fmt(e.target)}</td><td>{_fmt(e.field)}</td>'
                     f'<td>{_fmt(e.cardinality)}</td><td>{_fmt(e.meaning)}</td></tr>')
        p.append('</tbody></table></div>')
    # рецепт + стык
    rec = tab.recipe or {}
    if rec:
        p.append('<h3 class="band">Рецепт (логика)</h3><div class="axes">'
                 f'<div><span class="lbl">Ведущий канал:</span> {_fmt(rec.get("ведущий_канал"))}</div>'
                 f'<div><span class="lbl">Что = проблема:</span> {_fmt(rec.get("что_проблема"))}</div>'
                 f'<div><span class="lbl">Норма глубины:</span> {_fmt(rec.get("норма_глубины"))}</div>'
                 f'<div><span class="lbl">Опора:</span> {_fmt(rec.get("опора"))}</div></div>')
    seam = tab.seam or {}
    if seam:
        p.append('<h3 class="band">Стык</h3><div class="axes">'
                 f'<div><span class="lbl">Даёт:</span> {_fmt(seam.get("даёт"))}</div>'
                 f'<div><span class="lbl">Потребляет:</span> {_fmt(seam.get("потребляет"))}</div></div>')
    return "".join(p)


# --- строки проекта (memory) ------------------------------------------------

def _load_rows(code: str, project) -> list:
    """Строки таблицы из <проект>/memory/<КОД>.yaml. Устойчиво к отсутствию памяти/файла."""
    if project is None:
        return []
    f = Path(project) / "memory" / f"{code}.yaml"
    if not f.is_file():
        return []
    try:
        import yaml
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [r for r in data["rows"] if isinstance(r, dict)]
    return []


def _rows_html(code: str, tab, project) -> str:
    rows = _load_rows(code, project)
    if not rows:
        return ('<h2 class="band">Строки проекта</h2>'
                f'<p class="muted">Память не заполнена (нет строк в <code>memory/{html.escape(code)}.yaml</code>).</p>')
    cols = [f.name for f in tab.fields] or sorted({k for r in rows for k in r})
    p = [f'<h2 class="band">Строки проекта ({len(rows)})</h2><div class="tablewrap"><table class="fw"><thead><tr>']
    p += [f'<th>{_fmt(c)}</th>' for c in cols]
    p.append('</tr></thead><tbody>')
    for r in rows:
        p.append('<tr>' + "".join(f'<td>{_fmt(r.get(c))}</td>' for c in cols) + '</tr>')
    p.append('</tbody></table></div>')
    return "".join(p)


# --- редактор инструкции (cap-instr) ---------------------------------------

_INSTR_EDITOR = """<h2 class="band">Инструкция заполнения</h2>
<p class="muted">Источник: <b>__SRC__</b>. Правка заменяет дефолт целиком; «Откатить» вернёт дефолт продукта (reg-facttables).</p>
<textarea id="editor" spellcheck="false">__CONTENT__</textarea>
<div class="editbar">
  <button id="save" class="btn">Сохранить</button>
  <button id="revert" class="btn" style="background:#888">Откатить к дефолту</button>
  <span id="status" class="muted"></span>
</div>
<script>
(function(){
  var ta=document.getElementById('editor'), save=document.getElementById('save'),
      rev=document.getElementById('revert'), st=document.getElementById('status');
  function post(content){
    st.textContent='Сохраняю…'; save.disabled=true; rev.disabled=true;
    fetch('/save',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'id=instr:__CODE__&content='+encodeURIComponent(content)})
      .then(function(r){return r.json();})
      .then(function(d){ st.textContent=d.message; if(d.ok){ setTimeout(function(){location.reload();},500);} else { save.disabled=false; rev.disabled=false; } })
      .catch(function(e){ st.textContent='Ошибка: '+e; save.disabled=false; rev.disabled=false; });
  }
  save.addEventListener('click', function(){ post(ta.value); });
  rev.addEventListener('click', function(){ post(''); });
})();
</script>"""


def _instruction_editor(code: str, project) -> str:
    if project is None:
        return ('<h2 class="band">Инструкция заполнения</h2>'
                '<p class="muted">Проект не открыт — правка инструкции недоступна.</p>')
    instr = read_instruction(code, project)
    return (_INSTR_EDITOR
            .replace("__SRC__", html.escape(instr.get("источник", "")))
            .replace("__CONTENT__", html.escape(instr.get("эффективная", "")))
            .replace("__CODE__", html.escape(code)))


# --- детальная страница таблицы --------------------------------------------

def render_table(code: str, project) -> str:
    schema = load_schema()
    if code not in schema.tables:
        return ('<h1>Таблицы фактов</h1><p class="muted">Таблица не найдена.</p>'
                '<p><a href="/facttables">← к обзору</a></p>')
    tab = schema.tables[code]
    return (f'<nav class="crumbs"><a href="/facttables">Таблицы фактов</a> / '
            f'<span>{html.escape(code)}</span></nav>'
            f'<h1>{html.escape(tab.title)} <code>{html.escape(code)}</code></h1>'
            + _passport_html(tab)
            + _rows_html(code, tab, project)
            + _instruction_editor(code, project))


def render(query: dict, project) -> str:
    """Точка входа раздела: ?table=<КОД> → детальная страница, иначе обзор."""
    code = (query.get("table", [None]) or [None])[0]
    return render_table(code, project) if code else render_overview()


def _save(code, content, project):
    """POST /save handler для инструкций (префикс instr:): (code, content, project) -> (ok, message)."""
    from schema.instructions import save_instruction
    if project is None:
        return False, "проект не открыт"
    try:
        saved = save_instruction(code, project, content)
    except (KeyError, ValueError) as exc:
        return False, f"не сохранено: {exc}"
    return True, ("Откат к дефолту ✓" if saved is None else "Сохранено ✓")


def register(register_section):
    """Саморегистрация раздела «Таблицы фактов» в окне (cap-ui-decouple): окно нас не импортирует."""
    register_section("таблицы", "/facttables", "Таблицы фактов", render,
                     save_prefix="instr:", save=_save)
