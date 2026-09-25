"""Format passages for the clipboard and for export (plain text, HTML, Markdown)."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from .store import Bible, Psalter, VerseRow

REF_STYLES = [
    ("after", "Reference after the text"),
    ("inline", "Reference in brackets at the end"),
    ("before", "Reference before the text"),
    ("none", "No reference"),
]


@dataclass
class CopyOptions:
    verse_numbers: bool = False
    layout: bool = True            # keep paragraph and poetry line breaks
    ref_style: str = "after"
    abbreviate: bool = False
    version: bool = True           # add "RSV-2CE" / "Coverdale" to the reference
    quotes: bool = False           # wrap the text in quotation marks
    whole_verses: bool = True      # expand a partial selection to whole verses
    pointing: str = "*"            # Psalter: "*" or ":"

    @classmethod
    def from_settings(cls, s) -> "CopyOptions":
        o = cls()
        for k, v in o.__dict__.items():
            val = s.value(f"copy/{k}", v)
            if isinstance(v, bool):
                val = val in (True, "true", "1", 1)
            o.__dict__[k] = type(v)(val)
        return o

    def save(self, s):
        for k, v in self.__dict__.items():
            s.setValue(f"copy/{k}", v)


def _clean(h: str) -> str:
    h = re.sub(r'<sup class="fn"[^>]*>.*?</sup>', "", h)
    h = re.sub(r'<span class="selah">(.*?)</span>', r" \1", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h))).strip()


def _inline_html(h: str) -> str:
    """Keep italics only."""
    h = re.sub(r'<sup class="fn"[^>]*>.*?</sup>', "", h)
    h = re.sub(r'<span class="selah">(.*?)</span>', r" <i>\1</i>", h)
    h = re.sub(r"<(?!/?i>)[^>]+>", "", h)
    return re.sub(r"\s+", " ", h).strip()


class Passage:
    """A formatted passage: a list of lines (each a list of (verse_number|None, text, html)) plus a reference."""

    def __init__(self, blocks: list[list[tuple]], reference: str, version: str = ""):
        self.blocks = blocks          # paragraphs/stanzas -> lines -> [(num, text, html), ...]
        self.reference = reference
        self.version = version        # "RSV-2CE", "Coverdale", "BCP"

    def plain(self, o: CopyOptions) -> str:
        paras = []
        for block in self.blocks:
            lines = []
            for line in block:
                parts = []
                for num, text, _ in line:
                    parts.append(f"{num} {text}" if (num and o.verse_numbers) else text)
                lines.append(" ".join(p for p in parts if p))
            paras.append(("\n" if o.layout else " ").join(l for l in lines if l))
        body = ("\n" if o.layout else " ").join(p for p in paras if p).strip()
        return _with_ref(body, self.reference, self.version, o)

    def html(self, o: CopyOptions) -> str:
        paras = []
        for block in self.blocks:
            lines = []
            for line in block:
                parts = []
                for num, _, h in line:
                    parts.append(f"<sup>{num}</sup>{h}" if (num and o.verse_numbers) else h)
                lines.append(" ".join(p for p in parts if p))
            joiner = "<br>" if o.layout else " "
            paras.append(joiner.join(l for l in lines if l))
        if o.layout:
            body = "".join(f"<p>{p}</p>" for p in paras if p)
        else:
            body = "<p>" + " ".join(p for p in paras if p) + "</p>"
        if o.quotes:
            body = re.sub(r"^<p>", "<p>“", body, count=1)
            body = re.sub(r"</p>$", "”</p>", body, count=1)
        if o.ref_style == "none" or not self.reference:
            return body
        ref = html.escape(_ref_text(self.reference, self.version, o))
        if o.ref_style == "before":
            return f"<p><b>{ref}</b></p>{body}"
        if o.ref_style == "inline":
            return re.sub(r"</p>$", f" ({ref})</p>", body)
        return f"{body}<p>— {ref}</p>"

    def markdown(self, o: CopyOptions) -> str:
        paras = []
        for block in self.blocks:
            lines = []
            for line in block:
                parts = []
                for num, _, h in line:
                    t = re.sub(r"</?i>", "*", h)
                    parts.append(f"<sup>{num}</sup>{t}" if (num and o.verse_numbers) else t)
                lines.append(" ".join(p for p in parts if p))
            paras.append(("  \n" if o.layout else " ").join(l for l in lines if l))
        body = ("\n\n" if o.layout else " ").join(p for p in paras if p)
        quoted = "\n".join("> " + l if l else ">" for l in body.split("\n"))
        if o.ref_style == "none" or not self.reference:
            return quoted
        ref = _ref_text(self.reference, self.version, o)
        if o.ref_style == "before":
            return f"**{ref}**\n\n{quoted}"
        return f"{quoted}\n>\n> — {ref}"


def _ref_text(reference: str, version: str, o: CopyOptions) -> str:
    if not (o.version and version):
        return reference
    return f"{reference} {version}" if o.ref_style == "inline" else f"{reference} ({version})"


def _with_ref(body: str, reference: str, version: str, o: CopyOptions) -> str:
    if o.quotes:
        body = f"“{body}”"
    if o.ref_style == "none" or not reference:
        return body
    ref = _ref_text(reference, version, o)
    if o.ref_style == "before":
        return f"{ref}\n{body}"
    if o.ref_style == "inline":
        return f"{body} ({ref})"
    return f"{body}\n— {ref}"


# --------------------------------------------------------------------------- builders

def bible_passage(bible: Bible, rows: list[VerseRow], o: CopyOptions, partial_text: str | None = None) -> Passage:
    ref = bible.ref_label(rows, o.abbreviate)
    if partial_text and not o.whole_verses:
        lines = [[(None, l.strip(), html.escape(l.strip()))] for l in partial_text.split("\n") if l.strip()]
        return Passage([lines], ref, "RSV-2CE")
    blocks: list[list[list]] = []
    poetry: list[bool] = []          # parallel to blocks: is this block a stanza of verse lines?
    for r in rows:
        first = True
        for kind, h in r.segs:
            if kind == "h" or (kind == "t" and r.verse != 0):
                continue
            text, hh = _clean(h), _inline_html(h)
            if not text:
                continue
            num = r.label if (first and r.verse > 0) else None
            first = False
            piece = (num, text, hh)
            if kind in ("l", "i"):
                if blocks and poetry[-1]:
                    blocks[-1].append([piece])
                else:
                    blocks.append([[piece]])
                    poetry.append(True)
            elif kind in ("p", "t") or not blocks:
                blocks.append([[piece]])
                poetry.append(False)
            else:  # continues the current paragraph or line
                blocks[-1][-1].append(piece)
    return Passage(blocks, ref, "RSV-2CE")


def psalter_passage(psalter: Psalter, keys: list[tuple[int, int]], o: CopyOptions) -> Passage:
    blocks = []
    for n, v in keys:
        _, a, b = psalter.psalms[n]["verses"][v - 1]
        sep = " * " if o.pointing == "*" else ": "
        blocks.append([[(str(v), _clean(a) + sep + _clean(b), a + sep + b)]])
    if not keys:
        return Passage([], "")
    ps = sorted({n for n, _ in keys})
    if len(ps) == 1:
        n = ps[0]
        vs = [v for _, v in keys]
        full = len(psalter.psalms[n]["verses"])
        if vs == list(range(1, full + 1)):
            ref = f"Psalm {n}"
        elif len(vs) == 1:
            ref = f"Psalm {n}:{vs[0]}"
        else:
            ref = f"Psalm {n}:{vs[0]}–{vs[-1]}"
    else:
        ref = f"Psalms {ps[0]}–{ps[-1]}"
    if o.abbreviate:
        ref = ref.replace("Psalms", "Pss").replace("Psalm", "Ps")
    # Psalter verses read as one verse per line.
    return Passage([[line for block in blocks for line in block]], ref, "Coverdale")


def canticle_passage(psalter: Psalter, key: str, verses: list[int], o: CopyOptions) -> Passage:
    c = psalter.canticles[key]
    sep = " * " if o.pointing == "*" else ": "
    lines = [[(str(i), _clean(c["verses"][i - 1][0]) + sep + _clean(c["verses"][i - 1][1]),
              c["verses"][i - 1][0] + sep + c["verses"][i - 1][1])] for i in verses]
    return Passage([lines], c["title"], "BCP")
