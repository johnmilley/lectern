"""HTML for the reading pane: Bible chapters, the Psalter, the Office, search results."""
from __future__ import annotations

import datetime as _dt
import html
import json
import re

from .books import BY_ID
from .store import SCOPES, Bible, Psalter, VerseRow

esc = html.escape

# LORD / GOD (the divine name) set in small capitals, as in the printed edition.
_DIVINE = re.compile(r"\b(LORD|GOD)(’s|'s)?\b")


def _divine(s: str) -> str:
    return _DIVINE.sub(lambda m: f'<span class="sc">{m.group(1).capitalize()}</span>{m.group(2) or ""}', s)


def ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def page(body: str, opts: dict, title: str = "", data: dict | None = None) -> str:
    theme = opts.get("theme", "paper")
    cls = [f"theme-{theme}"]
    for key in ("verse_numbers", "headings", "fn_markers", "red"):
        if not opts.get(key, True):
            cls.append(f"no-{key.replace('_', '-')}")
    payload = json.dumps(data or {}, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html class="{' '.join(cls)}" style="--fs:{int(opts.get('font_size', 20))}px">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<link rel="stylesheet" href="reader.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script id="page-data" type="application/json">{payload}</script>
<script src="reader.js"></script>
</head>
<body>
<main class="page">
{body}
</main>
<div id="popover" hidden></div>
</body>
</html>"""


# --------------------------------------------------------------------------- Bible chapters

def render_chapter(bible: Bible, book: int, chapter: int, opts: dict) -> tuple[str, dict]:
    rows = bible.chapter(book, chapter)
    b = bible.book_by_id[book]
    notes = bible.notes_for(r.id for r in rows)
    alt = bible.alt_number(book, chapter)
    chapters = bible.chapters(book)

    out: list[str] = []
    out.append('<header class="chap-head">')
    if chapter == chapters[0]:
        out.append(f'<div class="book-title">{esc(b["title"])}</div>')
    else:
        out.append(f'<div class="running-title">{esc(b["title"])}</div>')
    label = "Psalm" if book == 21 else "Chapter"
    alt_html = f' <span class="alt">[{alt}]</span>' if alt else ""
    out.append(f'<h1 class="chap-title">{label} {chapter}{alt_html}</h1>')
    if book == 21:
        out.append(f'<div class="crosslink"><a href="lectern:coverdale/{chapter}">Read in the Coverdale Psalter &#x203A;</a></div>')
    out.append("</header>")

    doc_ids = {n["verse_id"] for n in notes if n["kind"] == "doc"}
    note_map = {n["note_id"]: {"kind": n["kind"], "html": n["html"]} for n in notes}
    out.append('<article class="text">')
    out.append(_verses_html(rows, doc_ids, first_chapter_numeral=chapter))
    out.append("</article>")

    if opts.get("endnotes", True) and notes:
        out.append(_endnotes_html(rows, notes, book))

    prev_ = bible.neighbour(book, chapter, -1)
    next_ = bible.neighbour(book, chapter, +1)
    out.append('<nav class="pager">')
    if prev_:
        out.append(f'<a href="lectern:chapter/{prev_[0]}/{prev_[1]}">&#x2039; {esc(_chap_label(bible, *prev_))}</a>')
    else:
        out.append("<span></span>")
    if next_:
        out.append(f'<a href="lectern:chapter/{next_[0]}/{next_[1]}">{esc(_chap_label(bible, *next_))} &#x203A;</a>')
    out.append("</nav>")
    data = {"kind": "bible", "notes": note_map, "book": book, "chapter": chapter}
    return "\n".join(out), data


def _chap_label(bible: Bible, book: int, chapter: int) -> str:
    name = bible.book_by_id[book]["name"]
    if book == 21:
        return f"Psalm {chapter}"
    return f"{name} {chapter}"


def _verses_html(rows: list[VerseRow], doc_ids: set, first_chapter_numeral: int | None = None,
                 show_chapter_numbers=False) -> str:
    out: list[str] = []
    mode = None            # None | 'prose' | 'poetry'
    line_open = False

    def close():
        nonlocal mode, line_open
        if mode == "prose":
            out.append("</p>")
        elif mode == "poetry":
            if line_open:
                out.append("</div>")
            out.append("</div>")
        mode, line_open = None, False

    def open_prose():
        nonlocal mode
        close()
        out.append('<p class="prose">')
        mode = "prose"

    def new_line(indent: bool):
        nonlocal mode, line_open
        if mode != "poetry":
            close()
            out.append('<div class="poetry">')
            mode = "poetry"
        elif line_open:
            out.append("</div>")
        out.append(f'<div class="line{" indent" if indent else ""}">')
        line_open = True

    prev_chapter = None
    for r in rows:
        started = False
        for kind, h in r.segs:
            h = _divine(h)
            if kind == "h":
                close()
                out.append(f'<h3 class="heading">{h}</h3>')
                continue
            if kind == "t":
                close()
                out.append(f'<p class="title"><span class="v" data-id="{r.id}">{h}</span></p>')
                continue
            if kind == "p":
                open_prose()
            elif kind in ("l", "i"):
                new_line(kind == "i")
            elif mode is None:
                open_prose()
            marker = ""
            if not started and r.verse > 0:
                started = True
                chap_start = r.verse == 1 and r.chapter != prev_chapter and (
                    first_chapter_numeral is not None or show_chapter_numbers)
                if chap_start:
                    marker = f'<span class="chapnum" data-id="{r.id}">{r.chapter}</span>'
                else:
                    marker = f'<sup class="vn" data-id="{r.id}">{esc(r.label)}</sup>'
                if r.id in doc_ids:
                    marker += f'<sup class="dn" data-verse="{r.id}" title="Doctrinal note">*</sup>'
                prev_chapter = r.chapter
            out.append(f'<span class="v" data-id="{r.id}">{marker}{h} </span>')
    close()
    return "\n".join(out)


def _endnotes_html(rows: list[VerseRow], notes: list[dict], book: int) -> str:
    by_id = {r.id: r for r in rows}
    fn = [n for n in notes if n["kind"] == "fn"]
    dn = [n for n in notes if n["kind"] == "doc"]
    xr = [n for n in notes if n["kind"] == "xref"]
    out = ['<section class="endnotes">']
    if fn:
        out.append('<h4>Notes</h4><ol class="notes notes-fn">')
        for n in fn:
            r = by_id[n["verse_id"]]
            out.append(f'<li id="n-{esc(n["note_id"])}"><a class="nref" href="lectern:verse/{r.id}">{r.chapter}:{esc(r.label)}</a> '
                       f'<span class="mk">{esc(n["marker"])}</span> {_divine(n["html"])}</li>')
        out.append("</ol>")
    if xr:
        out.append('<h4>Cross References</h4><ol class="notes notes-xr">')
        for n in xr:
            r = by_id[n["verse_id"]]
            body = re.sub(r"^<b>[^<]*</b>\s*", "", n["html"])
            out.append(f'<li><a class="nref" href="lectern:verse/{r.id}">{r.chapter}:{esc(r.label)}</a> {_links(body)}</li>')
        out.append("</ol>")
    if dn:
        out.append('<h4>Doctrinal Notes</h4><ol class="notes notes-dn">')
        for n in dn:
            r = by_id[n["verse_id"]]
            out.append(f'<li id="d-{r.id}"><a class="nref" href="lectern:verse/{r.id}">{r.chapter}:{esc(r.label)}</a> {_links(_divine(n["html"]))}</li>')
        out.append("</ol>")
    out.append("</section>")
    return "\n".join(out)


def _links(h: str) -> str:
    return re.sub(r'href="ref:(\d+)\.(\d+)\.(\d+)"', r'href="lectern:ref/\1/\2/\3"', h)


def note_popup_html(h: str) -> str:
    return _links(_divine(h))


# --------------------------------------------------------------------------- passages (Office lessons, export)

def render_passage(bible: Bible, rows: list[VerseRow], heading: str | None = None) -> str:
    if not rows:
        return '<p class="rubric">That passage could not be found.</p>'
    out = []
    if heading:
        out.append(f'<div class="passage-ref">{esc(heading)}</div>')
    # Drop section headings inside lessons, as a lectionary does.
    rows = [VerseRow(r.id, r.book, r.chapter, r.verse, r.verse_end, [s for s in r.segs if s[0] != "h"], r.text)
            for r in rows]
    out.append(_verses_html(rows, set()))
    return "\n".join(out)


# --------------------------------------------------------------------------- Coverdale Psalter

def _cov_verse(n: int, v: list, opts: dict, first=False) -> str:
    num, a, b = v
    star = '<span class="star">*</span>' if opts.get("pointing", "*") == "*" else '<span class="colon">:</span>'
    a, b = _divine(a), _divine(b)
    if first:
        m = re.match(r"^(\W*)(\w)(\w*)(.*)$", a, re.S)
        if m:
            a = f'{m.group(1)}<span class="dropcap">{m.group(2)}</span><span class="lead">{m.group(3)}</span>{m.group(4)}'
    return (f'<p class="pv" data-ps="{n}" data-v="{num}"><span class="pvn">{num}</span>'
            f'<span class="pvt">{a} {star} {b}</span></p>')


def render_psalm(psalter: Psalter, n: int, opts: dict, first=1, last=None, header=True,
                 bible: Bible | None = None, compare=False) -> str:
    ps = psalter.psalms[n]
    verses = ps["verses"]
    last = last or len(verses)
    out = [f'<section class="psalm" id="ps-{n}">']
    if header:
        range_note = "" if (first, last) == (1, len(verses)) else f'<span class="range">vv. {first}–{last}</span>'
        out.append(f'<div class="ps-head"><span class="ps-num">Psalm {n}.</span>'
                   f'<span class="ps-latin">{esc(ps["latin"])}.</span>{range_note}</div>')
    sections = {s["start"]: s for s in ps.get("sections", [])}
    rsv = {}
    if compare and bible is not None:
        for r in bible.chapter(21, n):
            if r.verse > 0:
                rsv[r.verse] = r
    started = False
    for v in verses[first - 1:last]:
        num = v[0]
        if num in sections and n == 119:
            s = sections[num]
            out.append(f'<div class="ps-section"><span class="hebrew">{esc(s["hebrew"])}.</span> '
                       f'<span class="ps-latin">{esc(s["latin"])}</span></div>')
            started = False
        first_verse = not started
        started = True
        if compare:
            r = rsv.get(num)
            right = _verses_html([r], set()) if r else ""
            out.append(f'<div class="compare-row"><div class="cov">{_cov_verse(n, v, opts, first_verse)}</div>'
                       f'<div class="rsv">{right}</div></div>')
        else:
            out.append(_cov_verse(n, v, opts, first_verse))
    if opts.get("gloria", True) and (last == len(verses) or n == 119):
        out.append(gloria_html(psalter))
    out.append("</section>")
    return "\n".join(out)


def gloria_html(psalter: Psalter) -> str:
    g = psalter.gloria
    return (f'<div class="gloria"><p>{g[0]} <span class="star">*</span> {g[1]}</p>'
            f'<p>{g[2]} <span class="star">*</span> {g[3]}</p></div>')


def render_psalm_page(psalter: Psalter, n: int, opts: dict, bible: Bible | None, compare=False) -> tuple[str, dict]:
    out = ['<header class="chap-head"><div class="running-title">The Psalter · Coverdale</div>'
           f'<h1 class="chap-title">Psalm {n}</h1>']
    links = []
    if bible is not None:
        links.append(f'<a href="lectern:chapter/21/{n}">Read in the RSV-2CE &#x203A;</a>')
        links.append(f'<a href="lectern:compare/{n}/{0 if compare else 1}">'
                     f'{"Hide" if compare else "Show"} RSV-2CE alongside</a>')
    if links:
        out.append(f'<div class="crosslink">{" · ".join(links)}</div>')
    out.append("</header>")
    out.append(f'<article class="psalter{" compare" if compare else ""}">')
    out.append(render_psalm(psalter, n, opts, header=True, bible=bible, compare=compare))
    out.append("</article>")
    out.append('<nav class="pager">')
    out.append(f'<a href="lectern:coverdale/{n - 1}">&#x2039; Psalm {n - 1}</a>' if n > 1 else "<span></span>")
    if n < 150:
        out.append(f'<a href="lectern:coverdale/{n + 1}">Psalm {n + 1} &#x203A;</a>')
    out.append("</nav>")
    return "\n".join(out), {"kind": "psalter"}


def render_psalter_day(psalter: Psalter, day: int, office: str, opts: dict) -> tuple[str, dict]:
    cday = psalter.course_day(day)
    name = "Morning Prayer" if office == "morning" else "Evening Prayer"
    out = ['<header class="chap-head"><div class="running-title">The Psalter · Coverdale</div>'
           f'<h1 class="chap-title">The {ordinal(cday)} Day</h1>'
           f'<div class="subtitle">{name}</div></header>',
           '<article class="psalter">']
    for n, a, b in psalter.appointed(cday, office):
        out.append(render_psalm(psalter, n, opts, a, b))
    out.append("</article>")
    prev_day, prev_off = (cday, "morning") if office == "evening" else (30 if cday == 1 else cday - 1, "evening")
    next_day, next_off = (cday, "evening") if office == "morning" else (1 if cday == 30 else cday + 1, "morning")
    lbl = {"morning": "Morning", "evening": "Evening"}
    out.append('<nav class="pager">'
               f'<a href="lectern:day/{prev_day}/{prev_off}">&#x2039; Day {prev_day}, {lbl[prev_off]}</a>'
               f'<a href="lectern:day/{next_day}/{next_off}">Day {next_day}, {lbl[next_off]} &#x203A;</a></nav>')
    return "\n".join(out), {"kind": "psalter"}


def render_canticle(psalter: Psalter, key: str, opts: dict, header=True, gloria=True) -> str:
    c = psalter.canticles[key]
    out = [f'<section class="canticle" id="c-{key}">']
    if header:
        src = f'<span class="range">{esc(c["source"])}</span>' if c["source"] else ""
        out.append(f'<div class="ps-head"><span class="ps-latin big">{esc(c["title"])}.</span>{src}</div>')
    star = '<span class="star">*</span>' if opts.get("pointing", "*") == "*" else '<span class="colon">:</span>'
    for i, (a, b) in enumerate(c["verses"]):
        a2 = _divine(a)
        if i == 0:
            m = re.match(r"^(\W*)(\w)(\w*)(.*)$", a2, re.S)
            if m:
                a2 = f'{m.group(1)}<span class="dropcap">{m.group(2)}</span><span class="lead">{m.group(3)}</span>{m.group(4)}'
        out.append(f'<p class="pv" data-cant="{key}" data-v="{i + 1}"><span class="pvt">{a2} {star} {_divine(b)}</span></p>')
    if gloria and key != "te_deum" and opts.get("gloria", True):
        out.append(gloria_html(psalter))
    out.append("</section>")
    return "\n".join(out)


def render_canticle_page(psalter: Psalter, key: str, opts: dict) -> tuple[str, dict]:
    body = ('<header class="chap-head"><div class="running-title">Canticles · Book of Common Prayer</div></header>'
            f'<article class="psalter">{render_canticle(psalter, key, opts)}</article>')
    return body, {"kind": "psalter"}


# --------------------------------------------------------------------------- Daily Office

OFFICE_CANTICLES = {
    "morning": [("First canticle", ["te_deum", "benedicite"]), ("Second canticle", ["benedictus", "jubilate"])],
    "evening": [("First canticle", ["magnificat", "cantate"]), ("Second canticle", ["nunc_dimittis", "deus_misereatur"])],
}


def render_office(psalter: Psalter, bible: Bible | None, date: _dt.date, office: str, lessons: list[str],
                  canticles: list[str], opts: dict) -> tuple[str, dict]:
    from .books import parse_ref

    day = psalter.course_day(date.day)
    name = "Morning Prayer" if office == "morning" else "Evening Prayer"
    datestr = f"{date.strftime('%A')} {date.day} {date.strftime('%B %Y')}"
    out = ['<header class="chap-head office-head">'
           f'<div class="running-title">The Daily Office</div>'
           f'<h1 class="chap-title">{name}</h1>'
           f'<div class="subtitle">{esc(datestr)}</div>'
           f'<div class="office-nav"><a href="lectern:officeday/-1">&#x2039; Previous day</a>'
           f'<a href="lectern:office/{date.isoformat()}/{"evening" if office == "morning" else "morning"}">'
           f'{"Evening" if office == "morning" else "Morning"} Prayer</a>'
           f'<a href="lectern:officeday/0">Today</a>'
           f'<a href="lectern:officeday/1">Next day &#x203A;</a></div>'
           "</header>", '<article class="psalter office">']

    if office == "morning":
        out.append('<p class="rubric">The Invitatory. <i>Except on the nineteenth day of the month, when it is read '
                   'in the course of the Psalms.</i></p>')
        if day != 19:
            out.append(render_canticle(psalter, "venite", opts))

    out.append(f'<h2 class="office-section">The Psalms</h2>'
               f'<p class="rubric">Appointed for the {ordinal(day)} day of the month, at {name}.</p>')
    for n, a, b in psalter.appointed(day, office):
        out.append(render_psalm(psalter, n, opts, a, b))

    cant_sets = OFFICE_CANTICLES[office]
    for i, title in enumerate(("The First Lesson", "The Second Lesson")):
        ref_txt = (lessons[i] if i < len(lessons) else "").strip()
        out.append(f'<h2 class="office-section">{title}</h2>')
        out.append(f'<form class="lesson-form" data-idx="{i}"><input type="text" name="ref" '
                   f'placeholder="Enter the lesson, e.g. Isaiah 40:1-11" value="{esc(ref_txt)}">'
                   f'<button type="submit">Set</button></form>')
        if ref_txt and bible is not None:
            rows = []
            for piece in re.split(r"\s*;\s*", ref_txt):
                ref = parse_ref(piece)
                if ref is None:
                    continue
                rows.extend(bible.verses_for_ref(ref))
            if rows:
                out.append(f'<div class="lesson">{render_passage(bible, rows)}</div>')
                out.append('<p class="rubric">Here endeth the '
                           f'{"First" if i == 0 else "Second"} Lesson.</p>')
            else:
                out.append('<p class="rubric">That reference could not be read. Try a form such as “Romans 8:28-39”.</p>')
        elif ref_txt and bible is None:
            out.append('<p class="rubric">Import the RSV-2CE to read the lessons here.</p>')
        label, choices = cant_sets[i]
        chosen = canticles[i] if i < len(canticles) and canticles[i] in choices else choices[0]
        opts_html = "".join(
            f'<a class="{"on" if k == chosen else ""}" href="lectern:canticle-choice/{office}/{i}/{k}">'
            f'{esc(psalter.canticles[k]["title"])}</a>' for k in choices)
        out.append(f'<div class="canticle-choice">{opts_html}</div>')
        out.append(render_canticle(psalter, chosen, opts))

    out.append('<p class="rubric office-foot">The Creed, the Prayers and the Collects follow, as appointed '
               'in <i>Divine Worship: Daily Office</i>.</p>')
    out.append("</article>")
    return "\n".join(out), {"kind": "office", "office": office, "date": date.isoformat()}


# --------------------------------------------------------------------------- search

def render_search(bible: Bible | None, psalter: Psalter, query: str, scope: str, book: int | None,
                  opts: dict) -> tuple[str, dict]:
    if scope == "psalter":
        res = psalter.search(query)
    elif bible is None:
        res = {"total": 0, "rows": [], "books": {}, "error": "Import the RSV-2CE to search the Bible."}
    else:
        res = bible.search(query, scope, book)
    out = ['<header class="search-head">',
           f'<h1 class="chap-title">Search</h1>',
           f'<form class="search-form"><input type="search" name="q" value="{esc(query)}" autofocus>'
           '<select name="scope">']
    for key, label in SCOPES:
        sel = " selected" if key == scope and not book else ""
        out.append(f'<option value="{key}"{sel}>{esc(label)}</option>')
    if book and bible is not None:
        out.append(f'<option value="book:{book}" selected>{esc(bible.book_by_id[book]["name"])}</option>')
    out.append('</select><button type="submit">Search</button></form>')
    if res.get("error"):
        out.append(f'<p class="rubric">{esc(res["error"])}</p>')
    total = res["total"]
    shown = len(res["rows"])
    what = "verse" if total == 1 else "verses"
    more = f" — showing the first {shown}; choose a book below to narrow" if shown < total else ""
    out.append(f'<p class="search-count">{total} {what}{more}</p>')
    if res["books"] and bible is not None and len(res["books"]) > 1:
        chips = "".join(
            f'<a class="chip" href="lectern:searchbook/{b}">{esc(BY_ID[b].abbr)} <span>{c}</span></a>'
            for b, c in sorted(res["books"].items()))
        out.append(f'<div class="chips">{chips}</div>')
    out.append('<p class="search-tips">Tips: all words must match · use <code>"quotes"</code> for a phrase · '
               '<code>lov*</code> for word beginnings · <code>-word</code> to exclude · <code>OR</code> for either.</p>')
    out.append("</header><ol class='results'>")
    for r in res["rows"]:
        if scope == "psalter":
            ref = f"Psalm {r['psalm']}:{r['verse']}"
            href = f"lectern:coverdale/{r['psalm']}/{r['verse']}"
        else:
            b = BY_ID[r["book"]]
            v = f"{r['verse']}–{r['verse_end']}" if r["verse_end"] > r["verse"] else str(r["verse"])
            ref = f"{b.name} {r['chapter']}:{v}" if r["verse"] else f"{b.name} {r['chapter']} (title)"
            href = f"lectern:verse/{r['id']}"
        out.append(f'<li><a class="rref" href="{href}">{esc(ref)}</a> <span class="rtext">{_divine(r["html"])}</span></li>')
    out.append("</ol>")
    return "\n".join(out), {"kind": "search"}


# --------------------------------------------------------------------------- welcome

def render_welcome(has_bible: bool) -> tuple[str, dict]:
    if has_bible:
        body = """<header class="chap-head"><h1 class="chap-title">Lectern</h1></header>"""
        return body, {}
    body = """
<header class="chap-head"><div class="running-title">Welcome</div><h1 class="chap-title">Lectern</h1>
<div class="subtitle">The Holy Bible · RSV Second Catholic Edition · with the Coverdale Psalter</div></header>
<article class="welcome">
<p>The RSV-2CE text is under copyright, so Lectern doesn't include it. It reads it once from your own copy of
the Ignatius Bible ebook (a DRM-free <code>.mobi</code> or <code>.azw</code> file) and keeps a private,
searchable copy on this computer.</p>
<p class="center"><a class="button" href="lectern:import">Import the RSV-2CE…</a></p>
<p>The Coverdale Psalter and the Prayer Book canticles are in the public domain and are included already.
You can open them from the <b>Psalter</b> tab now.</p>
</article>"""
    return body, {}
