# Lectern

A desktop reader for the **Revised Standard Version, Second Catholic Edition (RSV-2CE)**, with the
**Coverdale Psalter** and the Prayer Book canticles, arranged for the Daily Office in the English
tradition of *Divine Worship*. It runs on Linux, Windows and macOS.

- **Read** the whole Catholic canon, laid out like a printed book: EB Garamond type, red rubrics and
  headings, small-capital LORD, drop numerals, and proper verse lines for poetry. Paper, Sepia and Night themes.
- **Notes**: the edition's footnotes, doctrinal notes and cross references appear after each chapter.
  Hover over a note mark in the text to read the note there. Cross references are links.
- **Find your place** by typing a reference in the box at the top (`Jn 3:16`, `rom 8:28-39`, `Ps 23`,
  `1 Cor 13`, `Ecclus 3`, `Apoc 21`). You can also use the book and chapter list, **←/→** to turn chapters,
  and **Alt+←/→** to go back and forward.
- **Search** the full text: all words must match, `"exact phrase"`, `forgiv*`, `-exclude`, `mercy OR compassion`.
  You can limit a search to the OT, NT, Gospels, Wisdom books, Deuterocanon, one book, or the Coverdale Psalter.
- **Copy**: click a verse number to select a verse, Shift-click another for a range, or just highlight text.
  Then press **Ctrl+C** (⌘C). The passage goes to the clipboard with its reference, as plain text for any app and
  as rich text for Word, Pages or Google Docs. You choose the format under *Preferences → Copying*: where the
  reference goes, verse numbers, line breaks, abbreviations and quotation marks.
  **Ctrl+Shift+C** copies the text alone. **Ctrl+E** opens Copy/Export for any passage, to copy it or save it
  as text, Markdown or HTML.
- **The Psalter**: all 150 psalms in Coverdale's translation, with their Latin titles and pointed with a
  red asterisk (or the Prayer Book colon). Psalm 119 is divided under its Hebrew letters. The psalms are set out
  in the monthly course, Morning and Evening for each day, with the Gloria Patri after each one. You can read
  any psalm in the RSV-2CE alongside it.
- **The Daily Office**: *Morning Prayer* (Ctrl+1) and *Evening Prayer* (Ctrl+2) for any date. Each gives the
  Venite, the psalms appointed for the day of the month, the two lessons and their canticles (Te Deum or
  Benedicite, Benedictus or Jubilate; Magnificat or Cantate, Nunc dimittis or Deus misereatur).
  Type the day's lessons from your *Divine Worship* ordo and they appear in full, in the RSV-2CE.
- **Bookmarks** (Ctrl+D). The app also remembers where you were.

## About the texts

The RSV-2CE is under copyright (© the National Council of the Churches of Christ in the USA; Ignatius Press),
so **Lectern doesn't include it**. The first time you run the app, it asks for your own copy of the
Ignatius Bible ebook, a DRM-free Kindle/Mobi file (`.mobi`, `.azw`, `.prc`). It reads the text, notes and
cross references once and keeps a private database here:

| OS | Location |
|---|---|
| Linux | `~/.local/share/Lectern/rsv2ce.sqlite` |
| Windows | `%LOCALAPPDATA%\Lectern\rsv2ce.sqlite` |
| macOS | `~/Library/Application Support/Lectern/rsv2ce.sqlite` |

The Coverdale Psalter and the canticles come from the Book of Common Prayer (public domain, via Project
Gutenberg). They are bundled in `lectern/resources/coverdale.json`, and `tools/build_coverdale.py` rebuilds that file.

*Divine Worship: Daily Office* itself (its ordinary, collects, lectionary and rubrics) is also under
copyright and is not reproduced. Lectern gives you the psalter, lessons and canticles; keep your office book
at hand for the rest.

## Running from source

Needs Python 3.10 or newer.

```sh
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m lectern
```

To import from the command line instead of through the app:

```sh
python -m lectern --import "path/to/Ignatius Bible (RSV-2CE).mobi"
```

On Linux, `packaging/linux/install-desktop-entry.sh` adds Lectern to your applications menu.

## The web version

`web/` holds a browser version of Lectern for phones, tablets and other computers. It has the same
reader, search, copying, Psalter and Daily Office. GitHub Pages publishes it on every push to `main`
(`.github/workflows/pages.yml`).

A Pages site is public, even when the repository is private. So the web version **doesn't include the RSV-2CE
either**. You load your own copy into each browser, once:

1. On the computer where you imported the ebook, run `python tools/export_web.py`. This writes
   `lectern-rsv2ce.json.gz` (about 2.4 MB). Keep it private, and don't commit it (`.gitignore` already excludes it).
2. Copy the file to the device, open the site, and choose **Load the RSV-2CE…**.

The browser keeps the text in its own storage (IndexedDB) on that device. Nothing is uploaded. The site also
works offline once it has been opened, and you can add it to your home screen. *Preferences → Remove from
this device* deletes the copy.

To try it locally:

```sh
sh tools/build_web.sh            # assembles build/web
python -m http.server -d build/web 8000
```

The web version shares `reader.css`, the fonts and `coverdale.json` with the desktop app. `web/books.js`,
`web/data.js`, `web/render.js` and `web/copy.js` port `books.py`, `store.py`, `render.py` and `copyfmt.py`,
so a change to one should go into the other too.

## Building a standalone app

Build on each platform you want to run it on (PyInstaller does not cross-compile):

```sh
pip install pyinstaller
pyinstaller packaging/lectern.spec
```

This produces `dist/Lectern/` (run `Lectern` or `Lectern.exe`), or `dist/Lectern.app` on macOS.
The bundle includes the Psalter and fonts, never the RSV-2CE text.

Build from a clean virtual environment with PySide6 installed from pip (`python -m venv build-env`,
then `pip install -r requirements.txt pyinstaller`). If PyInstaller instead picks up a Linux
distribution's own Qt packages, it also bundles the desktop's Qt and KDE libraries, and the result
can pass 900 MB.

## Keyboard

| Keys | Action |
|---|---|
| Ctrl+L | Go to a passage |
| Ctrl+F | Search |
| ← / → | Previous / next chapter (also Ctrl+[ and Ctrl+]) |
| Alt+← / Alt+→ | Back / forward |
| Ctrl+C | Copy the selection with its reference |
| Ctrl+Shift+C | Copy text only |
| Ctrl+Alt+C | Copy the reference only |
| Ctrl+A | Select the whole chapter |
| Ctrl+E | Copy or export a passage |
| Ctrl+D | Bookmark |
| Ctrl+1 / Ctrl+2 / Ctrl+3 | Morning Prayer / Evening Prayer / today's psalms |
| Ctrl+= / Ctrl+- | Larger / smaller text |
| Esc | Clear the selection |

On macOS, use ⌘ in place of Ctrl.

## Notes on the import

The ebook has a number of its own slips, and the importer repairs them. It recovers verse numbers that
were dropped or mistyped, moves chapter numbers that were printed a few words early, and restores the
chapter numbers of the Greek additions to Esther. It also puts Daniel 3 into the Catholic (Vulgate)
numbering, so the Song of the Three is 3:24–90 and the Benedicite is 3:57–88. Where the RSV itself omits
a verse (Matthew 17:21, Acts 8:37, and so on), the number is simply absent, as in print.

The importer is `lectern/importer/mobi_rsv.py`.
