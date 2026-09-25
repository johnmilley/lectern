"""Canonical book list (Catholic canon, RSV-2CE order) and reference parsing."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    id: int          # 1-based canonical order
    code: str        # short stable code
    name: str        # display name
    abbr: str        # abbreviation used in references
    testament: str   # 'OT' or 'NT'
    deutero: bool
    aliases: tuple[str, ...] = ()


_RAW = [
    # code, name, abbr, testament, deutero, aliases
    ("Gen", "Genesis", "Gen", "OT", False, ("gn", "ge")),
    ("Exod", "Exodus", "Ex", "OT", False, ("exo", "exod")),
    ("Lev", "Leviticus", "Lev", "OT", False, ("lv", "le")),
    ("Num", "Numbers", "Num", "OT", False, ("nm", "nu", "nb")),
    ("Deut", "Deuteronomy", "Deut", "OT", False, ("dt", "de")),
    ("Josh", "Joshua", "Josh", "OT", False, ("jos", "jsh", "josue")),
    ("Judg", "Judges", "Judg", "OT", False, ("jdg", "jg", "jgs")),
    ("Ruth", "Ruth", "Ruth", "OT", False, ("ru", "rth")),
    ("1Sam", "1 Samuel", "1 Sam", "OT", False, ("1 sm", "1 sa", "1 kingdoms")),
    ("2Sam", "2 Samuel", "2 Sam", "OT", False, ("2 sm", "2 sa", "2 kingdoms")),
    ("1Kgs", "1 Kings", "1 Kings", "OT", False, ("1 kgs", "1 ki", "1 kg")),
    ("2Kgs", "2 Kings", "2 Kings", "OT", False, ("2 kgs", "2 ki", "2 kg")),
    ("1Chr", "1 Chronicles", "1 Chron", "OT", False, ("1 chr", "1 ch", "1 paralipomenon", "1 par")),
    ("2Chr", "2 Chronicles", "2 Chron", "OT", False, ("2 chr", "2 ch", "2 paralipomenon", "2 par")),
    ("Ezra", "Ezra", "Ezra", "OT", False, ("ezr", "1 esdras")),
    ("Neh", "Nehemiah", "Neh", "OT", False, ("ne", "2 esdras")),
    ("Tob", "Tobit", "Tob", "OT", True, ("tb", "tobias")),
    ("Jdt", "Judith", "Jud", "OT", True, ("jdt", "jdth")),
    ("Esth", "Esther", "Esther", "OT", False, ("est", "esth", "es")),
    ("Job", "Job", "Job", "OT", False, ("jb",)),
    ("Ps", "Psalms", "Ps", "OT", False, ("psalm", "pss", "psa", "psalter")),
    ("Prov", "Proverbs", "Prov", "OT", False, ("pr", "prv", "pro")),
    ("Eccl", "Ecclesiastes", "Eccles", "OT", False, ("eccl", "ecc", "qoh", "qoheleth", "ec")),
    ("Song", "Song of Solomon", "Song", "OT", False,
     ("song of songs", "sg", "canticle of canticles", "canticles", "cant", "sos", "ss")),
    ("Wis", "Wisdom", "Wis", "OT", True, ("wisdom of solomon", "ws")),
    ("Sir", "Sirach", "Sir", "OT", True, ("ecclesiasticus", "ecclus")),
    ("Isa", "Isaiah", "Is", "OT", False, ("isa", "isaias")),
    ("Jer", "Jeremiah", "Jer", "OT", False, ("jr", "jeremias")),
    ("Lam", "Lamentations", "Lam", "OT", False, ("la",)),
    ("Bar", "Baruch", "Bar", "OT", True, ("ba",)),
    ("Ezek", "Ezekiel", "Ezek", "OT", False, ("ez", "eze", "ezk", "ezechiel")),
    ("Dan", "Daniel", "Dan", "OT", False, ("dn", "da")),
    ("Hos", "Hosea", "Hos", "OT", False, ("ho", "osee")),
    ("Joel", "Joel", "Joel", "OT", False, ("jl",)),
    ("Amos", "Amos", "Amos", "OT", False, ("am",)),
    ("Obad", "Obadiah", "Obad", "OT", False, ("ob", "abdias")),
    ("Jonah", "Jonah", "Jon", "OT", False, ("jnh", "jonas")),
    ("Mic", "Micah", "Mic", "OT", False, ("mi", "michaeas", "micheas")),
    ("Nah", "Nahum", "Nahum", "OT", False, ("na", "nah")),
    ("Hab", "Habakkuk", "Hab", "OT", False, ("hb", "habacuc")),
    ("Zeph", "Zephaniah", "Zeph", "OT", False, ("zep", "zph", "sophonias")),
    ("Hag", "Haggai", "Hag", "OT", False, ("hg", "aggeus", "aggaeus")),
    ("Zech", "Zechariah", "Zech", "OT", False, ("zec", "zc", "zacharias")),
    ("Mal", "Malachi", "Mal", "OT", False, ("ml", "malachias")),
    ("1Macc", "1 Maccabees", "1 Mac", "OT", True, ("1 macc", "1 mc", "1 machabees", "1 ma")),
    ("2Macc", "2 Maccabees", "2 Mac", "OT", True, ("2 macc", "2 mc", "2 machabees", "2 ma")),
    ("Matt", "Matthew", "Mt", "NT", False, ("matt", "mat")),
    ("Mark", "Mark", "Mk", "NT", False, ("mrk", "mar", "mr")),
    ("Luke", "Luke", "Lk", "NT", False, ("luk", "lu")),
    ("John", "John", "Jn", "NT", False, ("jhn", "joh")),
    ("Acts", "Acts", "Acts", "NT", False, ("ac", "act", "the acts", "acts of the apostles")),
    ("Rom", "Romans", "Rom", "NT", False, ("ro", "rm")),
    ("1Cor", "1 Corinthians", "1 Cor", "NT", False, ("1 co",)),
    ("2Cor", "2 Corinthians", "2 Cor", "NT", False, ("2 co",)),
    ("Gal", "Galatians", "Gal", "NT", False, ("ga",)),
    ("Eph", "Ephesians", "Eph", "NT", False, ("ep",)),
    ("Phil", "Philippians", "Phil", "NT", False, ("php", "pp")),
    ("Col", "Colossians", "Col", "NT", False, ("co",)),
    ("1Thess", "1 Thessalonians", "1 Thess", "NT", False, ("1 th", "1 thes")),
    ("2Thess", "2 Thessalonians", "2 Thess", "NT", False, ("2 th", "2 thes")),
    ("1Tim", "1 Timothy", "1 Tim", "NT", False, ("1 ti", "1 tm")),
    ("2Tim", "2 Timothy", "2 Tim", "NT", False, ("2 ti", "2 tm")),
    ("Titus", "Titus", "Tit", "NT", False, ("ti",)),
    ("Phlm", "Philemon", "Philem", "NT", False, ("phm", "phlm", "philem")),
    ("Heb", "Hebrews", "Heb", "NT", False, ("he",)),
    ("Jas", "James", "Jas", "NT", False, ("jm", "ja")),
    ("1Pet", "1 Peter", "1 Pet", "NT", False, ("1 pt", "1 pe")),
    ("2Pet", "2 Peter", "2 Pet", "NT", False, ("2 pt", "2 pe")),
    ("1John", "1 John", "1 Jn", "NT", False, ("1 jo", "1 jhn", "1 john")),
    ("2John", "2 John", "2 Jn", "NT", False, ("2 jo", "2 jhn", "2 john")),
    ("3John", "3 John", "3 Jn", "NT", False, ("3 jo", "3 jhn", "3 john")),
    ("Jude", "Jude", "Jude", "NT", False, ("jud",)),
    ("Rev", "Revelation", "Rev", "NT", False, ("apocalypse", "apoc", "re", "rv", "revelation of john")),
]

TITLES = {
    "Gen": "The First Book of Moses, called Genesis", "Exod": "The Second Book of Moses, called Exodus",
    "Lev": "The Third Book of Moses, called Leviticus", "Num": "The Fourth Book of Moses, called Numbers",
    "Deut": "The Fifth Book of Moses, called Deuteronomy", "Josh": "The Book of Joshua",
    "Judg": "The Book of Judges", "Ruth": "The Book of Ruth", "1Sam": "The First Book of Samuel",
    "2Sam": "The Second Book of Samuel", "1Kgs": "The First Book of the Kings",
    "2Kgs": "The Second Book of the Kings", "1Chr": "The First Book of the Chronicles",
    "2Chr": "The Second Book of the Chronicles", "Ezra": "The Book of Ezra", "Neh": "The Book of Nehemiah",
    "Tob": "The Book of Tobit", "Jdt": "The Book of Judith", "Esth": "The Book of Esther",
    "Job": "The Book of Job", "Ps": "The Book of Psalms", "Prov": "The Book of Proverbs",
    "Eccl": "Ecclesiastes", "Song": "The Song of Solomon", "Wis": "The Wisdom of Solomon",
    "Sir": "The Wisdom of Jesus the Son of Sirach", "Isa": "The Book of the Prophet Isaiah",
    "Jer": "The Book of the Prophet Jeremiah", "Lam": "The Lamentations of Jeremiah",
    "Bar": "The Book of Baruch", "Ezek": "The Book of the Prophet Ezekiel", "Dan": "The Book of Daniel",
    "1Macc": "The First Book of the Maccabees", "2Macc": "The Second Book of the Maccabees",
    "Matt": "The Gospel According to Matthew", "Mark": "The Gospel According to Mark",
    "Luke": "The Gospel According to Luke", "John": "The Gospel According to John",
    "Acts": "The Acts of the Apostles", "Rom": "The Letter of Paul to the Romans",
    "1Cor": "The First Letter of Paul to the Corinthians", "2Cor": "The Second Letter of Paul to the Corinthians",
    "Gal": "The Letter of Paul to the Galatians", "Eph": "The Letter of Paul to the Ephesians",
    "Phil": "The Letter of Paul to the Philippians", "Col": "The Letter of Paul to the Colossians",
    "1Thess": "The First Letter of Paul to the Thessalonians",
    "2Thess": "The Second Letter of Paul to the Thessalonians",
    "1Tim": "The First Letter of Paul to Timothy", "2Tim": "The Second Letter of Paul to Timothy",
    "Titus": "The Letter of Paul to Titus", "Phlm": "The Letter of Paul to Philemon",
    "Heb": "The Letter to the Hebrews", "Jas": "The Letter of James", "1Pet": "The First Letter of Peter",
    "2Pet": "The Second Letter of Peter", "1John": "The First Letter of John",
    "2John": "The Second Letter of John", "3John": "The Third Letter of John", "Jude": "The Letter of Jude",
    "Rev": "The Revelation to John",
}
_MINOR = {"Hos", "Joel", "Amos", "Obad", "Jonah", "Mic", "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal"}


def book_title(code: str, name: str) -> str:
    if code in TITLES:
        return TITLES[code]
    if code in _MINOR:
        return f"The Book of the Prophet {name}"
    return name


BOOKS: list[Book] = [
    Book(i + 1, code, name, abbr, t, dc, aliases)
    for i, (code, name, abbr, t, dc, aliases) in enumerate(_RAW)
]
BY_ID = {b.id: b for b in BOOKS}
BY_CODE = {b.code: b for b in BOOKS}


def _norm(s: str) -> str:
    s = s.lower().replace(".", " ")
    s = re.sub(r"^(i{1,3})\s+", lambda m: str(len(m.group(1))) + " ", s)   # II Kings -> 2 kings
    s = re.sub(r"^(first|1st)\s+", "1 ", s)
    s = re.sub(r"^(second|2nd)\s+", "2 ", s)
    s = re.sub(r"^(third|3rd)\s+", "3 ", s)
    s = re.sub(r"^([123])\s*", r"\1 ", s)
    return re.sub(r"\s+", " ", s).strip()


_ALIASES: dict[str, Book] = {}
for _b in BOOKS:
    for _a in (_b.name, _b.abbr, _b.code, *_b.aliases):
        _ALIASES.setdefault(_norm(_a), _b)
# "Jud" is ambiguous (Judith vs Jude); prefer Judith as the RSV-2CE notes do, "jude" stays Jude.
_ALIASES["jud"] = BY_CODE["Jdt"]


def find_book(name: str) -> Book | None:
    """Resolve a book name, abbreviation or unambiguous prefix."""
    n = _norm(name)
    if not n:
        return None
    if n in _ALIASES:
        return _ALIASES[n]
    # Unique prefix match against full names and aliases.
    hits = {b.id: b for k, b in _ALIASES.items() if k.startswith(n)}
    if len(hits) == 1:
        return next(iter(hits.values()))
    # Prefer a full-name prefix match if still ambiguous (e.g. "jo" -> ambiguous, "joh" -> John).
    named = [b for b in BOOKS if _norm(b.name).startswith(n)]
    if len(named) == 1:
        return named[0]
    return None


@dataclass
class Ref:
    book: Book
    chapter: int | None = None
    verse: int | None = None
    end_chapter: int | None = None
    end_verse: int | None = None

    def label(self) -> str:
        s = self.book.name
        if self.book.code == "Ps" and self.chapter is not None and self.end_chapter in (None, self.chapter):
            s = "Psalm"
        if self.chapter is None:
            return s
        s += f" {self.chapter}"
        if self.verse is not None:
            s += f":{self.verse}"
        if self.end_chapter is not None and self.end_chapter != self.chapter:
            s += f"–{self.end_chapter}"
            if self.end_verse is not None:
                s += f":{self.end_verse}"
        elif self.end_verse is not None and self.end_verse != self.verse:
            s += f"–{self.end_verse}"
        return s


_REF_RE = re.compile(
    r"^\s*(?P<book>(?:[1-3]|i{1,3}|first|second|third)?\s*[a-z][a-z .]*?)\.?\s*"
    r"(?:(?P<c1>\d+)(?:\s*[:.,]\s*(?P<v1>\d+)[a-z]?)?"
    r"(?:\s*[-–—]\s*(?P<c2>\d+)(?:\s*[:.,]\s*(?P<v2>\d+)[a-z]?)?)?)?\s*$",
    re.I,
)


def parse_ref(text: str) -> Ref | None:
    """Parse strings like 'Jn 3:16', 'ps 23', 'Rom 8:28-39', '1 Cor 13', 'Gen 1:1-2:3'."""
    m = _REF_RE.match(text.strip())
    if not m:
        return None
    book = find_book(m.group("book"))
    if not book:
        return None
    c1 = int(m.group("c1")) if m.group("c1") else None
    v1 = int(m.group("v1")) if m.group("v1") else None
    c2 = int(m.group("c2")) if m.group("c2") else None
    v2 = int(m.group("v2")) if m.group("v2") else None
    ref = Ref(book, c1, v1)
    if c2 is not None:
        if v1 is not None and v2 is None:
            # "3:16-18" -> the second number is a verse
            ref.end_chapter, ref.end_verse = c1, c2
        elif v1 is None and v2 is None:
            ref.end_chapter = c2            # "Ps 1-3" -> chapter range
        else:
            ref.end_chapter, ref.end_verse = c2, v2
    return ref
