"""Build lectern/resources/coverdale.json from the Project Gutenberg Book of Common Prayer (#29622).

The Coverdale Psalter (as printed in the Book of Common Prayer) is in the public domain.
Run once:  python tools/build_coverdale.py [path/to/pg29622.txt]
"""
import json
import os
import re
import sys
import urllib.request

URL = "https://www.gutenberg.org/cache/epub/29622/pg29622.txt"
OUT = os.path.join(os.path.dirname(__file__), "..", "lectern", "resources", "coverdale.json")

HEBREW = ["Aleph", "Beth", "Gimel", "Daleth", "He", "Vau", "Zain", "Cheth", "Teth", "Yod", "Caph",
          "Lamed", "Mem", "Nun", "Samech", "Ain", "Pe", "Tzaddi", "Koph", "Resh", "Schin", "Tau"]

# The 1662 table: psalms appointed for each day of the month, morning and evening.
# Entries are psalm numbers, or (119, first_verse, last_verse) for portions of Psalm 119.
DAYS = {
    1: ([1, 2, 3, 4, 5], [6, 7, 8]),
    2: ([9, 10, 11], [12, 13, 14]),
    3: ([15, 16, 17], [18]),
    4: ([19, 20, 21], [22, 23]),
    5: ([24, 25, 26], [27, 28, 29]),
    6: ([30, 31], [32, 33, 34]),
    7: ([35, 36], [37]),
    8: ([38, 39, 40], [41, 42, 43]),
    9: ([44, 45, 46], [47, 48, 49]),
    10: ([50, 51, 52], [53, 54, 55]),
    11: ([56, 57, 58], [59, 60, 61]),
    12: ([62, 63, 64], [65, 66, 67]),
    13: ([68], [69, 70]),
    14: ([71, 72], [73, 74]),
    15: ([75, 76, 77], [78]),
    16: ([79, 80, 81], [82, 83, 84, 85]),
    17: ([86, 87, 88], [89]),
    18: ([90, 91, 92], [93, 94]),
    19: ([95, 96, 97], [98, 99, 100, 101]),
    20: ([102, 103], [104]),
    21: ([105], [106]),
    22: ([107], [108, 109]),
    23: ([110, 111, 112, 113], [114, 115]),
    24: ([116, 117, 118], [[119, 1, 32]]),
    25: ([[119, 33, 72]], [[119, 73, 104]]),
    26: ([[119, 105, 144]], [[119, 145, 176]]),
    27: ([120, 121, 122, 123, 124, 125], [126, 127, 128, 129, 130, 131]),
    28: ([132, 133, 134, 135], [136, 137, 138]),
    29: ([139, 140, 141], [142, 143]),
    30: ([144, 145, 146], [147, 148, 149, 150]),
}


# Transcription slips in the Gutenberg text where the colon (the mid-verse pause) was lost.
CORRECTIONS = {
    (20, 9): ("heaven; when", "heaven: when"),
    (37, 1): ("ungodly 2 neither", "ungodly: neither"),
    (72, 4): ("right; defend", "right: defend"),
    (83, 3): ("people's and", "people: and"),
    (94, 1): ("belongeth, thou God", "belongeth: thou God"),
    (118, 14): ("song i and", "song: and"),
    (135, 19): ("Israel; praise", "Israel: praise"),
    (140, 4): ("ungodly; preserve", "ungodly: preserve"),
}


CANTICLES = [
    # heading in the source, key, English title, where it comes from
    ("VENITE, EXULTEMUS DOMINO.", "venite", "Venite, exultemus Domino", "Psalm 95"),
    ("TE DEUM LAUDAMUS.", "te_deum", "Te Deum laudamus", ""),
    ("BENEDICITE, OMNIA OPERA.", "benedicite", "Benedicite, omnia opera", "The Song of the Three Children"),
    ("BENEDICTUS.", "benedictus", "Benedictus", "St Luke 1:68"),
    ("JUBILATE DEO.", "jubilate", "Jubilate Deo", "Psalm 100"),
    ("MAGNIFICAT.", "magnificat", "Magnificat", "St Luke 1:46"),
    ("CANTATE DOMINO.", "cantate", "Cantate Domino", "Psalm 98"),
    ("NUNC DIMITTIS.", "nunc_dimittis", "Nunc dimittis", "St Luke 2:29"),
    ("DEUS MISEREATUR.", "deus_misereatur", "Deus misereatur", "Psalm 67"),
]


def canticles(text: str) -> list:
    out = []
    for heading, key, title, source in CANTICLES:
        i = text.index("\n" + heading + "\n") + len(heading) + 2
        verses = []
        for para in re.split(r"\n\s*\n", text[i:]):
            p = " ".join(line.strip() for line in para.strip().splitlines()).strip()
            if not p or re.match(r"^(St |Psalm [clxvi]+\.|Luke|S\. )", p):
                continue
            if p.startswith("_") or p.startswith("Glory be to the Father") or p.isupper():
                break
            p = re.sub(r"\s+", " ", italics(p))
            first, sep, second = p.partition(": ")
            verses.append([first.strip(), second.strip()])
        assert len(verses) > 3, key
        out.append({"key": key, "title": title, "source": source, "verses": verses})
    return out


def italics(s: str) -> str:
    return re.sub(r"_([^_]+)_", r"<i>\1</i>", s)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src:
        text = open(src, encoding="utf-8").read()
    else:
        text = urllib.request.urlopen(URL).read().decode("utf-8")
    text = text.replace("\r\n", "\n")
    start = text.index("THE PSALMS OF DAVID\n\n\nDAY 1 MORNING PRAYER")
    end = text.index("FORMS OF PRAYER", start)
    body = text[start:end]

    psalms = {}
    cur = None
    section = None
    paras = [" ".join(line.strip() for line in para.strip().splitlines()).strip()
             for para in re.split(r"\n\s*\n", body)]
    while paras:
        p = paras.pop(0)
        if not p or p.startswith("THE PSALMS OF DAVID") or p.startswith("DAY "):
            continue
        m = re.match(r"^PSALM (\d+)\.?\s*(_[^_]*_\.?|[^_]*$)\s*(.*)$", p)
        if m:
            n = int(m.group(1))
            latin = re.sub(r"_|,?\s*&c\.?", "", m.group(2)).strip().rstrip(".").strip()
            if m.group(3).strip():
                paras.insert(0, m.group(3).strip())   # first verse printed on the heading line
            cur = psalms[n] = {"number": n, "latin": latin, "verses": [], "sections": []}
            if n == 119:
                section = {"start": 1, "latin": latin, "hebrew": HEBREW[0]}
                cur["sections"].append(section)
            continue
        m = re.match(r"^_?([^_:]+?)_?\.?$", p) if len(p) < 40 and ":" not in p else None
        if m and cur and cur["number"] == 119:
            section = {"start": None, "latin": m.group(1).strip().rstrip("."),
                       "hebrew": HEBREW[len(cur["sections"])]}
            cur["sections"].append(section)
            continue
        if cur is None:
            continue
        p = re.sub(r"^(\d+) (\d) (?=\D)", r"\1\2 ", p)          # "1 2 And…" -> "12 And…"
        p = re.sub(r"^(\d+)[`']", r"\1 ", p)                       # "17`They" -> "17 They"
        p = re.sub(r"^Ill will ", "11 I will ", p)                   # OCR in Psalm 42
        expect0 = (cur["verses"][-1][0] + 1) if cur["verses"] else 1
        # a paragraph holding two verses ("…altar; 7 That I may…"): split before the embedded number
        emb = re.search(r"(?<=[;:,.!?]) (%d) (?=[A-Z])" % (expect0 + 1), p)
        if emb and cur is not None:
            pending_split = p[emb.start() + 1:]
            p = p[:emb.start()]
        else:
            pending_split = None
        m = re.match(r"^(\d+)\s+(.*)$", p)
        expect = (cur["verses"][-1][0] + 1) if cur["verses"] else 1
        if m:
            num, t = int(m.group(1)), m.group(2)
            if num != expect and (str(num).startswith(str(expect)) or str(expect).startswith(str(num))):
                num = expect          # OCR slip: "161" or "1" for "16"
        elif cur["verses"] and not (section is not None and section["start"] is None):
            # a verse the transcription broke across two paragraphs
            last = cur["verses"][-1]
            joined = (last[1] + (": " + last[2] if last[2] else "") + " " + italics(p)).strip()
            first, sep, second = joined.partition(": ")
            last[1], last[2] = first.strip(), second.strip()
            continue
        else:
            num, t = expect, p
        if section is not None and section["start"] is None:
            section["start"] = num
        t = italics(t)
        first, sep, second = t.partition(": ")
        if not sep:
            first, second = t, ""
        cur["verses"].append([num, first.strip(), second.strip()])
        if pending_split:
            paras.insert(0, pending_split)

    for (n, vn), (old, new) in CORRECTIONS.items():
        v = psalms[n]["verses"][vn - 1]
        whole = (v[1] + (": " + v[2] if v[2] else "")).replace(old, new)
        assert new in whole, (n, vn)
        first, _, second = whole.partition(": ")
        v[1], v[2] = first.strip(), second.strip()
    missing = [(n, v[0]) for n, ps in psalms.items() for v in ps["verses"] if not v[2]]
    assert not missing, missing
    assert len(psalms) == 150, len(psalms)
    bad = []
    for n, ps in psalms.items():
        nums = [v[0] for v in ps["verses"]]
        if nums != list(range(1, len(nums) + 1)):
            bad.append((n, [(a, b) for a, b in zip(nums, nums[1:]) if b != a + 1]))
    assert not bad, bad
    assert len(psalms[119]["sections"]) == 22
    assert len(psalms[119]["verses"]) == 176

    out = {
        "title": "The Psalter, or Psalms of David, after the translation of Miles Coverdale",
        "source": "The Book of Common Prayer (Project Gutenberg eBook #29622); public domain",
        "gloria": ["Glory be to the Father, and to the Son", "and to the Holy Ghost;",
                   "As it was in the beginning, is now, and ever shall be", "world without end. Amen."],
        "canticles": canticles(text),
        "days": {str(d): {"morning": m, "evening": e} for d, (m, e) in DAYS.items()},
        "psalms": {str(n): psalms[n] for n in sorted(psalms)},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    print(f"wrote {OUT}: {sum(len(p['verses']) for p in psalms.values())} verses")


if __name__ == "__main__":
    main()
