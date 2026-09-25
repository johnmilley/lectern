// Lectern reading pane: verse selection, copying, note pop-ups and links.
"use strict";

const App = (() => {
  let bridge = null;
  const data = JSON.parse(document.getElementById("page-data")?.textContent || "{}");
  let anchor = null;          // last clicked verse (for shift-click ranges)
  let copyHandled = false;

  function connect() {
    if (typeof QWebChannel === "undefined" || !window.qt) return;
    new QWebChannel(qt.webChannelTransport, ch => { bridge = ch.objects.bridge; });
  }

  // ---- verse identity -------------------------------------------------------------------
  // Bible verses carry data-id (reading order); Psalter verses carry data-ps + data-v, canticles data-cant.
  const keyOf = el => el.dataset.id ? "b:" + el.dataset.id
      : el.dataset.ps ? `p:${el.dataset.ps}:${el.dataset.v}`
      : el.dataset.cant ? `c:${el.dataset.cant}:${el.dataset.v}` : null;
  const units = () => Array.from(document.querySelectorAll(".text .v[data-id], .lesson .v[data-id], .pv"));

  function unitsFor(key) { return units().filter(u => keyOf(u) === key); }

  function orderedKeys() {
    const seen = new Set(), out = [];
    for (const u of units()) { const k = keyOf(u); if (k && !seen.has(k)) { seen.add(k); out.push(k); } }
    return out;
  }

  function selectedKeys() {
    const seen = new Set(), out = [];
    for (const u of document.querySelectorAll(".v.sel, .pv.sel")) {
      const k = keyOf(u); if (k && !seen.has(k)) { seen.add(k); out.push(k); }
    }
    return out;
  }

  function setSelected(keys) {
    const ks = new Set(keys);
    for (const u of units()) u.classList.toggle("sel", ks.has(keyOf(u)));
    notifySelection();
  }

  function notifySelection() {
    if (bridge) bridge.selectionChanged(JSON.stringify(selectedKeys()));
  }

  function clickVerse(el, shift) {
    const key = keyOf(el.closest(".v, .pv") || el);
    if (!key) return;
    const all = orderedKeys();
    if (shift && anchor && all.includes(anchor)) {
      const a = all.indexOf(anchor), b = all.indexOf(key);
      setSelected(all.slice(Math.min(a, b), Math.max(a, b) + 1));
    } else {
      const cur = selectedKeys();
      if (cur.length === 1 && cur[0] === key) setSelected([]);
      else if (cur.includes(key) && (window.event?.ctrlKey || window.event?.metaKey))
        setSelected(cur.filter(k => k !== key));
      else if (window.event?.ctrlKey || window.event?.metaKey) setSelected(cur.concat([key]));
      else setSelected([key]);
      anchor = key;
    }
  }

  // ---- text selection → verses ----------------------------------------------------------
  function selectionInfo() {
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.toString().trim()) {
      const range = sel.getRangeAt(0);
      const keys = [], seen = new Set();
      for (const u of units()) {
        if (range.intersectsNode(u)) {
          const k = keyOf(u);
          if (k && !seen.has(k)) { seen.add(k); keys.push(k); }
        }
      }
      return { keys, text: cleanText(range), partial: true };
    }
    return { keys: selectedKeys(), text: "", partial: false };
  }

  // Selected text without verse numbers or note markers; poetry lines kept on their own lines.
  function cleanText(range) {
    const frag = range.cloneContents();
    frag.querySelectorAll(".vn, .fn, .dn, .chapnum, .pvn, .heading, .rubric, .selah").forEach(n => n.remove());
    frag.querySelectorAll(".star").forEach(n => { n.textContent = "*"; });
    let out = "";
    const walk = node => {
      for (const c of node.childNodes) {
        if (c.nodeType === 3) { out += c.nodeValue; continue; }
        if (c.nodeType !== 1) continue;
        const block = /^(P|DIV|H\d|LI|SECTION|ARTICLE)$/.test(c.tagName);
        if (block && out && !out.endsWith("\n")) out += "\n";
        walk(c);
        if (block && out && !out.endsWith("\n")) out += "\n";
      }
    };
    walk(frag);
    return out.replace(/[ \t]+/g, " ").replace(/ *\n */g, "\n").replace(/\n{2,}/g, "\n").trim();
  }

  function requestCopy(mode) {
    const info = selectionInfo();
    if (!info.keys.length && !info.text) return false;
    if (bridge) bridge.copy(JSON.stringify(Object.assign(info, { mode: mode || "default" })));
    return true;
  }

  // ---- note pop-ups ---------------------------------------------------------------------
  const pop = () => document.getElementById("popover");
  function showPopover(target, htmlText) {
    const p = pop();
    p.innerHTML = htmlText;
    p.hidden = false;
    const r = target.getBoundingClientRect();
    const w = Math.min(p.offsetWidth, window.innerWidth - 20);
    let left = Math.max(10, Math.min(r.left - w / 2, window.innerWidth - w - 10));
    let top = r.bottom + 8;
    if (top + p.offsetHeight > window.innerHeight - 10) top = r.top - p.offsetHeight - 8;
    p.style.left = left + "px";
    p.style.top = top + "px";
  }
  function hidePopover() { const p = pop(); if (p) p.hidden = true; }

  function noteHtml(el) {
    const notes = data.notes || {};
    if (el.classList.contains("fn")) {
      const n = notes[el.dataset.note];
      return n ? `<i>${el.textContent}</i> ${n.html}` : null;
    }
    if (el.classList.contains("dn")) {
      const li = document.getElementById("d-" + el.dataset.verse);
      return li ? li.innerHTML : null;
    }
    return null;
  }

  // ---- navigation helpers called from Python ---------------------------------------------
  function scrollToKey(key, flash, select) {
    const els = unitsFor(key);
    if (!els.length) return;
    els[0].scrollIntoView({ block: "center" });
    if (select) setSelected([key]);
    if (flash) {
      els.forEach(e => e.classList.add("flash"));
      setTimeout(() => els.forEach(e => e.classList.remove("flash")), 1600);
    }
  }
  function selectKeys(keys, scroll) {
    setSelected(keys);
    if (scroll && keys.length) {
      const el = unitsFor(keys[0])[0];
      if (el) el.scrollIntoView({ block: keys.length > 3 ? "start" : "center" });
      anchor = keys[0];
    }
  }
  function selectAllVerses() { setSelected(orderedKeys()); }
  function topVerse() {
    for (const u of units()) {
      const r = u.getBoundingClientRect();
      if (r.bottom > 40) return keyOf(u);
    }
    return null;
  }

  // ---- events -----------------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    connect();

    document.addEventListener("click", e => {
      const a = e.target.closest("a[href^='lectern:']");
      if (a) {
        e.preventDefault();
        hidePopover();
        if (bridge) bridge.navigate(a.getAttribute("href"));
        return;
      }
      const num = e.target.closest(".vn, .chapnum, .pvn");
      if (num) { e.preventDefault(); clickVerse(num, e.shiftKey); return; }
      const mark = e.target.closest(".fn, .dn");
      if (mark) {
        const h = noteHtml(mark);
        if (h) { showPopover(mark, h); e.stopPropagation(); return; }
      }
      if (!e.target.closest("#popover")) hidePopover();
    });

    let hoverTimer = null;
    document.addEventListener("mouseover", e => {
      const mark = e.target.closest(".fn, .dn");
      if (!mark) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => { const h = noteHtml(mark); if (h) showPopover(mark, h); }, 250);
    });
    document.addEventListener("mouseout", e => {
      if (e.target.closest(".fn, .dn")) clearTimeout(hoverTimer);
    });

    document.addEventListener("copy", e => {
      if (e.target.closest && e.target.closest("input, textarea")) return;
      if (requestCopy()) { e.preventDefault(); copyHandled = true; }
    });
    document.addEventListener("keydown", e => {
      if (e.target.closest("input, textarea, select")) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "c") {
        copyHandled = false;
        // Chromium fires no copy event when nothing is highlighted; copy the chosen verses instead.
        setTimeout(() => { if (!copyHandled) requestCopy(); }, 30);
      } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !mod && !e.altKey && !e.shiftKey) {
        // turn the page, unless the page itself scrolls sideways
        if (document.documentElement.scrollWidth <= window.innerWidth && bridge) {
          e.preventDefault();
          bridge.navigate(e.key === "ArrowLeft" ? "lectern:prev" : "lectern:next");
        }
      } else if (e.key === "Escape") {
        setSelected([]); hidePopover(); window.getSelection()?.removeAllRanges();
      }
    });

    // Office lesson boxes and the search form talk to the app instead of submitting.
    document.querySelectorAll("form.lesson-form").forEach(f => f.addEventListener("submit", e => {
      e.preventDefault();
      if (bridge) bridge.setLesson(Number(f.dataset.idx), f.elements.ref.value);
    }));
    document.querySelectorAll("form.search-form").forEach(f => {
      f.addEventListener("submit", e => {
        e.preventDefault();
        if (bridge) bridge.search(f.elements.q.value, f.elements.scope.value);
      });
      f.elements.scope.addEventListener("change", () => bridge && bridge.search(f.elements.q.value, f.elements.scope.value));
    });

    let scrollTimer = null;
    window.addEventListener("scroll", () => {
      hidePopover();
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(() => { if (bridge) bridge.scrolled(topVerse() || ""); }, 300);
    }, { passive: true });
  });

  return { scrollToKey, selectKeys, selectAllVerses, selectionInfo, requestCopy, topVerse,
           clear: () => setSelected([]) };
})();
