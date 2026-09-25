"""Left-hand navigator: books & chapters, the Psalter and Office, bookmarks."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem,
                               QPushButton, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..render import ordinal
from ..store import Bible, Psalter

LOC = Qt.ItemDataRole.UserRole


class ChapterGrid(QListWidget):
    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setGridSize(QSize(40, 30))
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)


class Navigator(QTabWidget):
    locationChosen = Signal(dict)
    bookmarkRemoved = Signal(int)

    def __init__(self, psalter: Psalter, parent=None):
        super().__init__(parent)
        self.bible: Bible | None = None
        self.psalter = psalter
        self.setDocumentMode(True)

        # ---- Bible tab
        bible_tab = QWidget()
        lay = QVBoxLayout(bible_tab)
        lay.setContentsMargins(0, 4, 0, 0)
        split = QSplitter(Qt.Orientation.Vertical)
        self.books = QTreeWidget()
        self.books.setHeaderHidden(True)
        self.books.setRootIsDecorated(True)
        self.books.itemClicked.connect(self._book_clicked)
        self.books.itemActivated.connect(self._book_clicked)
        chap_box = QWidget()
        cl = QVBoxLayout(chap_box)
        cl.setContentsMargins(4, 4, 4, 0)
        self.chap_label = QLabel("Chapters")
        f = self.chap_label.font()
        f.setBold(True)
        self.chap_label.setFont(f)
        self.chapters = ChapterGrid()
        self.chapters.itemClicked.connect(self._chapter_clicked)
        self.chapters.itemActivated.connect(self._chapter_clicked)
        cl.addWidget(self.chap_label)
        cl.addWidget(self.chapters)
        split.addWidget(self.books)
        split.addWidget(chap_box)
        split.setSizes([420, 200])
        lay.addWidget(split)
        self.addTab(bible_tab, "Bible")
        self._current_book: int | None = None

        # ---- Psalter / Office tab
        self.psalter_tree = QTreeWidget()
        self.psalter_tree.setHeaderHidden(True)
        self.psalter_tree.itemClicked.connect(self._loc_clicked)
        self.psalter_tree.itemActivated.connect(self._loc_clicked)
        self.addTab(self.psalter_tree, "Psalter")
        self._build_psalter()

        # ---- Bookmarks tab
        bm_tab = QWidget()
        bl = QVBoxLayout(bm_tab)
        bl.setContentsMargins(0, 4, 0, 4)
        self.bookmarks = QListWidget()
        self.bookmarks.itemClicked.connect(self._loc_clicked_list)
        self.bookmarks.itemActivated.connect(self._loc_clicked_list)
        row = QHBoxLayout()
        rm = QPushButton("Remove")
        rm.clicked.connect(self._remove_bookmark)
        row.addStretch(1)
        row.addWidget(rm)
        bl.addWidget(self.bookmarks)
        bl.addLayout(row)
        self.addTab(bm_tab, "Bookmarks")

    # ---- Bible
    def set_bible(self, bible: Bible | None):
        self.bible = bible
        self.books.clear()
        self.chapters.clear()
        if bible is None:
            item = QTreeWidgetItem(["Import the RSV-2CE to read the Bible"])
            item.setData(0, LOC, {"t": "welcome"})
            self.books.addTopLevelItem(item)
            return
        ot = QTreeWidgetItem(["Old Testament"])
        nt = QTreeWidgetItem(["New Testament"])
        for top in (ot, nt):
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            top.setFlags(top.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.books.addTopLevelItem(top)
        for b in bible.books:
            it = QTreeWidgetItem([b["name"]])
            it.setData(0, LOC, b["id"])
            it.setToolTip(0, b["title"] + (" (deuterocanonical)" if b["deutero"] else ""))
            if b["deutero"]:
                f = it.font(0)
                f.setItalic(True)
                it.setFont(0, f)
            (ot if b["testament"] == "OT" else nt).addChild(it)
        ot.setExpanded(True)
        nt.setExpanded(True)

    def _book_clicked(self, item: QTreeWidgetItem):
        v = item.data(0, LOC)
        if isinstance(v, dict):
            self.locationChosen.emit(v)
            return
        if v is None:
            item.setExpanded(not item.isExpanded())
            return
        self.show_chapters(v)
        chs = self.bible.chapters(v) if self.bible else []
        if chs:
            self.locationChosen.emit({"t": "chapter", "book": v, "chapter": chs[0]})

    def show_chapters(self, book: int, current: int | None = None):
        if self.bible is None:
            return
        if book != self._current_book:
            self._current_book = book
            self.chapters.clear()
            for c in self.bible.chapters(book):
                it = QListWidgetItem(str(c))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setData(LOC, c)
                self.chapters.addItem(it)
            name = self.bible.book_by_id[book]["name"]
            self.chap_label.setText("Psalms" if book == 21 else f"{name} — chapters")
        if current is not None:
            for i in range(self.chapters.count()):
                if self.chapters.item(i).data(LOC) == current:
                    self.chapters.setCurrentRow(i)
                    self.chapters.scrollToItem(self.chapters.item(i))
                    break
        # keep the book highlighted in the tree
        for i in range(self.books.topLevelItemCount()):
            top = self.books.topLevelItem(i)
            for j in range(top.childCount()):
                ch = top.child(j)
                if ch.data(0, LOC) == book:
                    self.books.setCurrentItem(ch)

    def _chapter_clicked(self, item: QListWidgetItem):
        if self._current_book is not None:
            self.locationChosen.emit({"t": "chapter", "book": self._current_book, "chapter": item.data(LOC)})

    # ---- Psalter
    def _build_psalter(self):
        t = self.psalter_tree
        t.clear()
        today = _dt.date.today()
        day = self.psalter.course_day(today.day)

        def add(parent, text, loc, bold=False, tip=None):
            it = QTreeWidgetItem([text])
            if loc is not None:
                it.setData(0, LOC, loc)
            if bold:
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
            if tip:
                it.setToolTip(0, tip)
            if parent is None:
                t.addTopLevelItem(it)
            else:
                parent.addChild(it)
            return it

        office = add(None, "The Daily Office", None, bold=True)
        add(office, "Morning Prayer — today", {"t": "office", "date": "today", "office": "morning"},
            tip="Mattins: the Invitatory, the psalms of the day, lessons and canticles")
        add(office, "Evening Prayer — today", {"t": "office", "date": "today", "office": "evening"},
            tip="Evensong: the psalms of the day, lessons and canticles")
        office.setExpanded(True)

        todays = add(None, f"Psalms for Today (the {ordinal(day)} day)", None, bold=True)
        add(todays, f"Morning — Ps {self.psalter.day_label(day, 'morning')}",
            {"t": "day", "day": day, "office": "morning"})
        add(todays, f"Evening — Ps {self.psalter.day_label(day, 'evening')}",
            {"t": "day", "day": day, "office": "evening"})
        todays.setExpanded(True)

        course = add(None, "The Monthly Course", None, bold=True)
        for d in range(1, 31):
            di = add(course, f"Day {d}", None)
            add(di, f"Morning — Ps {self.psalter.day_label(d, 'morning')}", {"t": "day", "day": d, "office": "morning"})
            add(di, f"Evening — Ps {self.psalter.day_label(d, 'evening')}", {"t": "day", "day": d, "office": "evening"})

        ps = add(None, "The Psalms (Coverdale)", None, bold=True)
        for n in range(1, 151):
            add(ps, f"Psalm {n}   {self.psalter.psalms[n]['latin']}", {"t": "coverdale", "n": n})

        cant = add(None, "Canticles", None, bold=True)
        for key, c in self.psalter.canticles.items():
            add(cant, c["title"] + (f" — {c['source']}" if c["source"] else ""), {"t": "canticle", "key": key})
        cant.setExpanded(True)

    def refresh_today(self):
        self._build_psalter()

    def _loc_clicked(self, item: QTreeWidgetItem):
        loc = item.data(0, LOC)
        if loc:
            self.locationChosen.emit(loc)
        else:
            item.setExpanded(not item.isExpanded())

    # ---- bookmarks
    def set_bookmarks(self, marks: list[dict]):
        self.bookmarks.clear()
        for i, m in enumerate(marks):
            it = QListWidgetItem(m.get("label", "?"))
            it.setData(LOC, m.get("loc"))
            it.setToolTip(m.get("snippet", ""))
            self.bookmarks.addItem(it)

    def _loc_clicked_list(self, item: QListWidgetItem):
        loc = item.data(LOC)
        if loc:
            self.locationChosen.emit(loc)

    def _remove_bookmark(self):
        row = self.bookmarks.currentRow()
        if row >= 0:
            self.bookmarkRemoved.emit(row)
