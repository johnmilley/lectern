"""Import, preferences and export dialogs."""
from __future__ import annotations

import os
import re
import traceback

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..books import parse_ref
from ..copyfmt import REF_STYLES, CopyOptions, bible_passage, psalter_passage
from ..paths import bible_db_path


# --------------------------------------------------------------------------- import

class _ImportWorker(QObject):
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, src: str, dest: str):
        super().__init__()
        self.src, self.dest = src, dest

    def run(self):
        from ..importer.mobi_rsv import import_file
        try:
            n = import_file(self.src, self.dest, log=self.progress.emit)
            self.finished.emit(True, f"Imported {n:,} verses.")
        except Exception as e:  # noqa: BLE001 - show the user whatever went wrong
            self.progress.emit(traceback.format_exc())
            self.finished.emit(False, str(e) or e.__class__.__name__)


class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import the RSV-2CE")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        info = QLabel(
            "<p>Choose your copy of the <b>Ignatius Bible (RSV-2CE)</b> ebook: a DRM-free Kindle/Mobi file "
            "(<code>.mobi</code>, <code>.azw</code>, <code>.prc</code>) or that book converted to HTML.</p>"
            "<p>Lectern reads it once and keeps a private, searchable copy on this computer. "
            "The ebook itself is not changed.</p>")
        info.setWordWrap(True)
        lay.addWidget(info)
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setPlaceholderText("Path to the ebook…")
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path)
        row.addWidget(browse)
        lay.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        self.log.hide()
        lay.addWidget(self.log)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.go = self.buttons.addButton("Import", QDialogButtonBox.ButtonRole.AcceptRole)
        self.go.clicked.connect(self._start)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._thread = None

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose the RSV-2CE ebook", os.path.expanduser("~"),
                                           "Ebooks (*.mobi *.azw *.azw3 *.prc *.html *.htm);;All files (*)")
        if f:
            self.path.setText(f)

    def _start(self):
        src = self.path.text().strip()
        if not src or not os.path.exists(src):
            QMessageBox.warning(self, "Import", "Please choose the ebook file first.")
            return
        self.go.setEnabled(False)
        self.log.show()
        self.log.appendPlainText(f"Reading {os.path.basename(src)}…")
        self._thread = QThread(self)
        self._worker = _ImportWorker(src, bible_db_path())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.log.appendPlainText)
        self._worker.finished.connect(self._done)
        self._thread.start()

    def _done(self, ok: bool, msg: str):
        self._thread.quit()
        self._thread.wait()
        if ok:
            self.log.appendPlainText(msg)
            QMessageBox.information(self, "Import complete", msg)
            self.accept()
        else:
            self.go.setEnabled(True)
            QMessageBox.critical(self, "Import failed",
                                 "That file couldn't be read as the Ignatius RSV-2CE ebook.\n\n" + msg)


# --------------------------------------------------------------------------- preferences

THEMES = [("paper", "Paper"), ("sepia", "Sepia"), ("night", "Night")]


def bool_setting(s: QSettings, key: str, default: bool) -> bool:
    return s.value(key, default) in (True, "true", "1", 1)


class CopyOptionsForm(QWidget):
    changed = Signal()

    def __init__(self, o: CopyOptions, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        self.ref_style = QComboBox()
        for k, label in REF_STYLES:
            self.ref_style.addItem(label, k)
        self.ref_style.setCurrentIndex(max(0, [k for k, _ in REF_STYLES].index(o.ref_style)))
        self.verse_numbers = QCheckBox("Include verse numbers")
        self.layout_ = QCheckBox("Keep paragraphs and poetry line breaks")
        self.abbreviate = QCheckBox("Abbreviate book names (Jn 3:16)")
        self.version = QCheckBox("Name the translation (RSV-2CE, Coverdale)")
        self.quotes = QCheckBox("Wrap the text in quotation marks")
        self.whole = QCheckBox("Expand a partial selection to whole verses")
        self.pointing = QComboBox()
        self.pointing.addItem("Asterisk  ( * )", "*")
        self.pointing.addItem("Colon  ( : )", ":")
        self.pointing.setCurrentIndex(0 if o.pointing == "*" else 1)
        for w, v in ((self.verse_numbers, o.verse_numbers), (self.layout_, o.layout), (self.abbreviate, o.abbreviate),
                     (self.version, o.version), (self.quotes, o.quotes), (self.whole, o.whole_verses)):
            w.setChecked(v)
            w.toggled.connect(self.changed)
        self.ref_style.currentIndexChanged.connect(self.changed)
        self.pointing.currentIndexChanged.connect(self.changed)
        form.addRow("Reference:", self.ref_style)
        for w in (self.verse_numbers, self.layout_, self.abbreviate, self.version, self.quotes, self.whole):
            form.addRow("", w)
        form.addRow("Psalter half-verse mark:", self.pointing)

    def options(self) -> CopyOptions:
        return CopyOptions(
            verse_numbers=self.verse_numbers.isChecked(), layout=self.layout_.isChecked(),
            ref_style=self.ref_style.currentData(), abbreviate=self.abbreviate.isChecked(),
            version=self.version.isChecked(), quotes=self.quotes.isChecked(),
            whole_verses=self.whole.isChecked(), pointing=self.pointing.currentData())


class PreferencesDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle("Preferences")
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        read = QWidget()
        f = QFormLayout(read)
        self.theme = QComboBox()
        for k, label in THEMES:
            self.theme.addItem(label, k)
        self.theme.setCurrentIndex([k for k, _ in THEMES].index(settings.value("view/theme", "paper")))
        self.size = QSpinBox()
        self.size.setRange(12, 40)
        self.size.setSuffix(" px")
        self.size.setValue(int(settings.value("view/font_size", 20)))
        f.addRow("Theme:", self.theme)
        f.addRow("Text size:", self.size)
        self.checks = {}
        for key, label, default in (
                ("verse_numbers", "Show verse numbers", True),
                ("headings", "Show section headings", True),
                ("fn_markers", "Show footnote markers", True),
                ("endnotes", "Show notes and cross references after each chapter", True),
                ("red", "Print rubrics, headings and numbers in red", True),
                ("gloria", "Add the Gloria Patri after each psalm and canticle", True)):
            cb = QCheckBox(label)
            cb.setChecked(bool_setting(settings, f"view/{key}", default))
            self.checks[key] = cb
            f.addRow("", cb)
        self.pointing = QComboBox()
        self.pointing.addItem("Asterisk  ( * )", "*")
        self.pointing.addItem("Colon, as in the Prayer Book  ( : )", ":")
        self.pointing.setCurrentIndex(0 if settings.value("view/pointing", "*") == "*" else 1)
        f.addRow("Psalter half-verse mark:", self.pointing)
        tabs.addTab(read, "Reading")

        self.copy_form = CopyOptionsForm(CopyOptions.from_settings(settings))
        copy_tab = QWidget()
        cl = QVBoxLayout(copy_tab)
        cl.addWidget(QLabel("How passages are copied with Ctrl+C (⌘C):"))
        cl.addWidget(self.copy_form)
        cl.addStretch(1)
        tabs.addTab(copy_tab, "Copying")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        s = self.s
        s.setValue("view/theme", self.theme.currentData())
        s.setValue("view/font_size", self.size.value())
        for k, cb in self.checks.items():
            s.setValue(f"view/{k}", cb.isChecked())
        s.setValue("view/pointing", self.pointing.currentData())
        self.copy_form.options().save(s)
        self.accept()


# --------------------------------------------------------------------------- export

class ExportDialog(QDialog):
    """Pick a passage (or use the selection), preview it, copy it or save it to a file."""

    FORMATS = [("txt", "Plain text"), ("md", "Markdown"), ("html", "HTML (opens in Word, Pages, etc.)")]

    def __init__(self, main, initial_ref: str = "", psalter_keys=None, parent=None):
        super().__init__(parent or main)
        self.main = main
        self.psalter_keys = psalter_keys
        self.setWindowTitle("Copy or Export a Passage")
        self.resize(640, 560)
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Passage:"))
        self.ref = QLineEdit(initial_ref)
        self.ref.setPlaceholderText("e.g. Romans 8:28-39; Psalm 23; Isaiah 40:1-11")
        self.ref.textChanged.connect(self._update)
        row.addWidget(self.ref)
        lay.addLayout(row)
        if psalter_keys:
            self.ref.setEnabled(False)

        fmt_box = QGroupBox("Format")
        fl = QHBoxLayout(fmt_box)
        self.fmt = QButtonGroup(self)
        for i, (k, label) in enumerate(self.FORMATS):
            rb = QRadioButton(label)
            rb.setProperty("fmt", k)
            self.fmt.addButton(rb, i)
            fl.addWidget(rb)
            if i == 0:
                rb.setChecked(True)
        self.fmt.buttonToggled.connect(lambda *_: self._update())
        lay.addWidget(fmt_box)

        self.opts = CopyOptionsForm(CopyOptions.from_settings(main.settings))
        self.opts.changed.connect(self._update)
        lay.addWidget(self.opts)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        lay.addWidget(self.preview, 1)

        bb = QDialogButtonBox()
        copy = bb.addButton("Copy", QDialogButtonBox.ButtonRole.ActionRole)
        save = bb.addButton("Save…", QDialogButtonBox.ButtonRole.ActionRole)
        close = bb.addButton(QDialogButtonBox.StandardButton.Close)
        copy.clicked.connect(self._copy)
        save.clicked.connect(self._save)
        close.clicked.connect(self.reject)
        lay.addWidget(bb)
        self._update()

    def _fmt(self) -> str:
        return self.fmt.checkedButton().property("fmt")

    def _passages(self):
        o = self.opts.options()
        if self.psalter_keys:
            return [psalter_passage(self.main.psalter, self.psalter_keys, o)], o
        bible = self.main.bible
        out = []
        if bible is None:
            return out, o
        for piece in re.split(r"\s*;\s*", self.ref.text().strip()):
            if not piece:
                continue
            r = parse_ref(piece)
            if r is None:
                continue
            rows = bible.verses_for_ref(r)
            if rows:
                out.append(bible_passage(bible, rows, o))
        return out, o

    def _render(self, fmt: str):
        ps, o = self._passages()
        if fmt == "html":
            return "\n".join(p.html(o) for p in ps), ps
        if fmt == "md":
            return "\n\n".join(p.markdown(o) for p in ps), ps
        return "\n\n".join(p.plain(o) for p in ps), ps

    def _update(self):
        text, ps = self._render(self._fmt())
        self.preview.setPlainText(text if ps else "Type a reference such as “John 1:1-14” or “Psalm 23”.")

    def _copy(self):
        plain, ps = self._render("txt")
        if not ps:
            return
        html_text, _ = self._render("html")
        self.main.put_on_clipboard(plain, html_text)
        self.main.statusBar().showMessage("Copied to the clipboard", 3000)

    def _save(self):
        fmt = self._fmt()
        text, ps = self._render(fmt)
        if not ps:
            return
        name = re.sub(r"[^\w\- ]+", "", ps[0].reference).strip().replace(" ", "_") or "passage"
        path, _ = QFileDialog.getSaveFileName(self, "Save passage", os.path.join(os.path.expanduser("~"), f"{name}.{fmt}"),
                                              {"txt": "Text (*.txt)", "md": "Markdown (*.md)",
                                               "html": "HTML (*.html)"}[fmt])
        if not path:
            return
        if fmt == "html":
            text = ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + ps[0].reference + "</title>"
                    "<style>body{font-family:'EB Garamond',Garamond,Georgia,serif;font-size:13pt;line-height:1.5;"
                    "max-width:36em;margin:2em auto}sup{font-size:.6em;color:#a3161b}</style></head><body>"
                    + text + "</body></html>")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        self.main.statusBar().showMessage(f"Saved {os.path.basename(path)}", 4000)


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts & Tips")
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        tb = QTextBrowser()
        mod = "⌘" if QGuiApplication.platformName() == "cocoa" else "Ctrl"
        tb.setHtml(f"""
<h3>Getting around</h3>
<table cellpadding="3">
<tr><td><b>{mod}+L</b></td><td>Go to a passage: <i>Jn 3:16</i>, <i>Rom 8:28-39</i>, <i>Ps 23</i>, <i>1 Cor 13</i></td></tr>
<tr><td><b>{mod}+F</b></td><td>Search: type words, or put <i>?</i> in front of a book name to search for it as a word</td></tr>
<tr><td><b>← / →</b></td><td>Previous / next chapter (also {mod}+[ and {mod}+])</td></tr>
<tr><td><b>Alt+← / Alt+→</b></td><td>Back / forward</td></tr>
<tr><td><b>{mod}+D</b></td><td>Bookmark the current passage</td></tr>
<tr><td><b>{mod}+1 / {mod}+2</b></td><td>Today’s Morning / Evening Prayer</td></tr>
<tr><td><b>{mod}+= / {mod}+-</b></td><td>Larger / smaller text</td></tr>
</table>
<h3>Selecting and copying</h3>
<ul>
<li>Click a <b>verse number</b> to select that verse; <b>Shift-click</b> another to select the range;
{mod}-click to add or remove single verses.</li>
<li>Or just highlight text with the mouse.</li>
<li><b>{mod}+C</b> copies the passage with its reference, formatted as set in <i>Preferences → Copying</i>.
Rich text (italics, verse numbers) goes to apps like Word; plain text everywhere else.</li>
<li><b>{mod}+Shift+C</b> copies the text only; right-click for more copy options.</li>
<li><b>{mod}+E</b> opens Copy/Export, where you can type any passage and save it as text, Markdown or HTML.</li>
<li><b>Esc</b> clears the selection.</li>
</ul>
<h3>Search</h3>
<ul>
<li>All words must match: <i>living water</i></li>
<li>Exact phrase: <i>"bread of life"</i> · beginnings of words: <i>forgiv*</i></li>
<li>Exclude: <i>love -god</i> · either: <i>mercy OR compassion</i></li>
<li>Choose a part of the Bible, or the Coverdale Psalter, from the list beside the search box.</li>
</ul>""")
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
