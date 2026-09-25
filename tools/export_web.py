"""Export the imported RSV-2CE database to a compressed file for Lectern on the web.

The web version never includes the Bible text: you load this file into the browser on
each device, and it stays in that browser's storage. Keep the file private.

    python tools/export_web.py [rsv2ce.sqlite] [lectern-rsv2ce.json.gz]
"""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def default_db() -> str:
    try:
        from lectern.paths import bible_db_path
        return bible_db_path()
    except Exception:  # noqa: BLE001  (PySide6 not installed)
        return os.path.expanduser("~/.local/share/Lectern/rsv2ce.sqlite")


def export(db_path: str, out_path: str) -> None:
    db = sqlite3.connect(db_path)
    books = [list(r) for r in db.execute("SELECT id, code, name, abbr, testament, deutero, title FROM books ORDER BY id")]
    verses = [[i, b, c, v, ve, json.loads(segs), text] for i, b, c, v, ve, segs, text in
              db.execute("SELECT id, book, chapter, verse, verse_end, segs, text FROM verses ORDER BY id")]
    data = {
        "format": "lectern-web",
        "schema": 1,
        "source": dict(db.execute("SELECT key, value FROM meta")).get("source", "RSV-2CE"),
        "books": books,
        "alt": [list(r) for r in db.execute("SELECT book, chapter, alt FROM chapter_alt")],
        "verses": verses,
        "notes": {nid: [kind, h] for nid, kind, h in db.execute("SELECT id, kind, html FROM notes")},
        "verse_notes": [list(r) for r in db.execute(
            "SELECT verse_id, kind, note_id, marker FROM verse_notes ORDER BY verse_id, rowid")],
    }
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.open(out_path, "wb", compresslevel=9) as f:
        f.write(raw)
    print(f"Wrote {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB, {len(verses)} verses)")


def main(argv: list[str]) -> int:
    db_path = argv[1] if len(argv) > 1 else default_db()
    out_path = argv[2] if len(argv) > 2 else "lectern-rsv2ce.json.gz"
    if not os.path.exists(db_path):
        print(f"No imported Bible at {db_path}. Import it in Lectern first.")
        return 1
    export(db_path, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
