"""The reading pane: a QWebEngineView showing generated pages, talking to Python over QWebChannel."""
from __future__ import annotations

import json

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..paths import resource_dir


class Bridge(QObject):
    """Methods the page's JavaScript calls (see reader.js)."""

    navigateRequested = Signal(str)
    copyRequested = Signal(dict)
    selectionChanged_ = Signal(list)
    scrolledTo = Signal(str)
    lessonSet = Signal(int, str)
    searchRequested = Signal(str, str)

    @Slot(str)
    def navigate(self, href: str):
        self.navigateRequested.emit(href)

    @Slot(str)
    def copy(self, payload: str):
        try:
            self.copyRequested.emit(json.loads(payload))
        except ValueError:
            pass

    @Slot(str)
    def selectionChanged(self, payload: str):
        try:
            self.selectionChanged_.emit(json.loads(payload))
        except ValueError:
            pass

    @Slot(str)
    def scrolled(self, key: str):
        self.scrolledTo.emit(key)

    @Slot(int, str)
    def setLesson(self, idx: int, ref: str):
        self.lessonSet.emit(idx, ref)

    @Slot(str, str)
    def search(self, q: str, scope: str):
        self.searchRequested.emit(q, scope)


class ReaderPage(QWebEnginePage):
    linkClicked = Signal(str)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        scheme = url.scheme()
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeBackForward:
            return False     # history is ours, not Chromium's
        if scheme == "lectern":
            self.linkClicked.emit(url.toString())
            return False
        if scheme in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return False
        return True

    def javaScriptConsoleMessage(self, level, message, line, source):  # keep the terminal quiet
        pass


class Reader(QWebEngineView):
    contextMenuWanted = Signal(dict, object)   # selection info, global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = ReaderPage(self)
        self.setPage(self._page)
        s = self._page.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        self.bridge = Bridge(self)
        self.channel = QWebChannel(self)
        self.channel.registerObject("bridge", self.bridge)
        self._page.setWebChannel(self.channel)
        self._after_load: list[str] = []
        self.loadFinished.connect(self._on_loaded)
        self.base_url = QUrl.fromLocalFile(resource_dir().rstrip("/\\") + "/")

    @property
    def linkClicked(self):
        return self._page.linkClicked

    def show_html(self, html: str, after_js: list[str] | None = None):
        self._after_load = list(after_js or [])
        self.setHtml(html, self.base_url)

    def _on_loaded(self, ok: bool):
        js, self._after_load = self._after_load, []
        for code in js:
            self.page().runJavaScript(code)

    def run(self, code: str, callback=None):
        if callback is None:
            self.page().runJavaScript(code)
        else:
            self.page().runJavaScript(code, 0, callback)

    def contextMenuEvent(self, event):
        pos = event.globalPos()

        def got(result):
            try:
                info = json.loads(result) if isinstance(result, str) else (result or {})
            except ValueError:
                info = {}
            self.contextMenuWanted.emit(info, pos)

        self.run("JSON.stringify(App.selectionInfo())", got)
