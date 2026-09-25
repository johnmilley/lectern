"""Read access to the imported RSV-2CE database and the bundled Coverdale Psalter."""
from __future__ import annotations

import html
import json
import re
import sqlite3
from dataclasses import dataclass

from .books import BY_ID, Ref
from .paths import resource


@dataclass
class VerseRow:
    id: int
    book: int
    chapter: int
    verse: int
    verse_end: int
    segs: list
    text: str

    @property
    def label(self) -> str:
        if self.verse == 0:
            return "title"
        if self.verse_end > self.verse:
            return f"{self.verse}–{self.verse_end}"
        return str(self.verse)


SCOPES = [
    ("all", "Whole Bible"),
    ("ot", "Old Testament"),
    ("nt", "New Testament"),
    ("pentateuch", "Pentateuch"),
    ("history", "Historical books"),
    ("wisdom", "Wisdom books"),
    ("prophets", "Prophets"),
    ("gospels", "Gospels"),
    ("epistles", "Acts, Letters & Revelation"),
    ("deutero", "Deuterocanonical books"),
    ("psalter", "Coverdale Psalter"),
]

_SCOPE_SQL = {
    "all": "1",
    "ot": "v.book <= 46",
    "nt": "v.book >= 47",
    "pentateuch": "v.book BETWEEN 1 AND 5",
    "history": "(v.book BETWEEN 6 AND 19 OR v.book IN (45, 46))",
    "wisdom": "v.book BETWEEN 20 AND 26",
    "prophets": "v.book BETWEEN 27 AND 44",
    "gospels": "v.book BETWEEN 47 AND 50",
    "epistles": "v.book >= 51",
    "deutero": "v.book IN (17, 18, 25, 26, 30, 45, 46)",
}


def fts_query(user: str) -> str | None:
    """Turn a friendly query into FTS5 syntax.

    Supports: plain words (all must match), "exact phrases", prefix*, -excluded words, and OR.
    """
    parts = re.findall(r'-?"[^"]+"|\S+', user)
    pos: list[str] = []
    neg: list[str] = []
    pending_or = False
    for p in parts:
        if p == "OR":
            pending_or = bool(pos)
            continue
        negate = p.startswith("-") and len(p) > 1
        if negate:
            p = p[1:]
        star = p.endswith("*")
        core = p.strip('"').rstrip("*")
        core = re.sub(r"[^\w\s']", " ", core).replace("'", "").strip()
        if not core:
            continue
        term = '"' + core.replace('"', '""') + '"' + ("*" if star else "")
        if negate:
            neg.append(term)
        elif pending_or and pos:
            pos[-1] = f"({pos[-1]} OR {term})"
            pending_or = False
        else:
            pos.append(term)
    if not pos:
        return None
    q = " AND ".join(pos)
    for n in neg:
        q = f"({q}) NOT {n}"
    return q


class Bible:
    def __init__(self, path: str):
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(books)")}
        title_col = "title" if "title" in cols else "name AS title"
        self.books = [dict(r) for r in self.db.execute(f"SELECT id, name, abbr, testament, deutero, {title_col} FROM books ORDER BY id")]
        self.book_by_id = {b["id"]: b for b in self.books}
        self._chapters: dict[int, list[int]] = {}
        for r in self.db.execute("SELECT DISTINCT book, chapter FROM verses ORDER BY book, chapter"):
            self._chapters.setdefault(r[0], []).append(r[1])
        self._alt = {(r[0], r[1]): r[2] for r in self.db.execute("SELECT book, chapter, alt FROM chapter_alt")}

    # ---- navigation
    def chapters(self, book: int) -> list[int]:
        return self._chapters.get(book, [])

    def alt_number(self, book: int, chapter: int):
        return self._alt.get((book, chapter))

    def neighbour(self, book: int, chapter: int, step: int):
        seq = [(b, c) for b in sorted(self._chapters) for c in self._chapters[b]]
        try:
            i = seq.index((book, chapter))
        except ValueError:
            return None
        j = i + step
        return seq[j] if 0 <= j < len(seq) else None

    # ---- text
    def _rows(self, where: str, args=()) -> list[VerseRow]:
        rows = self.db.execute(
            f"SELECT id, book, chapter, verse, verse_end, segs, text FROM verses v WHERE {where} ORDER BY id", args)
        return [VerseRow(r["id"], r["book"], r["chapter"], r["verse"], r["verse_end"],
                         json.loads(r["segs"]), r["text"]) for r in rows]

    def chapter(self, book: int, chapter: int) -> list[VerseRow]:
        return self._rows("book = ? AND chapter = ?", (book, chapter))

    def verses_by_ids(self, ids) -> list[VerseRow]:
        ids = list(ids)
        if not ids:
            return []
        return self._rows(f"id IN ({','.join('?' * len(ids))})", ids)

    def verses_for_ref(self, ref: Ref) -> list[VerseRow]:
        b = ref.book.id
        if ref.chapter is None:
            return self._rows("book = ?", (b,))
        c1, v1 = ref.chapter, ref.verse
        c2 = ref.end_chapter if ref.end_chapter is not None else c1
        v2 = ref.end_verse
        if v1 is None:
            return self._rows("book = ? AND chapter BETWEEN ? AND ?", (b, c1, c2))
        if v2 is None:
            v2 = 10_000 if ref.end_chapter is not None and ref.end_chapter != c1 else v1
        if c1 == c2:
            return self._rows("book = ? AND chapter = ? AND verse_end >= ? AND verse <= ? AND verse > 0",
                              (b, c1, v1, v2))
        return self._rows(
            "book = ? AND verse > 0 AND (chapter > ? OR (chapter = ? AND verse_end >= ?)) "
            "AND (chapter < ? OR (chapter = ? AND verse <= ?))",
            (b, c1, c1, v1, c2, c2, v2))

    def notes_for(self, verse_ids) -> list[dict]:
        ids = list(verse_ids)
        if not ids:
            return []
        q = (f"SELECT vn.verse_id, vn.kind, vn.marker, n.id AS note_id, n.html FROM verse_notes vn "
             f"JOIN notes n ON n.id = vn.note_id WHERE vn.verse_id IN ({','.join('?' * len(ids))}) "
             f"ORDER BY vn.verse_id, vn.rowid")
        return [dict(r) for r in self.db.execute(q, ids)]

    # ---- labels
    def ref_label(self, rows: list[VerseRow], abbreviate=False) -> str:
        rows = [r for r in rows if r.verse > 0] or rows
        if not rows:
            return ""
        first, last = rows[0], rows[-1]
        b = BY_ID[first.book]
        name = b.abbr if abbreviate else b.name
        if first.book == 21 and not abbreviate:
            name = "Psalm" if first.chapter == last.chapter else "Psalms"
        end_v = max(last.verse, last.verse_end)
        whole_chapter = False
        chap_rows = [r for r in self.chapter(first.book, first.chapter) if r.verse > 0]
        if first.chapter == last.chapter and chap_rows and first.id == chap_rows[0].id and last.id == chap_rows[-1].id:
            whole_chapter = len(rows) > 1 or len(chap_rows) == 1
        if whole_chapter:
            return f"{name} {first.chapter}"
        if first.chapter == last.chapter:
            if first.verse == end_v:
                return f"{name} {first.chapter}:{first.verse}"
            return f"{name} {first.chapter}:{first.verse}–{end_v}"
        return f"{name} {first.chapter}:{first.verse}–{last.chapter}:{end_v}"

    # ---- search
    def search(self, query: str, scope: str = "all", book: int | None = None, limit: int = 400):
        q = fts_query(query)
        if not q:
            return {"total": 0, "rows": [], "books": {}, "error": None}
        where = _SCOPE_SQL.get(scope, "1")
        args: list = [q]
        if book:
            where = "v.book = ?"
            args.append(book)
        try:
            counts = {r[0]: r[1] for r in self.db.execute(
                f"SELECT v.book, count(*) FROM verses_fts f JOIN verses v ON v.id = f.rowid "
                f"WHERE verses_fts MATCH ? AND {where} GROUP BY v.book", args)}
            rows = self.db.execute(
                f"SELECT v.id, v.book, v.chapter, v.verse, v.verse_end, "
                f"highlight(verses_fts, 0, char(1), char(2)) AS hl "
                f"FROM verses_fts f JOIN verses v ON v.id = f.rowid "
                f"WHERE verses_fts MATCH ? AND {where} ORDER BY v.id LIMIT ?", args + [limit]).fetchall()
        except sqlite3.OperationalError as e:
            return {"total": 0, "rows": [], "books": {}, "error": str(e)}
        out = []
        for r in rows:
            out.append({"id": r["id"], "book": r["book"], "chapter": r["chapter"], "verse": r["verse"],
                        "verse_end": r["verse_end"], "html": marks_to_html(r["hl"])})
        return {"total": sum(counts.values()), "rows": out, "books": counts, "error": None}


def marks_to_html(s: str) -> str:
    s = html.escape(s.replace("\n", " "), quote=False)
    return s.replace("\x01", "<mark>").replace("\x02", "</mark>")


class Psalter:
    """The Coverdale Psalter and Prayer Book canticles (public domain, bundled)."""

    def __init__(self):
        with open(resource("coverdale.json"), encoding="utf-8") as f:
            self.data = json.load(f)
        self.psalms = {int(k): v for k, v in self.data["psalms"].items()}
        self.days = {int(k): v for k, v in self.data["days"].items()}
        self.canticles = {c["key"]: c for c in self.data["canticles"]}
        self.gloria = self.data["gloria"]

    @staticmethod
    def course_day(day_of_month: int) -> int:
        """1662: on the 31st the psalms of the 30th are repeated."""
        return min(day_of_month, 30)

    def appointed(self, day: int, office: str) -> list:
        """[(psalm, first_verse, last_verse)] for 'morning' or 'evening'."""
        out = []
        for e in self.days[self.course_day(day)][office]:
            if isinstance(e, list):
                out.append(tuple(e))
            else:
                out.append((e, 1, len(self.psalms[e]["verses"])))
        return out

    def day_label(self, day: int, office: str) -> str:
        parts = []
        for n, a, b in self.appointed(day, office):
            full = len(self.psalms[n]["verses"])
            parts.append(str(n) if (a, b) == (1, full) else f"{n}:{a}–{b}")
        return ", ".join(parts)

    def verse_text(self, n: int, v: int, pointing: str = "*") -> str:
        num, first, second = self.psalms[n]["verses"][v - 1]
        return f"{first} {pointing} {second}" if pointing == "*" else f"{first}: {second}"

    def search(self, query: str, limit: int = 400):
        words = [w.lower() for w in re.findall(r'"[^"]+"|\S+', query)]
        words = [w.strip('"') for w in words if not w.startswith("-")]
        if not words:
            return {"total": 0, "rows": [], "books": {}, "error": None}
        pats = [re.compile(r"\b" + re.escape(w.rstrip("*")) + (r"\w*" if w.endswith("*") else r"\b"), re.I)
                for w in words]
        out = []
        total = 0
        for n in sorted(self.psalms):
            for num, first, second in self.psalms[n]["verses"]:
                plain = re.sub(r"<[^>]+>", "", f"{first}: {second}")
                if all(p.search(plain) for p in pats):
                    total += 1
                    if len(out) < limit:
                        h = html.escape(plain, quote=False)
                        for p in pats:
                            h = p.sub(lambda m: f"<mark>{m.group(0)}</mark>", h)
                        out.append({"psalm": n, "verse": num, "html": h})
        return {"total": total, "rows": out, "books": {}, "error": None}
