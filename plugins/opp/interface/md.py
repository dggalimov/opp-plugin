"""Компактный отрисовщик Markdown → HTML (без сторонних библиотек).

Поддержано: заголовки (#..######), списки (- / * и 1.) с вложенностью, таблицы (| .. |),
цитаты (>), горизонтальная черта (---), абзацы; в строках — **жирный**, *курсив*, `код`,
[текст](ссылка). Этого достаточно для паспорта, правил и просмотра markdown-файлов проекта.
"""

from __future__ import annotations
import html
import re

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_HR = re.compile(r"^(-{3,}|\*{3,})$")
_LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
_SEP = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")

# Разрешённые схемы ссылок: http/https/mailto и относительные пути.
# javascript:/data:/vbscript: и прочие исполняемые схемы обезвреживаются (экранирование не спасает href).
_SAFE_SCHEME = re.compile(r"^(https?:|mailto:)", re.IGNORECASE)
_HAS_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _link(m: re.Match) -> str:
    href = m.group(2)
    if _HAS_SCHEME.match(href) and not _SAFE_SCHEME.match(href):
        return f"{m.group(1)} ({href})"  # схема не разрешена — оставить текстом, без <a>
    return f'<a href="{href}" target="_blank" rel="noopener">{m.group(1)}</a>'


def _inline(text: str) -> str:
    text = html.escape(text)
    text = _CODE.sub(r"<code>\1</code>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _LINK.sub(_link, text)
    return text


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _parse_table(lines: list[str], i: int):
    header = _split_row(lines[i])
    i += 2  # шапка + разделитель
    rows = []
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        rows.append(_split_row(lines[i]))
        i += 1
    out = ["<table><thead><tr>"]
    out += [f"<th>{_inline(c)}</th>" for c in header]
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out), i


def _parse_list(lines: list[str], i: int):
    items = []  # (indent, ordered, content)
    while i < len(lines):
        m = _LIST.match(lines[i])
        if not m:
            break
        ordered = bool(re.match(r"\d+\.", m.group(2)))
        items.append((len(m.group(1)), ordered, m.group(3)))
        i += 1

    out = []
    stack = []  # (indent, tag)
    for indent, ordered, content in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if not stack or indent > stack[-1][0]:
            stack.append((indent, tag))
            out.append(f"<{tag}><li>{_inline(content)}")
        else:
            out.append(f"</li><li>{_inline(content)}")
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out), i


def md_to_html(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        m = _HEADING.match(stripped)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if _HR.match(stripped):
            out.append("<hr>")
            i += 1
            continue
        if "|" in line and i + 1 < n and "-" in lines[i + 1] and _SEP.match(lines[i + 1]):
            tbl, i = _parse_table(lines, i)
            out.append(tbl)
            continue
        if stripped.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            continue
        if _LIST.match(line):
            lst, i = _parse_list(lines, i)
            out.append(lst)
            continue
        para = []
        while i < n and lines[i].strip() and not _HEADING.match(lines[i].strip()) \
                and not lines[i].strip().startswith(">") and not _LIST.match(lines[i]) \
                and not _HR.match(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)
