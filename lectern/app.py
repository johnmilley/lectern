"""Lectern: the RSV-2CE and the Coverdale Psalter, for reading, searching and copying."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys

from PySide6.QtCore import QByteArray, QMimeData, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QCompleter, QDockWidget, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QToolBar, QWidget, QSizePolicy)

from . import __version__
from .books import BY_ID, BOOKS, find_book, parse_ref
from .copyfmt import CopyOptions, bible_passage, canticle_passage, psalter_passage
from .paths import APP_NAME, ORG_NAME, bible_db_path, resource
from .render import (page, render_canticle_page, render_chapter, render_office, render_psalm_page,
                     render_psalter_day, render_search, render_welcome)
from .store import Bible, Psalter
from .ui.dialogs import (ExportDialog, ImportDialog, PreferencesDialog, ShortcutsDialog, bool_setting)
from .ui.navigator import Navigator
from .ui.reader import Reader


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.psalter = Psalter()
        self.bible: Bible | None = None
        self.history: list[dict] = []
        self.hist_idx = -1
        self.loc: dict = {"t": "welcome"}
        self.selected_keys: list[str] = []
        self.top_key = ""

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource("icon.svg")))
        self.reader = Reader(self)
        self.setCentralWidget(self.reader)
        self.reader.linkClicked.connect(self.open_link)
        self.reader.bridge.navigateRequested.connect(self.open_link)
        self.reader.bridge.copyRequested.connect(self.copy_payload)
        self.reader.bridge.selectionChanged_.connect(self._selection_changed)
        self.reader.bridge.scrolledTo.connect(self._scrolled)
        self.reader.bridge.lessonSet.connect(self._set_lesson)
        self.reader.bridge.searchRequested.connect(lambda q, sc: self.search(q, sc))
        self.reader.contextMenuWanted.connect(self._context_menu)

        self.nav = Navigator(self.psalter)
        self.nav.locationChosen.connect(self.go)
        self.nav.bookmarkRemoved.connect(self._remove_bookmark)
        dock = QDockWidget("Contents", self)
        dock.setObjectName("contents")
        dock.setWidget(self.nav)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.nav_dock = dock

        self._build_actions()
        self._build_toolbar()
        self._build_menus()
        self.statusBar()

        self.load_bible()
        self.nav.set_bookmarks(self.bookmarks())

        geo = self.settings.value("window/geometry")
        if isinstance(geo, QByteArray):
            self.restoreGeometry(geo)
        else:
            self.resize(1180, 820)
        state = self.settings.value("window/state")
        if isinstance(state, QByteArray):
            self.restoreState(state)

        last = self.settings.value("nav/last")
        start = None
        if last:
            try:
                start = json.loads(last)
            except ValueError:
                start = None
        if start is None or (start.get("t") == "chapter" and self.bible is None):
            start = {"t": "chapter", "book": 50, "chapter": 1} if self.bible else {"t": "welcome"}
        if start.get("t") == "search":
            start = {"t": "chapter", "book": 50, "chapter": 1} if self.bible else {"t": "welcome"}
        self.go(start)

        # Keep "today" current if the app is left open overnight.
        self._today = _dt.date.today()
        self._day_timer = QTimer(self)
        self._day_timer.timeout.connect(self._check_day)
        self._day_timer.start(60_000)

    # ------------------------------------------------------------------ setup
    def _act(self, text, slot, shortcut=None, tip=None, checkable=False, checked=False):
        a = QAction(text, self)
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        if checkable:
            a.setCheckable(True)
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.addAction(a)
        return a

    def _build_actions(self):
        S = QKeySequence.StandardKey
        self.a_back = self._act("Back", self.back, [QKeySequence(S.Back), "Alt+Left"], "Go back")
        self.a_fwd = self._act("Forward", self.forward, [QKeySequence(S.Forward), "Alt+Right"], "Go forward")
        self.a_prev = self._act("Previous Chapter", lambda: self.step(-1), ["Ctrl+[", "Ctrl+PgUp"], "Previous chapter")
        self.a_next = self._act("Next Chapter", lambda: self.step(1), ["Ctrl+]", "Ctrl+PgDown"], "Next chapter")
        self.a_goto = self._act("Go to Passage…", self.focus_goto, "Ctrl+L", "Type a reference such as Jn 3:16")
        self.a_find = self._act("Search…", self.focus_search, QKeySequence(S.Find), "Search the Bible")
        self.a_copy = self._act("Copy", lambda: self.copy_selection("default"), None,
                                "Copy the selected passage with its reference")
        self.a_copy_plain = self._act("Copy Text Only", lambda: self.copy_selection("plain"), "Ctrl+Shift+C")
        self.a_copy_nums = self._act("Copy with Verse Numbers", lambda: self.copy_selection("numbers"))
        self.a_copy_ref = self._act("Copy Reference", lambda: self.copy_selection("ref"), "Ctrl+Alt+C")
        self.a_export = self._act("Copy or Export Passage…", self.export, "Ctrl+E",
                                  "Copy or save any passage as text, Markdown or HTML")
        self.a_select_all = self._act("Select Whole Chapter", lambda: self.reader.run("App.selectAllVerses()"),
                                      QKeySequence(S.SelectAll))
        self.a_bookmark = self._act("Bookmark This Passage", self.add_bookmark, "Ctrl+D")
        self.a_import = self._act("Import RSV-2CE…", self.import_bible, None,
                                  "Import the Bible text from your Ignatius RSV-2CE ebook")
        self.a_prefs = self._act("Preferences…", self.preferences, QKeySequence(S.Preferences) if sys.platform == "darwin" else "Ctrl+,")
        self.a_quit = self._act("Quit", self.close, QKeySequence(S.Quit))
        self.a_bigger = self._act("Larger Text", lambda: self.zoom(1), [QKeySequence(S.ZoomIn), "Ctrl+="])
        self.a_smaller = self._act("Smaller Text", lambda: self.zoom(-1), QKeySequence(S.ZoomOut))
        self.a_morning = self._act("Morning Prayer", lambda: self.go({"t": "office", "date": "today", "office": "morning"}),
                                   "Ctrl+1", "Today's Morning Prayer")
        self.a_evening = self._act("Evening Prayer", lambda: self.go({"t": "office", "date": "today", "office": "evening"}),
                                   "Ctrl+2", "Today's Evening Prayer")
        self.a_psalms_today = self._act("Today's Psalms", self.todays_psalms, "Ctrl+3",
                                        "The psalms appointed for today (Coverdale)")
        self.a_shortcuts = self._act("Keyboard Shortcuts & Tips", lambda: ShortcutsDialog(self).exec(), "F1")
        self.a_about = self._act("About Lectern", self.about)

    def _build_toolbar(self):
        tb = QToolBar("Navigation", self)
        tb.setObjectName("navbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)
        self.a_back.setText("‹ Back")
        self.a_fwd.setText("Forward ›")
        tb.addAction(self.a_back)
        tb.addAction(self.a_fwd)
        tb.addSeparator()
        self.omni = QLineEdit()
        self.omni.setPlaceholderText("Go to a passage (Jn 3:16, Ps 23) or search for words…")
        self.omni.setClearButtonEnabled(True)
        self.omni.setMinimumWidth(320)
        self.omni.returnPressed.connect(self._omni_enter)
        names = sorted({b.name for b in BOOKS} | {b.abbr for b in BOOKS})
        comp = QCompleter(names, self)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        self.omni.setCompleter(comp)
        tb.addWidget(self.omni)
        tb.addSeparator()
        self.a_prev.setText("‹ Chapter")
        self.a_next.setText("Chapter ›")
        tb.addAction(self.a_prev)
        tb.addAction(self.a_next)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.a_morning)
        tb.addAction(self.a_evening)
        tb.addSeparator()
        copy_btn = QAction("Copy", self)
        copy_btn.setToolTip("Copy the selected verses with their reference (Ctrl+C)")
        copy_btn.triggered.connect(lambda: self.copy_selection("default"))
        tb.addAction(copy_btn)
        tb.addAction(self.a_export)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        m.addAction(self.a_import)
        m.addAction(self.a_export)
        m.addSeparator()
        m.addAction(self.a_prefs)
        m.addSeparator()
        m.addAction(self.a_quit)

        m = mb.addMenu("&Edit")
        self.a_copy.setText("Copy\tCtrl+C")
        m.addAction(self.a_copy)
        m.addAction(self.a_copy_plain)
        m.addAction(self.a_copy_nums)
        m.addAction(self.a_copy_ref)
        m.addSeparator()
        m.addAction(self.a_select_all)
        m.addAction(self.a_export)
        m.addSeparator()
        m.addAction(self.a_find)

        m = mb.addMenu("&View")
        self.theme_actions = {}
        for key, label in (("paper", "Paper"), ("sepia", "Sepia"), ("night", "Night")):
            a = QAction(label, self, checkable=True)
            a.setChecked(self.settings.value("view/theme", "paper") == key)
            a.triggered.connect(lambda _=False, k=key: self.set_view("theme", k))
            m.addAction(a)
            self.theme_actions[key] = a
        m.addSeparator()
        m.addAction(self.a_bigger)
        m.addAction(self.a_smaller)
        m.addSeparator()
        self.view_toggles = {}
        for key, label, default in (("verse_numbers", "Verse Numbers", True), ("headings", "Section Headings", True),
                                    ("fn_markers", "Footnote Markers", True),
                                    ("endnotes", "Notes && Cross References", True),
                                    ("red", "Red Rubrics", True), ("gloria", "Gloria Patri after Psalms", True)):
            a = QAction(label, self, checkable=True)
            a.setChecked(bool_setting(self.settings, f"view/{key}", default))
            a.toggled.connect(lambda on, k=key: self.set_view(k, on))
            m.addAction(a)
            self.view_toggles[key] = a
        m.addSeparator()
        m.addAction(self.nav_dock.toggleViewAction())

        m = mb.addMenu("&Go")
        for a in (self.a_back, self.a_fwd, None, self.a_goto, self.a_find, None, self.a_prev, self.a_next):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Office")
        m.addAction(self.a_morning)
        m.addAction(self.a_evening)
        m.addAction(self.a_psalms_today)
        m.addSeparator()
        cm = m.addMenu("Canticles")
        for key, c in self.psalter.canticles.items():
            a = cm.addAction(c["title"])
            a.triggered.connect(lambda _=False, k=key: self.go({"t": "canticle", "key": k}))

        m = mb.addMenu("&Bookmarks")
        m.addAction(self.a_bookmark)

        m = mb.addMenu("&Help")
        m.addAction(self.a_shortcuts)
        m.addAction(self.a_about)

    # ------------------------------------------------------------------ data
    def load_bible(self):
        path = bible_db_path()
        self.bible = None
        if os.path.exists(path):
            try:
                self.bible = Bible(path)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, APP_NAME, f"The imported Bible couldn't be opened:\n{e}\n\nPlease import it again.")
        self.nav.set_bible(self.bible)
        for a in (self.a_prev, self.a_next, self.a_find):
            a.setEnabled(True)

    def import_bible(self):
        if ImportDialog(self).exec():
            self.load_bible()
            self.go({"t": "chapter", "book": 1, "chapter": 1})

    def opts(self) -> dict:
        s = self.settings
        o = {"theme": s.value("view/theme", "paper"), "font_size": int(s.value("view/font_size", 20)),
             "pointing": s.value("view/pointing", "*")}
        for key in ("verse_numbers", "headings", "fn_markers", "endnotes", "red", "gloria"):
            o[key] = bool_setting(s, f"view/{key}", True)
        return o

    def set_view(self, key, value):
        self.settings.setValue(f"view/{key}", value)
        if key == "theme":
            for k, a in self.theme_actions.items():
                a.setChecked(k == value)
        self.refresh()

    def zoom(self, step: int):
        size = max(12, min(40, int(self.settings.value("view/font_size", 20)) + step))
        self.settings.setValue("view/font_size", size)
        self.reader.run(f"document.documentElement.style.setProperty('--fs', '{size}px')")
        self.statusBar().showMessage(f"Text size {size}px", 1500)

    # ------------------------------------------------------------------ navigation
    def go(self, loc: dict, push: bool = True):
        loc = dict(loc)
        if loc.get("t") == "office" and loc.get("date") == "today":
            loc["date"] = _dt.date.today().isoformat()
        if push:
            if 0 <= self.hist_idx < len(self.history):
                self.history[self.hist_idx]["scroll"] = self.top_key   # remember where we were
            self.history = self.history[: self.hist_idx + 1]
            self.history.append(loc)
            self.hist_idx = len(self.history) - 1
        self.loc = loc
        self.top_key = ""
        self.render()
        self.a_back.setEnabled(self.hist_idx > 0)
        self.a_fwd.setEnabled(self.hist_idx < len(self.history) - 1)
        if loc.get("t") != "search":
            persist = {k: v for k, v in loc.items() if k not in ("select", "scroll", "flash")}
            self.settings.setValue("nav/last", json.dumps(persist))

    def back(self):
        if self.hist_idx > 0:
            self.history[self.hist_idx]["scroll"] = self.top_key
            self.hist_idx -= 1
            self.go(self.history[self.hist_idx], push=False)

    def forward(self):
        if self.hist_idx < len(self.history) - 1:
            self.history[self.hist_idx]["scroll"] = self.top_key
            self.hist_idx += 1
            self.go(self.history[self.hist_idx], push=False)

    def refresh(self):
        keep = self.top_key
        loc = dict(self.loc)
        if keep:
            loc["scroll"] = keep
        self.loc = loc
        self.render()

    def step(self, delta: int):
        t = self.loc.get("t")
        if t == "chapter" and self.bible:
            nb = self.bible.neighbour(self.loc["book"], self.loc["chapter"], delta)
            if nb:
                self.go({"t": "chapter", "book": nb[0], "chapter": nb[1]})
        elif t == "coverdale":
            n = self.loc["n"] + delta
            if 1 <= n <= 150:
                self.go({"t": "coverdale", "n": n, "compare": self.loc.get("compare", False)})
        elif t == "day":
            d, o = self.loc["day"], self.loc["office"]
            if delta > 0:
                d, o = (d, "evening") if o == "morning" else (d % 30 + 1, "morning")
            else:
                d, o = (d, "morning") if o == "evening" else ((d - 2) % 30 + 1, "evening")
            self.go({"t": "day", "day": d, "office": o})
        elif t == "office":
            date = _dt.date.fromisoformat(self.loc["date"]) + _dt.timedelta(days=delta)
            self.go({"t": "office", "date": date.isoformat(), "office": self.loc["office"]})

    def render(self):
        loc, o = self.loc, self.opts()
        t = loc.get("t")
        after: list[str] = []
        title = APP_NAME
        try:
            if t == "chapter" and self.bible:
                body, data = render_chapter(self.bible, loc["book"], loc["chapter"], o)
                name = self.bible.book_by_id[loc["book"]]["name"]
                title = f"Psalm {loc['chapter']}" if loc["book"] == 21 else f"{name} {loc['chapter']}"
                self.nav.show_chapters(loc["book"], loc["chapter"])
                if loc.get("select"):
                    keys = [f"b:{i}" for i in loc["select"]]
                    after.append(f"App.selectKeys({json.dumps(keys)}, {json.dumps(not loc.get('scroll'))})")
                if loc.get("flash"):
                    after.append(f"App.scrollToKey('b:{loc['flash']}', true, false)")
            elif t == "coverdale":
                body, data = render_psalm_page(self.psalter, loc["n"], o, self.bible, loc.get("compare", False))
                title = f"Psalm {loc['n']} (Coverdale)"
                if loc.get("v"):
                    after.append(f"App.scrollToKey('p:{loc['n']}:{loc['v']}', true, false)")
            elif t == "day":
                body, data = render_psalter_day(self.psalter, loc["day"], loc["office"], o)
                title = f"Psalter, Day {loc['day']} {loc['office'].title()}"
            elif t == "canticle":
                body, data = render_canticle_page(self.psalter, loc["key"], o)
                title = self.psalter.canticles[loc["key"]]["title"]
            elif t == "office":
                date = _dt.date.fromisoformat(loc["date"])
                lessons, cants = self._office_state(date, loc["office"])
                body, data = render_office(self.psalter, self.bible, date, loc["office"], lessons, cants, o)
                title = ("Morning" if loc["office"] == "morning" else "Evening") + " Prayer"
            elif t == "search":
                body, data = render_search(self.bible, self.psalter, loc["q"], loc.get("scope", "all"),
                                           loc.get("book"), o)
                title = f"Search: {loc['q']}"
            else:
                body, data = render_welcome(self.bible is not None)
        except (KeyError, IndexError, ValueError):
            body, data = render_welcome(self.bible is not None)
        if loc.get("scroll"):
            after.append(f"App.scrollToKey({json.dumps(loc['scroll'])}, false, false)")
        self.reader.show_html(page(body, o, title, data), after)
        self.setWindowTitle(f"{title} — {APP_NAME}")
        self.selected_keys = []
        self.omni.setPlaceholderText(f"{title} — go to a passage or search…" if t != "welcome"
                                     else "Go to a passage (Jn 3:16, Ps 23) or search for words…")

    def open_link(self, href: str):
        path = href.split(":", 1)[1] if ":" in href else href
        parts = [p for p in path.split("/") if p]
        if not parts:
            return
        kind, args = parts[0], parts[1:]
        try:
            if kind == "chapter":
                self.go({"t": "chapter", "book": int(args[0]), "chapter": int(args[1])})
            elif kind == "verse" and self.bible:
                rows = self.bible.verses_by_ids([int(args[0])])
                if rows:
                    r = rows[0]
                    if self.loc.get("t") == "chapter" and (self.loc["book"], self.loc["chapter"]) == (r.book, r.chapter):
                        self.reader.run(f"App.scrollToKey('b:{r.id}', true, false)")
                    else:
                        self.go({"t": "chapter", "book": r.book, "chapter": r.chapter, "flash": r.id})
            elif kind == "ref" and self.bible:
                b, c, v = int(args[0]), int(args[1]), int(args[2])
                rows = self.bible._rows("book = ? AND chapter = ? AND verse_end >= ? AND verse <= ?", (b, c, v, v))
                if rows:
                    self.go({"t": "chapter", "book": b, "chapter": c, "flash": rows[0].id})
                else:
                    self.go({"t": "chapter", "book": b, "chapter": c})
            elif kind == "coverdale":
                loc = {"t": "coverdale", "n": int(args[0])}
                if len(args) > 1:
                    loc["v"] = int(args[1])
                self.go(loc)
            elif kind == "compare":
                self.go({"t": "coverdale", "n": int(args[0]), "compare": args[1] == "1"})
            elif kind == "day":
                self.go({"t": "day", "day": int(args[0]), "office": args[1]})
            elif kind == "office":
                self.go({"t": "office", "date": args[0], "office": args[1]})
            elif kind == "officeday":
                delta = int(args[0])
                if delta == 0:
                    date = _dt.date.today()
                else:
                    date = _dt.date.fromisoformat(self.loc.get("date", _dt.date.today().isoformat())) + _dt.timedelta(days=delta)
                self.go({"t": "office", "date": date.isoformat(), "office": self.loc.get("office", "morning")})
            elif kind == "canticle-choice":
                office, idx, key = args[0], int(args[1]), args[2]
                self.settings.setValue(f"office/canticle/{office}/{idx}", key)
                self.refresh()
            elif kind == "searchbook":
                self.go({"t": "search", "q": self.loc.get("q", ""), "scope": "all", "book": int(args[0])})
            elif kind == "import":
                self.import_bible()
            elif kind == "prev":
                self.step(-1)
            elif kind == "next":
                self.step(1)
        except (IndexError, ValueError):
            pass

    # ------------------------------------------------------------------ omnibox & search
    def focus_goto(self):
        self.omni.setFocus()
        self.omni.selectAll()

    def focus_search(self):
        if self.loc.get("t") == "search":
            self.reader.setFocus()
            self.reader.run("document.querySelector('.search-form input')?.select()")
            return
        self.omni.setFocus()
        self.omni.selectAll()

    def _omni_enter(self):
        text = self.omni.text().strip()
        if not text:
            return
        self.omni.clear()
        self.reader.setFocus()
        if text[0] in "?/":
            self.search(text[1:].strip())
            return
        if self.go_text(text):
            return
        self.search(text)

    def go_text(self, text: str) -> bool:
        """Go to a reference; returns False if the text isn't one."""
        m = re.match(r"^(?:cov(?:erdale)?|bcp)\s*(?:ps(?:alm)?\s*)?(\d{1,3})(?:\s*[:.]\s*(\d+))?$", text, re.I)
        if m and 1 <= int(m.group(1)) <= 150:
            loc = {"t": "coverdale", "n": int(m.group(1))}
            if m.group(2):
                loc["v"] = int(m.group(2))
            self.go(loc)
            return True
        m = re.match(r"^day\s*(\d{1,2})\s*(morning|evening|am|pm|m|e)?$", text, re.I)
        if m and 1 <= int(m.group(1)) <= 31:
            off = (m.group(2) or "morning").lower()
            self.go({"t": "day", "day": Psalter.course_day(int(m.group(1))),
                     "office": "evening" if off in ("evening", "pm", "e") else "morning"})
            return True
        ref = parse_ref(text)
        if ref is None:
            return False
        if self.bible is None:
            if ref.book.code == "Ps" and ref.chapter:
                self.go({"t": "coverdale", "n": ref.chapter, **({"v": ref.verse} if ref.verse else {})})
                return True
            QMessageBox.information(self, APP_NAME, "Import the RSV-2CE first (File → Import RSV-2CE…).")
            return True
        chapters = self.bible.chapters(ref.book.id)
        if not chapters:
            return False
        if ref.chapter is None:
            self.go({"t": "chapter", "book": ref.book.id, "chapter": chapters[0]})
            return True
        if ref.chapter not in chapters:
            self.statusBar().showMessage(f"{ref.book.name} has no chapter {ref.chapter}", 4000)
            return True
        if ref.verse is None and ref.end_chapter in (None, ref.chapter):
            self.go({"t": "chapter", "book": ref.book.id, "chapter": ref.chapter})
            return True
        rows = self.bible.verses_for_ref(ref)
        ids = [r.id for r in rows if r.chapter == ref.chapter] or [r.id for r in rows]
        self.go({"t": "chapter", "book": ref.book.id, "chapter": ref.chapter, "select": ids})
        if len(rows) > len(ids):
            self.statusBar().showMessage(f"{self.bible.ref_label(rows)}: continues into the next chapter — "
                                         "use Copy/Export (Ctrl+E) for the whole passage", 6000)
        return True

    def search(self, q: str, scope: str = "all"):
        q = q.strip()
        if not q:
            return
        book = None
        if scope.startswith("book:"):
            book = int(scope.split(":")[1])
            scope = "all"
        self.go({"t": "search", "q": q, "scope": scope, "book": book})

    # ------------------------------------------------------------------ selection & copying
    def _selection_changed(self, keys: list):
        self.selected_keys = keys
        if keys:
            n = len(keys)
            label = self._label_for_keys(keys)
            self.statusBar().showMessage(f"{label} selected — Ctrl+C to copy, right-click for more" if label
                                         else f"{n} selected")
        else:
            self.statusBar().clearMessage()

    def _scrolled(self, key: str):
        self.top_key = key

    def _label_for_keys(self, keys: list) -> str:
        bkeys = [int(k[2:]) for k in keys if k.startswith("b:")]
        if bkeys and self.bible:
            return self.bible.ref_label(self.bible.verses_by_ids(bkeys))
        pkeys = [tuple(map(int, k[2:].split(":"))) for k in keys if k.startswith("p:")]
        if pkeys:
            return psalter_passage(self.psalter, pkeys, CopyOptions()).reference
        return ""

    def copy_selection(self, mode: str = "default"):
        self.reader.run(f"App.requestCopy({json.dumps(mode)}) || false", lambda ok: None if ok else
                        self.statusBar().showMessage("Select some verses first: click a verse number, or highlight text", 4000))

    def copy_payload(self, info: dict):
        keys = info.get("keys") or []
        mode = info.get("mode", "default")
        partial = info.get("text") or ""
        o = CopyOptions.from_settings(self.settings)
        if mode == "plain":
            o.ref_style = "none"
            o.verse_numbers = False
        elif mode == "numbers":
            o.verse_numbers = True
        passage = None
        bkeys = [int(k[2:]) for k in keys if k.startswith("b:")]
        pkeys = [tuple(map(int, k[2:].split(":"))) for k in keys if k.startswith("p:")]
        ckeys = [k[2:].split(":") for k in keys if k.startswith("c:")]
        if bkeys and self.bible:
            rows = self.bible.verses_by_ids(bkeys)
            passage = bible_passage(self.bible, rows, o, partial_text=partial if info.get("partial") else None)
        elif pkeys:
            o.pointing = self.opts()["pointing"] if o.pointing == "*" else o.pointing
            passage = psalter_passage(self.psalter, pkeys, o)
            if info.get("partial") and not o.whole_verses and partial:
                passage.blocks = [[[(None, l, l)] for l in partial.split("\n") if l.strip()]]
        elif ckeys:
            key = ckeys[0][0]
            passage = canticle_passage(self.psalter, key, [int(v) for k, v in ckeys if k == key], o)
        if passage is None:
            if partial:
                self.put_on_clipboard(partial, None)
                self.statusBar().showMessage("Copied", 2000)
            return
        if mode == "ref":
            ref = passage.reference + (f" ({passage.version})" if o.version and passage.version else "")
            self.put_on_clipboard(ref, None)
            self.statusBar().showMessage(f"Copied “{ref}”", 3000)
            return
        self.put_on_clipboard(passage.plain(o), passage.html(o))
        self.statusBar().showMessage(f"Copied {passage.reference}", 3000)

    def put_on_clipboard(self, plain: str, html_text: str | None):
        md = QMimeData()
        md.setText(plain)
        if html_text:
            md.setHtml(f"<meta charset='utf-8'><div style=\"font-family:'EB Garamond',Garamond,Georgia,serif\">{html_text}</div>")
        QApplication.clipboard().setMimeData(md)

    def export(self):
        initial = ""
        psalter_keys = None
        if self.selected_keys:
            if all(k.startswith("p:") for k in self.selected_keys):
                psalter_keys = [tuple(map(int, k[2:].split(":"))) for k in self.selected_keys]
            else:
                initial = self._label_for_keys(self.selected_keys)
        elif self.loc.get("t") == "chapter" and self.bible:
            b = BY_ID[self.loc["book"]]
            initial = f"{b.name} {self.loc['chapter']}"
        ExportDialog(self, initial, psalter_keys).exec()

    def _context_menu(self, info: dict, pos):
        m = QMenu(self)
        has = bool(info.get("keys") or info.get("text"))
        for a in (self.a_copy, self.a_copy_nums, self.a_copy_plain, self.a_copy_ref):
            a.setEnabled(has)
        self.a_copy.setText("Copy")
        m.addAction(self.a_copy)
        m.addAction(self.a_copy_nums)
        m.addAction(self.a_copy_plain)
        m.addAction(self.a_copy_ref)
        m.addSeparator()
        m.addAction(self.a_export)
        if self.loc.get("t") in ("chapter", "coverdale", "day", "canticle"):
            m.addAction(self.a_select_all)
        m.addSeparator()
        word = (info.get("text") or "").strip()
        if word and len(word) < 40 and "\n" not in word:
            a = m.addAction(f"Search for “{word}”")
            a.triggered.connect(lambda: self.search(f'"{word}"' if " " in word else word))
        m.addAction(self.a_bookmark)
        m.exec(pos)
        self.a_copy.setText("Copy\tCtrl+C")
        for a in (self.a_copy, self.a_copy_nums, self.a_copy_plain, self.a_copy_ref):
            a.setEnabled(True)

    # ------------------------------------------------------------------ office
    def _office_state(self, date: _dt.date, office: str):
        lessons = json.loads(self.settings.value(f"office/lessons/{date.isoformat()}/{office}", "[]") or "[]")
        cants = [self.settings.value(f"office/canticle/{office}/{i}", "") for i in range(2)]
        return lessons, cants

    def _set_lesson(self, idx: int, ref: str):
        if self.loc.get("t") != "office":
            return
        key = f"office/lessons/{self.loc['date']}/{self.loc['office']}"
        lessons = json.loads(self.settings.value(key, "[]") or "[]")
        while len(lessons) <= idx:
            lessons.append("")
        lessons[idx] = ref.strip()
        self.settings.setValue(key, json.dumps(lessons))
        self.refresh()

    def todays_psalms(self):
        hour = _dt.datetime.now().hour
        self.go({"t": "day", "day": Psalter.course_day(_dt.date.today().day),
                 "office": "morning" if hour < 14 else "evening"})

    def _check_day(self):
        if _dt.date.today() != self._today:
            self._today = _dt.date.today()
            self.nav.refresh_today()

    # ------------------------------------------------------------------ bookmarks
    def bookmarks(self) -> list[dict]:
        try:
            return json.loads(self.settings.value("bookmarks", "[]") or "[]")
        except ValueError:
            return []

    def add_bookmark(self):
        loc = {k: v for k, v in self.loc.items() if k not in ("scroll", "flash")}
        label = self.windowTitle().replace(f" — {APP_NAME}", "")
        if self.selected_keys:
            lab = self._label_for_keys(self.selected_keys)
            if lab:
                label = lab
            bkeys = [int(k[2:]) for k in self.selected_keys if k.startswith("b:")]
            if bkeys:
                loc["select"] = bkeys
        marks = self.bookmarks()
        marks.append({"label": label, "loc": loc, "added": _dt.date.today().isoformat()})
        self.settings.setValue("bookmarks", json.dumps(marks))
        self.nav.set_bookmarks(marks)
        self.statusBar().showMessage(f"Bookmarked {label}", 3000)

    def _remove_bookmark(self, row: int):
        marks = self.bookmarks()
        if 0 <= row < len(marks):
            del marks[row]
            self.settings.setValue("bookmarks", json.dumps(marks))
            self.nav.set_bookmarks(marks)

    # ------------------------------------------------------------------ misc
    def preferences(self):
        if PreferencesDialog(self.settings, self).exec():
            for k, a in self.view_toggles.items():
                a.blockSignals(True)
                a.setChecked(bool_setting(self.settings, f"view/{k}", True))
                a.blockSignals(False)
            theme = self.settings.value("view/theme", "paper")
            for k, a in self.theme_actions.items():
                a.setChecked(k == theme)
            self.refresh()

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}", f"""
<h3>{APP_NAME} {__version__}</h3>
<p>A reader for the <b>Revised Standard Version, Second Catholic Edition</b>, with the
<b>Coverdale Psalter</b> and the Prayer Book canticles, arranged for the Daily Office.</p>
<p>The RSV-2CE text is © the National Council of the Churches of Christ in the USA and
Ignatius Press. It is imported from your own copy of the ebook and stays on this computer.</p>
<p>The Coverdale Psalter and canticles are from the Book of Common Prayer (public domain).
Typeset in EB Garamond (SIL Open Font License).</p>""")

    def closeEvent(self, e):
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        super().closeEvent(e)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) >= 3 and argv[1] == "--import":
        from .importer.mobi_rsv import import_file
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.setOrganizationName(ORG_NAME)
        QCoreApplication.setApplicationName(APP_NAME)
        import_file(argv[2], bible_db_path())
        print(f"Saved to {bible_db_path()}")
        return 0
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_NAME)
    app = QApplication(argv)
    for f in ("EBGaramond-VF.ttf", "EBGaramond-Italic-VF.ttf"):
        QFontDatabase.addApplicationFont(resource("fonts", f))
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
