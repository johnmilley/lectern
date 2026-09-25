"""Import the Ignatius Bible (RSV-2CE) Kindle/Mobi edition into a SQLite database.

The Bible text is copyrighted, so it is never shipped with this program. Each user
imports it from their own copy of the ebook. The Mobi book is converted to HTML;
this module walks that HTML and pulls out:

  * verses (with prose/poetry layout, italics and footnote markers)
  * section headings and psalm titles (stored inline with the verse they precede)
  * the three note sets in that edition (exegetical footnotes, doctrinal notes
    and parallel-passage cross references)
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser

from ..books import BOOKS, BY_ID, book_title

# --------------------------------------------------------------------------- DOM


class Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict):
        self.tag = tag
        self.attrs = attrs
        self.children: list = []

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


class _Builder(HTMLParser):
    VOID = {"br", "mbp:pagebreak", "img", "hr", "meta"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs))
        self.stack[-1].children.append(n)
        if tag not in self.VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(src: str) -> Node:
    b = _Builder()
    b.feed(src)
    b.close()
    return b.root


def _flat_blocks(root: Node):
    """Yield the top-level stream: block nodes (p/blockquote/div) and bare anchors."""
    for c in root.children:
        if isinstance(c, str):
            continue
        if c.tag in ("p", "blockquote"):
            yield c
        elif c.tag == "a" and "id" in c.attrs:
            yield c
        elif c.tag in ("html", "body", "div", "root"):
            yield from _flat_blocks(c)
        elif c.tag == "mbp:pagebreak":
            yield c


def _fp(href: str | None) -> str | None:
    if href and href.startswith("#filepos"):
        return href[1:]
    return None


# --------------------------------------------------------------------------- tokens

@dataclass
class Tok:
    kind: str           # TEXT CHAP VERSE FN DOC XREF ANCHOR SPACER BR
    value: str = ""
    italic: bool = False
    selah: bool = False
    href: str | None = None
    alt: str | None = None
    white: bool = False


def _inline_tokens(node: Node, ctx: dict | None = None, out: list | None = None) -> list[Tok]:
    if ctx is None:
        ctx = {}
    if out is None:
        out = []
    for c in node.children:
        if isinstance(c, str):
            _text_token(c, ctx, out)
            continue
        t = c.tag
        if t == "a" and "id" in c.attrs and not c.children:
            out.append(Tok("ANCHOR", c.attrs["id"]))
            continue
        if t == "br":
            out.append(Tok("BR"))
            continue
        sub = dict(ctx)
        if t == "a":
            sub["href"] = _fp(c.attrs.get("href"))
            if "id" in c.attrs:
                out.append(Tok("ANCHOR", c.attrs["id"]))
        elif t == "sup":
            if c.text() == "":
                # An empty superscript where the ebook dropped a verse number.
                for a in _find_all(c, "a"):
                    if "id" in a.attrs:
                        out.append(Tok("ANCHOR", a.attrs["id"]))
                out.append(Tok("VERSE", "?"))
                continue
            sub["sup"] = True
        elif t in ("b", "strong"):
            sub["bold"] = True
        elif t in ("i", "em"):
            sub["italic"] = True
        elif t == "font":
            if c.attrs.get("size") == "5":
                sub["big"] = True
            col = c.attrs.get("color")
            if col:
                sub["color"] = col
        _inline_tokens(c, sub, out)
    return out


_DIGITS = re.compile(r"^\s*(\d+)\s*$")
_CHAPNUM = re.compile(r"^\s*(\d+)\s*(?:\[\s*(\d+)\s*\])?\s*$")   # "19[18]" (Hebrew[Greek] psalm numbers)
_SUPNUM = re.compile(r"^[\s>.]*(\d+)(?:\s*[,–-]\s*(\d+))?\s*$")     # "12", ">53", "7, 8"
_BRACKET = re.compile(r"^\s*\[\s*(\d+)\s*\]\s*$")


def _text_token(s: str, ctx: dict, out: list):
    color = ctx.get("color")
    href = ctx.get("href")
    m = _DIGITS.match(s)
    if color == "white" and not (m and ctx.get("sup")):
        return   # white text is layout padding; white verse numbers still count
    if color == "red" and href and 0 < len(s.strip()) <= 2:
        out.append(Tok("FN", s.strip(), href=href))
        return
    if ctx.get("sup"):
        sm = _SUPNUM.match(s)
        if sm:
            out.append(Tok("VERSE", sm.group(1), href=href, white=color == "white", alt=sm.group(2)))
        elif not s.strip():
            out.append(Tok("SPACER"))
        else:
            out.append(Tok("TEXT", s, italic=bool(ctx.get("italic"))))
        return
    if ctx.get("big"):
        cm = _CHAPNUM.match(s)
        bm = _BRACKET.match(s)
        if bm:
            out.append(Tok("ALT", bm.group(1)))
        elif cm and ctx.get("bold"):
            out.append(Tok("CHAP", cm.group(1), href=href, alt=cm.group(2)))
        elif s.strip() == "*":
            out.append(Tok("DOC", href=href))
        elif s.strip():
            out.append(Tok("TEXT", s, italic=bool(ctx.get("italic"))))
        return
    if _BRACKET.match(s) and not ctx.get("bold"):
        return   # "[115]": Greek psalm number printed mid-psalm
    if s.strip() == "*" and href:
        out.append(Tok("DOC", href=href))
        return
    if ctx.get("bold"):
        if m:
            out.append(Tok("VERSE", m.group(1), href=href))
            return
        bm = _BRACKET.match(s)
        if bm:   # "[13]" – chapter number of a Greek addition (Esther)
            out.append(Tok("CHAP", bm.group(1), href=href))
            return
    out.append(Tok("TEXT", s, italic=bool(ctx.get("italic")),
                   selah=(color == "blue" and s.strip() == "Selah")))


# --------------------------------------------------------------------------- model

@dataclass
class Verse:
    book: int
    chapter: int
    verse: int
    segs: list = field(default_factory=list)      # [[kind, html], ...]
    notes: list = field(default_factory=list)     # [(kind, note_id, marker)]
    from_chap: bool = False                        # started by a chapter number (verse 1 implied)
    verse_end: int = 0                             # for combined verses printed "7, 8"

    def add_seg(self, kind: str):
        self.segs.append([kind, ""])

    def append(self, s: str):
        if not self.segs or self.segs[-1][0] == "h":
            self.add_seg("c")
        self.segs[-1][1] += s

    def is_empty(self) -> bool:
        return not any(_strip_tags(h).strip() for k, h in self.segs if k != "h")


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def _plain(segs, lines=True) -> str:
    out = []
    for kind, h in segs:
        if kind == "h":
            continue
        t = html.unescape(re.sub(r'<sup class="fn"[^>]*>.*?</sup>', "", h))
        t = _strip_tags(t).strip()
        if not t:
            continue
        if out and kind in ("l", "i", "t") and lines:
            out.append("\n")
        elif out:
            out.append(" ")
        out.append(t)
    return re.sub(r"[ \t]+", " ", "".join(out)).strip()


# --------------------------------------------------------------------------- importer

class RSVImporter:
    def __init__(self, html_src: str, log=print):
        self.src = html_src
        self.log = log
        self.root = parse_html(html_src)
        self.stream = list(_flat_blocks(self.root))
        self.anchor_to_verse: dict[str, Verse] = {}
        self.verses: list[Verse] = []
        self.notes: dict[str, dict] = {}
        self.chapter_alt: dict[tuple[int, int], int] = {}
        self._synthetic = 0

    # ---- locate regions via the contents page
    def _toc(self):
        """Return [(title, filepos_id)] from the front table of contents."""
        toc = []
        for n in self.stream:
            if n.tag != "p":
                continue
            if n.text().strip() == "Chapters":
                break   # reached the first book's chapter index
            for a in _find_all(n, "a"):
                fp = _fp(a.attrs.get("href"))
                if fp:
                    toc.append((a.text().strip(), fp))
        return toc

    def run(self):
        toc = self._toc()
        titles = [t for t, _ in toc]
        skip = {"THE OLD TESTAMENT", "THE NEW TESTAMENT", "Abbreviations in the Notes"}
        note_entries = {t: fp for t, fp in toc if t in ("Parallel Notes", "Doctrinal Notes", "Exegetical Notes")}
        book_entries = [(t, fp) for t, fp in toc if t not in skip and t not in note_entries]
        if len(book_entries) != len(BOOKS):
            raise ValueError(f"Expected {len(BOOKS)} books in the contents, found {len(book_entries)}: {titles}")

        index = {}
        for i, n in enumerate(self.stream):
            if n.tag == "a" and "id" in n.attrs:
                index.setdefault(n.attrs["id"], i)
            elif isinstance(n, Node):
                for a in _find_all(n, "a"):
                    if "id" in a.attrs:
                        index.setdefault(a.attrs["id"], i)
        starts = [index[fp] for _, fp in book_entries]
        text_end = index[note_entries["Parallel Notes"]]
        for bi, book in enumerate(BOOKS):
            s = starts[bi]
            e = starts[bi + 1] if bi + 1 < len(starts) else text_end
            self._parse_book(book.id, self.stream[s:e])

        notes_order = sorted(note_entries.items(), key=lambda kv: index[kv[1]])
        kinds = {"Parallel Notes": "xref", "Doctrinal Notes": "doc", "Exegetical Notes": "fn"}
        for i, (title, fp) in enumerate(notes_order):
            s = index[fp]
            e = index[notes_order[i + 1][1]] if i + 1 < len(notes_order) else len(self.stream)
            self._parse_notes(kinds[title], self.stream[s:e])

    # ---- book text
    def _parse_book(self, book_id: int, blocks):
        # Skip the book's front page: everything up to and including the chapter index.
        for i, n in enumerate(blocks):
            if n.tag == "p" and _is_link_list(n):
                blocks = blocks[i + 1:]
                break

        # First pass: turn blocks into typed token lists.
        items = []   # ('heading', text) | ('anchor', id) | ('block', tokens, node, info)
        for n in blocks:
            if n.tag == "a":
                items.append(("anchor", n.attrs["id"]))
                continue
            if n.tag == "mbp:pagebreak":
                continue
            if n.attrs.get("align") == "center":
                txt = re.sub(r"\s+", " ", n.text()).strip()
                for a in _find_all(n, "a"):
                    if "id" in a.attrs:
                        items.append(("anchor", a.attrs["id"]))
                if txt and _has_color(n, "blue"):
                    items.append(("heading", txt))
                continue
            toks = _inline_tokens(n)
            plain = "".join(t.value for t in toks if t.kind == "TEXT")
            first = next((t for t in toks if t.kind != "ANCHOR"
                          and not (t.kind == "TEXT" and not t.value.strip())), None)
            first_txt = next((t.value for t in toks if t.kind == "TEXT" and t.value.strip()), "")
            info = {
                "lead_ws": first is not None and first.kind == "TEXT" and first_txt[:1].isspace(),
                "lower": bool(re.match(r"^[\s“‘\"'(]*[a-z]", first_txt)),
                "numbered": first is not None and first.kind in ("CHAP", "VERSE", "DOC", "ALT"),
                "spacer": first is not None and first.kind == "SPACER" and next(
                    (t.kind for t in toks[toks.index(first) + 1:] if t.kind not in ("ANCHOR", "SPACER")), "") == "TEXT",
                "has_num": any(t.kind in ("CHAP", "VERSE") for t in toks),
                "len": len(plain.strip()),
                "quote": n.tag == "blockquote",
                "narrow": n.attrs.get("width") == "0pt",
            }
            items.append(("block", toks, n, info))

        # Classify blocks as prose paragraphs or poetry lines.
        infos = [it[3] for it in items if it[0] == "block"]
        for b in infos:
            b["cont"] = not b["numbered"] and not b["spacer"]
        for i, b in enumerate(infos):
            short = b["len"] < 140
            nxt = infos[i + 1] if i + 1 < len(infos) else None
            poetry = b["quote"] or b["spacer"] or (short and (
                b["cont"] or b["narrow"] or (nxt is not None and nxt["cont"] and nxt["len"] < 140)))
            if not poetry:
                b["kind"] = "p"
            elif b["spacer"]:
                b["kind"] = "l"
            elif b["lead_ws"] or b["lower"]:
                b["kind"] = "i"    # clause continuing a sentence: indent
            else:
                b["kind"] = "l"

        # Second pass: assemble verses.
        book_verses: list[Verse] = []
        chapter = 0
        cur: Verse | None = None
        pending: list[list] = []        # headings and unattached text waiting for a home
        pending_anchors: list[str] = []

        def start_verse(ch: int, v: int) -> Verse:
            nonlocal cur
            vv = Verse(book_id, ch, v)
            book_verses.append(vv)
            cur = vv
            return vv

        def flush_anchors(target: Verse | None):
            nonlocal pending_anchors
            if target is not None:
                for a in pending_anchors:
                    self.anchor_to_verse[a] = target
            pending_anchors = []

        def flush_pending_into(target: Verse):
            nonlocal pending
            for p in pending:
                target.segs.append(p)
            pending = []

        def pending_has_text() -> bool:
            return any(p[0] != "h" for p in pending)

        for it in items:
            if it[0] == "anchor":
                pending_anchors.append(it[1])
                continue
            if it[0] == "heading":
                pending.append(["h", html.escape(it[1], quote=False)])
                continue
            toks, node, b = it[1], it[2], it[3]
            kind = b["kind"]

            if not b["has_num"] and (cur is None or pending):
                # Unnumbered text after a heading: a psalm title or prologue for what follows,
                # or the tail of the previous verse (decided when the next number arrives).
                seg = ["t", ""]
                for t in toks:
                    if t.kind == "ANCHOR":
                        pending_anchors.append(t.value)
                    elif t.kind == "TEXT":
                        seg[1] += _fmt_text(t)
                    elif t.kind == "FN" and t.href:
                        seg[1] += f'<sup class="fn" data-note="{t.href}">{html.escape(t.value)}</sup>'
                        seg.append(("fn", t.href, t.value))
                    elif t.kind == "BR":
                        seg[1] += " "
                if _strip_tags(seg[1]).strip():
                    seg.append(kind)
                    pending.append(seg)
                continue

            new_block = True
            first_text = True
            for t in toks:
                k = t.kind
                if k == "ANCHOR":
                    pending_anchors.append(t.value)
                    continue
                if k == "SPACER":
                    continue
                if k == "ALT":
                    if cur is not None:
                        self.chapter_alt[(book_id, cur.chapter)] = int(t.value)
                    continue
                if k == "CHAP":
                    chapter = int(t.value)
                    if t.alt:
                        self.chapter_alt[(book_id, chapter)] = int(t.alt)
                    if pending_has_text():
                        # psalm title / book prologue becomes verse 0 of this chapter
                        v0 = start_verse(chapter, 0)
                        for p in pending:
                            v0.segs.append(p[:2])
                            v0.notes.extend(x for x in p[2:] if isinstance(x, tuple))
                        pending = []
                        flush_anchors(v0)
                    v = start_verse(chapter, 1)
                    v.from_chap = True
                    flush_pending_into(v)
                    flush_anchors(v)
                    if t.href:
                        v.notes.append(("xref", t.href, ""))
                    v.add_seg(kind if new_block else "c")
                    new_block = False
                    continue
                if k == "VERSE":
                    if t.value == "?":
                        if cur is None or cur.chapter != chapter:
                            continue
                        vnum = cur.verse + 1
                    else:
                        vnum = int(t.value)
                    if cur is not None and cur.chapter == chapter and (
                            (vnum == cur.verse and not cur.from_chap and new_block)
                            or (t.white and vnum != cur.verse + 1)):
                        continue   # repeated or hidden number used only to indent a line
                    if pending_has_text() and cur is not None:
                        # text after a mid-chapter heading finishes the previous verse
                        for p in pending:
                            if p[0] == "h":
                                cur.segs.append(p)
                            else:
                                cur.segs.append([p[-1] if isinstance(p[-1], str) and p[-1] in "pli" else "p", p[1]])
                                cur.notes.extend(x for x in p[2:] if isinstance(x, tuple))
                        pending = []
                    if (vnum == 1 and cur is not None and cur.from_chap and cur.chapter == chapter
                            and cur.verse == 1 and len(book_verses) > 1):
                        # Chapter number set a few words early ("7 Pharaoh listen to me?” 1 And the LORD…"):
                        # the words before verse 1 finish the previous chapter's last verse.
                        prev = book_verses[-2]
                        for sk, sh in cur.segs:
                            if sk != "h" and _strip_tags(sh).strip():
                                prev.segs.append(["c", sh])
                        prev.notes.extend(n for n in cur.notes if n[0] == "fn")
                        cur.notes = [n for n in cur.notes if n[0] != "fn"]
                        cur.segs = [s for s in cur.segs if s[0] == "h"]
                        cur.from_chap = False
                        cur.add_seg(kind if new_block else "c")
                        v = cur
                    elif cur is not None and cur.chapter == chapter and cur.from_chap and cur.is_empty() and vnum != 1:
                        # chapter number immediately followed by a later verse number (Esther additions)
                        cur.verse = vnum
                        cur.from_chap = False
                        v = cur
                    else:
                        if cur is None:
                            chapter = chapter or 1
                        v = start_verse(chapter, vnum)
                        flush_pending_into(v)
                        v.add_seg(kind if new_block else "c")
                    if t.alt:
                        v.verse_end = int(t.alt)
                    flush_anchors(v)
                    if t.href:
                        v.notes.append(("xref", t.href, ""))
                    new_block = False
                    first_text = False
                    continue
                if cur is None:
                    if k == "TEXT" and t.value.strip():
                        pending.append(["t", _fmt_text(t), kind])
                    continue
                if k == "TEXT" and first_text and new_block and t.value.strip():
                    # a bare "47 " typed at the start of a paragraph instead of a marked-up number
                    mnum = re.match(r"^\s*(\d+)\s+", t.value)
                    if mnum and int(mnum.group(1)) == cur.verse + 1:
                        v = start_verse(chapter, int(mnum.group(1)))
                        flush_pending_into(v)
                        flush_anchors(v)
                        v.add_seg(kind)
                        new_block = False
                        t = Tok("TEXT", t.value[mnum.end():], italic=t.italic)
                if k == "TEXT" and t.value.strip():
                    first_text = False
                flush_anchors(cur)
                if pending:
                    flush_pending_into(cur)
                    if not new_block:
                        cur.add_seg("c")
                if new_block:
                    cur.add_seg(kind)
                    new_block = False
                if k == "TEXT":
                    cur.append(_fmt_text(t))
                elif k == "BR":
                    cur.add_seg("l")
                elif k == "FN":
                    if t.href:
                        cur.notes.append(("fn", t.href, t.value))
                        cur.append(f'<sup class="fn" data-note="{t.href}">{html.escape(t.value)}</sup>')
                elif k == "DOC":
                    if t.href:
                        cur.notes.append(("doc", t.href, "*"))
        if cur is not None and pending:
            for p in pending:
                cur.segs.append(p[:2] if p[0] == "h" else ["p", p[1]])
        flush_anchors(cur)

        _fix_numbering(book_id, book_verses)
        self.verses.extend(book_verses)

    # ---- notes
    def _parse_notes(self, kind: str, blocks):
        cur_id = None
        fresh = False          # an anchor has been seen since the last paragraph
        for n in blocks:
            if n.tag == "a" and "id" in n.attrs:
                cur_id, fresh = n.attrs["id"], True
                continue
            if n.tag != "p":
                continue
            inner_ids = [a.attrs["id"] for a in _find_all(n, "a") if "id" in a.attrs]
            if inner_ids:
                cur_id, fresh = inner_ids[0], True
            text = n.text().strip()
            # Some entries have no anchor of their own; start a new note for them anyway.
            starts_entry = (kind == "doc" and text.startswith("*")) or (
                kind == "xref" and re.match(r"^[1-3]?\s?[A-Z][a-z]*\.? \d+:\d+", text) is not None)
            if starts_entry and not fresh:
                self._synthetic += 1
                cur_id = f"{kind}{self._synthetic}"
            fresh = False
            if cur_id is None:
                continue
            body = self._note_html(n, kind).strip()
            if not body:
                continue
            note = self.notes.setdefault(cur_id, {"kind": kind, "html": []})
            note["html"].append(body)
            if "target" not in note:
                links = [_fp(a.attrs.get("href")) for a in _find_all(n, "a")]
                back = [h for a, h in zip(_find_all(n, "a"), links) if a.text().strip().lower().startswith("back to")]
                for h in (back or links[:1]):
                    if h and h in self.anchor_to_verse:
                        note["target"] = self.anchor_to_verse[h]
                        break

    def _note_html(self, node: Node, kind: str) -> str:
        out = []

        def walk(n: Node, italic=False):
            for c in n.children:
                if isinstance(c, str):
                    out.append(html.escape(c, quote=False))
                    continue
                t = c.tag
                if t == "sup" and kind == "fn":
                    continue  # the note letter itself
                if t == "a":
                    href = _fp(c.attrs.get("href"))
                    label = c.text()
                    if label.strip().lower().startswith("back to text"):
                        continue
                    target = self.anchor_to_verse.get(href) if href else None
                    if target:
                        out.append(f'<a href="ref:{target.book}.{target.chapter}.{max(target.verse, 1)}">{html.escape(label)}</a>')
                    else:
                        walk(c, italic)
                    continue
                if t in ("i", "em"):
                    out.append("<i>")
                    walk(c, True)
                    out.append("</i>")
                    continue
                if t in ("b", "strong"):
                    out.append("<b>")
                    walk(c, italic)
                    out.append("</b>")
                    continue
                walk(c, italic)

        walk(node)
        s = "".join(out)
        s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"<b>\s*</b>", "", s)
        s = re.sub(r"^\*\s*", "", s)
        s = re.sub(r"\s*\.\s*$", ".", s) if kind == "xref" else s
        return s

    # ---- output
    def write_db(self, path: str):
        if os.path.exists(path):
            os.remove(path)
        con = sqlite3.connect(path)
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT INTO books(id, code, name, abbr, testament, deutero, title) VALUES (?,?,?,?,?,?,?)",
            [(b.id, b.code, b.name, b.abbr, b.testament, int(b.deutero), book_title(b.code, b.name))
             for b in BOOKS],
        )
        used_notes = set()
        rows = []
        note_rows = []
        carry: list = []    # headings of a dropped (empty) verse move to the next one
        for seq, v in enumerate(self.verses, 1):
            segs = carry + [[k, re.sub(r"\s+", " ", h).strip()] for k, h in v.segs if _strip_tags(h).strip()]
            carry = []
            if v.is_empty() and v.verse != 0:
                carry = [sg for sg in segs if sg[0] == "h"]
                continue
            if not segs:
                continue
            plain = _plain(segs)
            search = re.sub(r"(?<=\w)'(?=\w)", "", plain)   # Melchiz'edek -> Melchizedek
            rows.append((seq, v.book, v.chapter, v.verse, max(v.verse, v.verse_end), json.dumps(segs, ensure_ascii=False), plain, search))
            for kind, nid, marker in v.notes:
                if nid in self.notes:
                    note_rows.append((seq, kind, nid, marker))
                    used_notes.add(nid)
        con.executemany("INSERT INTO verses(id, book, chapter, verse, verse_end, segs, text, search) VALUES (?,?,?,?,?,?,?,?)", rows)
        # Notes the text doesn't point to (entries without an anchor) hang on the verse they refer back to.
        seq_of = {id(v): seq for seq, v in enumerate(self.verses, 1)}
        written = {r[0] for r in rows}
        for nid, n in self.notes.items():
            t = n.get("target")
            if nid in used_notes or t is None or seq_of.get(id(t)) not in written:
                continue
            note_rows.append((seq_of[id(t)], n["kind"], nid, "*" if n["kind"] == "doc" else ""))
            used_notes.add(nid)
        note_rows.sort(key=lambda r: r[0])
        con.executemany("INSERT INTO verse_notes(verse_id, kind, note_id, marker) VALUES (?,?,?,?)", note_rows)
        con.executemany(
            "INSERT INTO notes(id, kind, html) VALUES (?,?,?)",
            [(nid, n["kind"], "<br>".join(n["html"])) for nid, n in self.notes.items() if nid in used_notes],
        )
        con.executemany("INSERT INTO chapter_alt(book, chapter, alt) VALUES (?,?,?)",
                        [(b, c, a) for (b, c), a in self.chapter_alt.items()])
        con.execute("INSERT INTO verses_fts(verses_fts) VALUES ('rebuild')")
        con.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", [
            ("source", "The Ignatius Bible (RSV-2CE), Ignatius Press"),
            ("schema", str(SCHEMA_VERSION)),
        ])
        con.commit()
        con.execute("VACUUM")
        con.close()
        return len(rows)


SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE books(id INTEGER PRIMARY KEY, code TEXT, name TEXT, abbr TEXT, testament TEXT, deutero INTEGER,
                   title TEXT);   -- the edition's full title, e.g. "The Gospel According to John"
CREATE TABLE verses(
    id INTEGER PRIMARY KEY,         -- reading order
    book INTEGER, chapter INTEGER, verse INTEGER,
    verse_end INTEGER,              -- same as verse unless the edition prints a combined number ("7, 8")
    segs TEXT,                      -- JSON [[kind, html], ...]: h=heading p=paragraph l=line i=indented line c=continue t=title
    text TEXT,                      -- plain text (poetry lines separated by newlines)
    search TEXT                     -- normalised text for full-text search
);
CREATE INDEX verses_ref ON verses(book, chapter, verse);
CREATE TABLE chapter_alt(book INTEGER, chapter INTEGER, alt INTEGER);  -- Greek/Vulgate psalm numbers
CREATE TABLE notes(id TEXT PRIMARY KEY, kind TEXT, html TEXT);
CREATE TABLE verse_notes(verse_id INTEGER, kind TEXT, note_id TEXT, marker TEXT);
CREATE INDEX verse_notes_v ON verse_notes(verse_id);
CREATE VIRTUAL TABLE verses_fts USING fts5(search, content='verses', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2");
"""


def _fix_numbering(book_id: int, vs: list[Verse]):
    """Repair numbering slips in the ebook and apply Catholic numbering to Daniel 3."""
    code = BY_ID[book_id].code
    if code == "Dan":
        _daniel3(vs)

    while _fix_pass(code, vs):
        pass   # a verse was split off; scan again


def _fix_pass(code: str, vs: list[Verse]) -> bool:
    idx = [j for j in range(len(vs)) if vs[j].verse > 0]
    for n, i in enumerate(idx):
        if n == 0 or n + 1 >= len(idx):
            continue
        v, prev, nxt = vs[i], vs[idx[n - 1]], vs[idx[n + 1]]
        if v.from_chap or v.chapter != prev.chapter or v.verse == max(prev.verse, prev.verse_end) + 1:
            continue
        # A verse number standing in for a missing chapter number ("16 And the Pharisees…", then 2, 3…)
        if v.verse == prev.chapter + 1 and nxt.chapter == v.chapter and nxt.verse == 2:
            old, new = v.chapter, v.verse
            v.verse, v.from_chap = 1, True
            for w in vs[i:]:
                if w is not v and w.from_chap:
                    break
                if w.chapter == old:
                    w.chapter = new
            continue
        # A misprinted number between two good ones (…22, 1, 24… -> 23; …14, 16, 16… -> 15)
        if nxt.chapter == v.chapter and (nxt.verse == prev.verse + 2
                                         or (nxt.verse == v.verse == prev.verse + 2)):
            v.verse = prev.verse + 1
            continue
        # A paragraph whose verse number the ebook dropped: split it off the verse before.
        if v.verse == prev.verse + 2 and prev.verse_end < v.verse - 1:
            def starts_like(a, b):   # parallel lines such as the Beatitudes ("“Blessed are…")
                a, b = a.strip(), b.strip()
                return a[:1] == "“" and b.startswith(a.split()[0])
            first_txt = _strip_tags(next((sg[1] for sg in prev.segs if sg[0] != "h" and sg[1].strip()), ""))
            cut = max((k for k, sg in enumerate(prev.segs) if k > 0 and _strip_tags(sg[1]).strip() and (
                       sg[0] == "p" or (sg[0] in "li" and starts_like(first_txt, _strip_tags(sg[1]))))),
                      default=None)
            if cut is not None and any(sg[0] not in ("h",) and _strip_tags(sg[1]).strip()
                                       for sg in prev.segs[:cut]):
                nv = Verse(prev.book, prev.chapter, prev.verse + 1, segs=prev.segs[cut:])
                prev.segs = prev.segs[:cut]
                fn_ids = set(re.findall(r'data-note="([^"]+)"', "".join(sg[1] for sg in nv.segs)))
                nv.notes = [x for x in prev.notes if x[1] in fn_ids]
                prev.notes = [x for x in prev.notes if x[1] not in fn_ids]
                vs.insert(i, nv)
                return True
        # Back to the Hebrew text after an Esther addition, without a chapter number.
        if code == "Esth":
            last: dict[int, int] = {}
            for w in vs[:i]:
                if w.chapter != v.chapter and w.verse > 0:
                    last[w.chapter] = w.verse
            cands = [c for c, lv in last.items() if lv == v.verse - 1]
            if cands:
                # the most recently seen such chapter
                target = max(cands, key=lambda c: max(k for k, w in enumerate(vs[:i]) if w.chapter == c))
                old = v.chapter
                prevnum = v.verse - 1
                for w in vs[i:]:
                    if w.from_chap or w.chapter != old or w.verse < prevnum:
                        break
                    prevnum = w.verse
                    w.chapter = target
    return False


def _daniel3(vs: list[Verse]):
    """The ebook numbers the Prayer of Azariah and Song of the Three 1–68 inside Dan 3, then resumes
    at 24. Renumber to the Catholic (Vulgate/NABRE) scheme: 3:24–90 for the Greek text, 3:91–97 after."""
    ch3 = [v for v in vs if v.chapter == 3]
    start = next((k for k in range(1, len(ch3)) if ch3[k].verse == 1 and ch3[k - 1].verse == 23), None)
    if start is None:
        return
    k = start
    orig_prev = 0
    while k < len(ch3) and ch3[k].verse == orig_prev + 1:
        n = orig_prev = ch3[k].verse
        if n <= 29:
            ch3[k].verse = n + 23
        elif n == 30:
            # v.30 ("And blessed is your glorious, holy name") is part of 3:52 in the Vulgate
            prev = ch3[k - 1]
            prev.segs.extend(ch3[k].segs)
            prev.notes.extend(ch3[k].notes)
            ch3[k].verse = -1   # dropped below
        else:
            ch3[k].verse = n + 22
        k += 1
    for w in ch3[k:]:
        if w.verse >= 24:
            w.verse += 67
    vs[:] = [w for w in vs if w.verse != -1]


# --------------------------------------------------------------------------- helpers

def _find_all(n: Node, tag: str):
    for c in n.children:
        if isinstance(c, str):
            continue
        if c.tag == tag:
            yield c
        yield from _find_all(c, tag)


def _has_color(n: Node, color: str) -> bool:
    return any(f.attrs.get("color") == color for f in _find_all(n, "font"))


def _is_link_list(n: Node) -> bool:
    links = list(_find_all(n, "a"))
    if not links:
        return False
    txt = n.text()
    return all(re.fullmatch(r"[\d\s]*", a.text()) for a in links) and re.fullmatch(r"[\d\s]+", txt) is not None


def _fmt_text(t: Tok) -> str:
    s = html.escape(t.value, quote=False)
    if t.selah:
        return f' <span class="selah">{s.strip()}</span>'
    if t.italic and s.strip():
        return f"<i>{s}</i>"
    return s


# --------------------------------------------------------------------------- entry points

def extract_mobi_html(mobi_path: str) -> str:
    """Unpack a (DRM-free) .mobi/.azw file and return its HTML."""
    import mobi  # type: ignore

    tmpdir, path = mobi.extract(mobi_path)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def import_file(src_path: str, db_path: str, log=print) -> int:
    if src_path.lower().endswith((".html", ".htm")):
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
    else:
        log("Unpacking ebook…")
        src = extract_mobi_html(src_path)
    log("Reading the text…")
    imp = RSVImporter(src, log=log)
    imp.run()
    log("Writing the database…")
    tmp = db_path + ".tmp"
    n = imp.write_db(tmp)
    os.replace(tmp, db_path)
    log(f"Imported {n} verses and {len(imp.notes)} notes.")
    return n


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m lectern.importer.mobi_rsv <book.mobi|book.html> <out.sqlite>")
        sys.exit(2)
    import_file(sys.argv[1], sys.argv[2])
