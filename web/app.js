// Lectern on the web: navigation, the contents drawer, selection and copying, preferences.
"use strict";

const App = (() => {
  let bible = null, psalter = null;
  let pageData = {};
  let route = { t: "welcome" };
  let anchor = null;            // last clicked verse, for shift-click ranges
  let pendingCopy = null;       // payload for a copy started from a button

  const $ = s => document.querySelector(s);
  const content = () => $("#content");

  // ------------------------------------------------------------------ preferences

  const PREF_DEFAULTS = {
    theme: "auto", font_size: 20, pointing: "*",
    verse_numbers: true, headings: true, fn_markers: true, endnotes: true, red: true, gloria: true,
    copy: { ...Copy.DEFAULTS },
  };
  const store = {
    get(k, d) { try { const v = localStorage.getItem("lectern." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("lectern." + k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  };
  let prefs = Object.assign({}, PREF_DEFAULTS, store.get("prefs", {}));
  prefs.copy = Object.assign({}, Copy.DEFAULTS, prefs.copy || {});
  const savePrefs = () => store.set("prefs", prefs);

  const darkQuery = matchMedia("(prefers-color-scheme: dark)");
  function applyPrefs() {
    const root = document.documentElement;
    const theme = prefs.theme === "auto" ? (darkQuery.matches ? "night" : "paper") : prefs.theme;
    root.className = [`theme-${theme}`, ...["verse_numbers", "headings", "fn_markers", "red"]
      .filter(k => !prefs[k]).map(k => "no-" + k.replace("_", "-"))].join(" ");
    root.style.setProperty("--fs", prefs.font_size + "px");
    const meta = $('meta[name="theme-color"]');
    if (meta) meta.content = getComputedStyle(root).getPropertyValue("--panel").trim() || "#f3eee2";
  }
  darkQuery.addEventListener("change", applyPrefs);

  // ------------------------------------------------------------------ routes
  // #/chapter/50/3?sel=1,2  #/verse/123  #/ref/50/3/16  #/coverdale/23[/4][?compare=1]  #/day/5/morning
  // #/canticle/venite  #/office/2026-09-24/morning  #/search?q=...&scope=...&book=...

  function parseHash(hash) {
    const [path, qs] = (hash.replace(/^#\/?/, "") || "").split("?");
    const p = path.split("/").filter(Boolean).map(decodeURIComponent);
    const q = new URLSearchParams(qs || "");
    const n = i => parseInt(p[i], 10);
    switch (p[0]) {
      case "chapter": return { t: "chapter", book: n(1), chapter: n(2),
                               select: q.get("sel") ? q.get("sel").split(",").map(Number) : null,
                               flash: q.get("v") ? Number(q.get("v")) : null };
      case "verse": return { t: "verse", id: n(1) };
      case "ref": return { t: "ref", book: n(1), chapter: n(2), verse: n(3) };
      case "coverdale": return { t: "coverdale", n: n(1), v: p[2] ? n(2) : null, compare: q.get("compare") === "1" };
      case "day": return { t: "day", day: n(1), office: p[2] === "evening" ? "evening" : "morning" };
      case "canticle": return { t: "canticle", key: p[1] };
      case "office": return { t: "office", date: p[1] === "today" || !p[1] ? Render.isoDate(new Date()) : p[1],
                              office: p[2] === "evening" ? "evening" : "morning" };
      case "search": return { t: "search", q: q.get("q") || "", scope: q.get("scope") || "all",
                              book: q.get("book") ? Number(q.get("book")) : null };
      default: return { t: "welcome" };
    }
  }

  function go(hash, { replace = false } = {}) {
    if (!hash.startsWith("#")) hash = "#" + hash;
    history.replaceState({ ...(history.state || {}), scroll: scrollY }, "");
    if (replace) history.replaceState({ scroll: 0 }, "", hash);
    else history.pushState({ scroll: 0 }, "", hash);
    render(0);
  }

  function render(scroll) {
    route = parseHash(location.hash);
    const o = prefs;
    let out, title = "Lectern";
    const after = [];
    try {
      // Links that resolve to a chapter.
      if (route.t === "verse" && bible) {
        const r = bible.byId.get(route.id);
        if (r) return go(`#/chapter/${r.book}/${r.chapter}?v=${r.id}`, { replace: true });
      }
      if (route.t === "ref" && bible) {
        const r = bible.chapter(route.book, route.chapter).find(x => x.verse <= route.verse && x.verseEnd >= route.verse);
        return go(`#/chapter/${route.book}/${route.chapter}${r ? "?v=" + r.id : ""}`, { replace: true });
      }
      if (route.t === "chapter" && bible && bible.chapter(route.book, route.chapter).length) {
        out = Render.chapter(bible, route.book, route.chapter, o);
        title = route.book === 21 ? `Psalm ${route.chapter}` : `${bible.bookById[route.book].name} ${route.chapter}`;
        if (route.select) after.push(() => selectKeys(route.select.map(i => "b:" + i), scroll === 0));
        if (route.flash) after.push(() => scrollToKey("b:" + route.flash, true));
      } else if (route.t === "chapter" && !bible && route.book === 21) {
        return go(`#/coverdale/${route.chapter}`, { replace: true });
      } else if (route.t === "coverdale" && psalter.psalms[route.n]) {
        out = Render.psalmPage(psalter, route.n, o, bible, route.compare && !!bible);
        title = `Psalm ${route.n} (Coverdale)`;
        if (route.v) after.push(() => scrollToKey(`p:${route.n}:${route.v}`, true));
      } else if (route.t === "day" && route.day >= 1 && route.day <= 31) {
        out = Render.psalterDay(psalter, route.day, route.office, o);
        title = `Psalter, Day ${Psalter.courseDay(route.day)} ${route.office === "morning" ? "Morning" : "Evening"}`;
      } else if (route.t === "canticle" && psalter.canticles[route.key]) {
        out = Render.canticlePage(psalter, route.key, o);
        title = psalter.canticles[route.key].title;
      } else if (route.t === "office" && /^\d{4}-\d\d-\d\d$/.test(route.date)) {
        const lessons = store.get(`office.lessons.${route.date}.${route.office}`, []);
        const cants = [0, 1].map(i => store.get(`office.canticle.${route.office}.${i}`, ""));
        out = Render.office(psalter, bible, route.date, route.office, lessons, cants, o);
        title = route.office === "morning" ? "Morning Prayer" : "Evening Prayer";
      } else if (route.t === "search" && route.q) {
        out = Render.search(bible, psalter, route.q, route.scope, route.book);
        title = `Search: ${route.q}`;
      }
    } catch (e) {
      console.error(e);
      out = null;
    }
    if (!out) { out = Render.welcome(!!bible); route = { t: "welcome" }; }
    pageData = out.data;
    hidePopover();
    closeSelBar();
    content().innerHTML = out.html;
    document.title = title === "Lectern" ? "Lectern" : `${title} — Lectern`;
    $("#omni input").placeholder = route.t === "welcome" ? "Go to a passage (Jn 3:16, Ps 23) or search…" : `${title} — go to or search…`;
    wireForms();
    syncDrawer();
    if (route.t !== "search" && route.t !== "welcome") store.set("last", location.hash);
    if (typeof scroll === "number") window.scrollTo(0, scroll);
    after.forEach(f => f());
  }

  function step(delta) {
    const r = route;
    if (r.t === "chapter" && bible) {
      const nb = bible.neighbour(r.book, r.chapter, delta);
      if (nb) go(`#/chapter/${nb[0]}/${nb[1]}`);
    } else if (r.t === "coverdale") {
      const n = r.n + delta;
      if (n >= 1 && n <= 150) go(`#/coverdale/${n}${r.compare ? "?compare=1" : ""}`);
    } else if (r.t === "day") {
      let d = Psalter.courseDay(r.day), o = r.office;
      if (delta > 0) [d, o] = o === "morning" ? [d, "evening"] : [d % 30 + 1, "morning"];
      else [d, o] = o === "evening" ? [d, "morning"] : [(d + 28) % 30 + 1, "evening"];
      go(`#/day/${d}/${o}`);
    } else if (r.t === "office") {
      const d = Render.parseDate(r.date);
      d.setDate(d.getDate() + delta);
      go(`#/office/${Render.isoDate(d)}/${r.office}`);
    }
  }

  // Omnibox: a reference goes there, anything else is a search.
  function goText(text) {
    let m = /^(?:cov(?:erdale)?|bcp)\s*(?:ps(?:alm)?\s*)?(\d{1,3})(?:\s*[:.]\s*(\d+))?$/i.exec(text);
    if (m && +m[1] >= 1 && +m[1] <= 150) { go(`#/coverdale/${m[1]}${m[2] ? "/" + m[2] : ""}`); return true; }
    m = /^day\s*(\d{1,2})\s*(morning|evening|am|pm|m|e)?$/i.exec(text);
    if (m && +m[1] >= 1 && +m[1] <= 31) {
      const off = (m[2] || "morning").toLowerCase();
      go(`#/day/${Psalter.courseDay(+m[1])}/${["evening", "pm", "e"].includes(off) ? "evening" : "morning"}`);
      return true;
    }
    const ref = Books.parseRef(text);
    if (!ref) return false;
    if (!bible) {
      if (ref.book.code === "Ps" && ref.chapter) { go(`#/coverdale/${ref.chapter}${ref.verse ? "/" + ref.verse : ""}`); return true; }
      toast("Load your RSV-2CE file first (Contents → Load the RSV-2CE).");
      return true;
    }
    const chapters = bible.chapters(ref.book.id);
    if (!chapters.length) return false;
    if (ref.chapter === null) { go(`#/chapter/${ref.book.id}/${chapters[0]}`); return true; }
    if (!chapters.includes(ref.chapter)) { toast(`${ref.book.name} has no chapter ${ref.chapter}`); return true; }
    if (ref.verse === null && (ref.endChapter === null || ref.endChapter === ref.chapter)) {
      go(`#/chapter/${ref.book.id}/${ref.chapter}`); return true;
    }
    const rows = bible.versesForRef(ref);
    const ids = rows.filter(r => r.chapter === ref.chapter).map(r => r.id);
    go(`#/chapter/${ref.book.id}/${ref.chapter}${ids.length ? "?sel=" + ids.join(",") : ""}`);
    if (rows.length > ids.length) toast(`${bible.refLabel(rows)} continues into the next chapter`);
    return true;
  }

  function search(q, scope = "all") {
    q = q.trim();
    if (!q) return;
    let book = null;
    if (scope.startsWith("book:")) { book = scope.split(":")[1]; scope = "all"; }
    go(`#/search?q=${encodeURIComponent(q)}${scope !== "all" ? "&scope=" + scope : ""}${book ? "&book=" + book : ""}`);
  }

  // ------------------------------------------------------------------ verse selection
  // Bible verses carry data-id (reading order); Psalter verses data-ps + data-v; canticles data-cant.

  const keyOf = el => el.dataset.id ? "b:" + el.dataset.id
    : el.dataset.ps ? `p:${el.dataset.ps}:${el.dataset.v}`
    : el.dataset.cant ? `c:${el.dataset.cant}:${el.dataset.v}` : null;
  const units = () => Array.from(content().querySelectorAll(".text .v[data-id], .lesson .v[data-id], .pv"));
  const unitsFor = key => units().filter(u => keyOf(u) === key);
  function uniqueKeys(els) {
    const seen = new Set(), out = [];
    for (const u of els) { const k = keyOf(u); if (k && !seen.has(k)) { seen.add(k); out.push(k); } }
    return out;
  }
  const orderedKeys = () => uniqueKeys(units());
  const selectedKeys = () => uniqueKeys(content().querySelectorAll(".v.sel, .pv.sel"));

  function setSelected(keys) {
    const ks = new Set(keys);
    for (const u of units()) u.classList.toggle("sel", ks.has(keyOf(u)));
    updateSelBar();
  }

  function clickVerse(el, e, touch) {
    const key = keyOf(el.closest(".v, .pv") || el);
    if (!key) return;
    const all = orderedKeys(), cur = selectedKeys();
    if (e.shiftKey && anchor && all.includes(anchor)) {
      const a = all.indexOf(anchor), b = all.indexOf(key);
      setSelected(all.slice(Math.min(a, b), Math.max(a, b) + 1));
      return;
    }
    const additive = touch || e.ctrlKey || e.metaKey;
    if (cur.includes(key) && (additive || cur.length === 1)) setSelected(cur.filter(k => k !== key));
    else if (additive) setSelected(all.filter(k => cur.includes(k) || k === key));
    else setSelected([key]);
    anchor = key;
  }

  function selectKeys(keys, scroll) {
    setSelected(keys);
    if (scroll && keys.length) {
      const el = unitsFor(keys[0])[0];
      if (el) el.scrollIntoView({ block: keys.length > 3 ? "start" : "center" });
      anchor = keys[0];
    }
  }

  function scrollToKey(key, flash) {
    const els = unitsFor(key);
    if (!els.length) return;
    els[0].scrollIntoView({ block: "center" });
    if (flash) {
      els.forEach(e => e.classList.add("flash"));
      setTimeout(() => els.forEach(e => e.classList.remove("flash")), 1600);
    }
  }

  // Highlighted text → the verses it touches, plus the text itself without numbers or note marks.
  function selectionInfo() {
    const sel = getSelection();
    if (sel && !sel.isCollapsed && sel.toString().trim() && content().contains(sel.anchorNode)) {
      const range = sel.getRangeAt(0);
      return { keys: uniqueKeys(units().filter(u => range.intersectsNode(u))), text: cleanText(range), partial: true };
    }
    return { keys: selectedKeys(), text: "", partial: false };
  }

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

  // ------------------------------------------------------------------ copying

  const parseKeys = (keys, prefix) => keys.filter(k => k.startsWith(prefix)).map(k => k.slice(2).split(":"));

  function buildPassage(info, mode) {
    const o = { ...prefs.copy };
    if (mode === "plain") { o.ref_style = "none"; o.verse_numbers = false; }
    else if (mode === "numbers") o.verse_numbers = true;
    const b = parseKeys(info.keys, "b:").map(k => Number(k[0]));
    const p = parseKeys(info.keys, "p:").map(k => k.map(Number));
    const c = parseKeys(info.keys, "c:");
    let passage = null;
    if (b.length && bible) passage = Copy.biblePassage(bible, bible.versesByIds(b), o, info.partial ? info.text : null);
    else if (p.length) {
      passage = Copy.psalterPassage(psalter, p, o, prefs.pointing);
      if (info.partial && !o.whole_verses && info.text)
        passage.blocks = [info.text.split("\n").filter(l => l.trim()).map(l => [[null, l, escHtml(l)]])];
    } else if (c.length) {
      const key = c[0][0];
      passage = Copy.canticlePassage(psalter, key, c.filter(k => k[0] === key).map(k => Number(k[1])), prefs.pointing);
    }
    return { passage, o };
  }

  // Returns {plain, html, label} for the current selection, or null when nothing is chosen.
  function payload(mode = "default") {
    const info = selectionInfo();
    if (!info.keys.length && !info.text) return null;
    const { passage, o } = buildPassage(info, mode);
    if (!passage) return info.text ? { plain: info.text, html: null, label: "text" } : null;
    if (mode === "ref") {
      const ref = passage.reference + (o.version && passage.version ? ` (${passage.version})` : "");
      return { plain: ref, html: null, label: `“${ref}”` };
    }
    const html = `<meta charset="utf-8"><div style="font-family:'EB Garamond',Garamond,Georgia,serif">${passage.html(o)}</div>`;
    return { plain: passage.plain(o), html, label: passage.reference };
  }

  async function copy(mode = "default") {
    const data = payload(mode);
    if (!data) { toast("Select some verses first: tap a verse number, or highlight text"); return; }
    try {
      if (navigator.clipboard && window.ClipboardItem) {
        const item = { "text/plain": new Blob([data.plain], { type: "text/plain" }) };
        if (data.html) item["text/html"] = new Blob([data.html], { type: "text/html" });
        await navigator.clipboard.write([new ClipboardItem(item)]);
      } else throw new Error("no async clipboard");
    } catch {
      pendingCopy = data;
      const ok = document.execCommand("copy");
      pendingCopy = null;
      if (!ok) { toast("Your browser wouldn't allow copying"); return; }
    }
    toast(`Copied ${data.label}`);
  }

  // ------------------------------------------------------------------ selection bar

  function labelForKeys(keys) {
    const b = parseKeys(keys, "b:").map(k => Number(k[0]));
    if (b.length && bible) return bible.refLabel(bible.versesByIds(b));
    const p = parseKeys(keys, "p:").map(k => k.map(Number));
    if (p.length) return Copy.psalterPassage(psalter, p, prefs.copy, prefs.pointing).reference;
    const c = parseKeys(keys, "c:");
    if (c.length) return psalter.canticles[c[0][0]].title;
    return "";
  }

  function updateSelBar() {
    const keys = selectedKeys();
    const bar = $("#selbar");
    if (!keys.length) { bar.hidden = true; return; }
    bar.querySelector(".sel-label").textContent = labelForKeys(keys) || `${keys.length} selected`;
    bar.hidden = false;
  }
  function closeSelBar() { $("#selbar").hidden = true; }

  // ------------------------------------------------------------------ notes

  function noteHtml(el) {
    if (el.classList.contains("fn")) {
      const n = (pageData.notes || {})[el.dataset.note];
      return n ? `<i>${escHtml(el.textContent)}</i> ${Render.links(Render.divine(n.html))}` : null;
    }
    if (el.classList.contains("dn")) {
      const li = document.getElementById("d-" + el.dataset.verse);
      return li ? li.innerHTML : null;
    }
    return null;
  }
  function showPopover(target, html) {
    const p = $("#popover");
    p.innerHTML = html;
    p.hidden = false;
    const r = target.getBoundingClientRect();
    const w = Math.min(p.offsetWidth, innerWidth - 20);
    p.style.left = Math.max(10, Math.min(r.left - w / 2, innerWidth - w - 10)) + "px";
    let top = r.bottom + 8;
    if (top + p.offsetHeight > innerHeight - 10) top = r.top - p.offsetHeight - 8;
    p.style.top = Math.max(10, top) + "px";
  }
  function hidePopover() { $("#popover").hidden = true; }

  // ------------------------------------------------------------------ bookmarks

  const bookmarks = () => store.get("bookmarks", []);
  function addBookmark() {
    let hash = location.hash.replace(/[?&](v)=\d+/, "");
    let label = document.title.replace(/ — Lectern$/, "");
    const keys = selectedKeys();
    if (keys.length) {
      label = labelForKeys(keys) || label;
      const b = parseKeys(keys, "b:").map(k => k[0]);
      if (b.length && route.t === "chapter") hash = `#/chapter/${route.book}/${route.chapter}?sel=${b.join(",")}`;
    }
    if (route.t === "welcome") return;
    const marks = bookmarks();
    marks.push({ label, hash, added: Render.isoDate(new Date()) });
    store.set("bookmarks", marks);
    buildBookmarks();
    toast(`Bookmarked ${label}`);
  }

  // ------------------------------------------------------------------ contents drawer

  const wide = matchMedia("(min-width: 1100px)");
  function openDrawer(open) {
    document.body.classList.toggle("drawer-open", open);
    store.set("drawer", open);
  }
  function drawerAfterNav() { if (!wide.matches) openDrawer(false); }

  function setTab(name) {
    document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === name));
    document.querySelectorAll(".tab").forEach(t => { t.hidden = t.id !== "tab-" + name; });
    store.set("tab", name);
  }

  function buildBibleTab() {
    const el = $("#tab-bible");
    if (!bible) {
      el.innerHTML = `<p class="drawer-note">The RSV-2CE isn't loaded in this browser yet.</p>
        <p><button class="button" data-act="load">Load the RSV-2CE…</button></p>`;
      return;
    }
    const part = (label, test) => `<div class="group">${label}</div>` + bible.books.filter(test).map(b =>
      `<details class="book" data-book="${b.id}"><summary>${escHtml(b.name)}</summary><div class="grid"></div></details>`).join("");
    el.innerHTML = part("Old Testament", b => b.id <= 46) + part("New Testament", b => b.id >= 47);
    el.querySelectorAll("details.book").forEach(d => d.addEventListener("toggle", () => {
      if (!d.open) return;
      const grid = d.querySelector(".grid");
      if (!grid.childElementCount) {
        const id = Number(d.dataset.book);
        grid.innerHTML = bible.chapters(id).map(c => `<a href="#/chapter/${id}/${c}" data-c="${c}">${c}</a>`).join("");
      }
      markCurrent();
    }));
  }

  function buildPsalterTab() {
    const days = Array.from({ length: 30 }, (_, i) => i + 1);
    const cants = Object.values(psalter.canticles);
    $("#tab-psalter").innerHTML = `
      <div class="group">Today</div>
      <a class="item" href="#/office/today/morning">Morning Prayer</a>
      <a class="item" href="#/office/today/evening">Evening Prayer</a>
      <a class="item" href="#" data-act="todays-psalms">Today's Psalms</a>
      <div class="group">The Psalms by Day</div>
      <div class="days">${days.map(d => `<span>${d}</span><a href="#/day/${d}/morning">Morning</a><a href="#/day/${d}/evening">Evening</a>`).join("")}</div>
      <div class="group">The Psalms</div>
      <div class="grid psalms">${Array.from({ length: 150 }, (_, i) => `<a href="#/coverdale/${i + 1}">${i + 1}</a>`).join("")}</div>
      <div class="group">Canticles</div>
      ${cants.map(c => `<a class="item" href="#/canticle/${c.key}">${escHtml(c.title)}</a>`).join("")}`;
  }

  function buildBookmarks() {
    const marks = bookmarks();
    $("#tab-marks").innerHTML = marks.length
      ? marks.map((m, i) => `<div class="mark-row"><a class="item" href="${escHtml(m.hash)}">${escHtml(m.label)}</a>` +
                            `<button class="x" data-act="unmark" data-i="${i}" aria-label="Remove">×</button></div>`).join("")
      : '<p class="drawer-note">No bookmarks yet. Select verses or open a page, then choose <b>Bookmark</b> (Ctrl+D).</p>';
  }

  function markCurrent() {
    document.querySelectorAll("#drawer a.cur").forEach(a => a.classList.remove("cur"));
    if (route.t === "chapter") {
      const d = document.querySelector(`details.book[data-book="${route.book}"]`);
      d?.querySelector(`a[data-c="${route.chapter}"]`)?.classList.add("cur");
    } else if (route.t === "coverdale") {
      document.querySelector(`#tab-psalter .psalms a[href="#/coverdale/${route.n}"]`)?.classList.add("cur");
    }
  }

  // Open the current book in the contents (closing the others) and bring it into view.
  function syncDrawer() {
    if (route.t === "chapter" && bible) {
      document.querySelectorAll("details.book[open]").forEach(d => { if (+d.dataset.book !== route.book) d.open = false; });
      const d = document.querySelector(`details.book[data-book="${route.book}"]`);
      if (d && !d.open) {
        d.open = true;
        requestAnimationFrame(() => {
          const drawer = $("#drawer"), top = d.offsetTop - drawer.querySelector(".tabs").offsetHeight - 8;
          if (top < drawer.scrollTop || top > drawer.scrollTop + drawer.clientHeight - 80) drawer.scrollTop = top;
        });
      }
    }
    markCurrent();
  }

  // ------------------------------------------------------------------ preferences dialog

  function buildSettings() {
    const c = prefs.copy;
    const check = (key, label, obj = "prefs") =>
      `<label class="chk"><input type="checkbox" data-pref="${obj}.${key}"${(obj === "copy" ? c : prefs)[key] ? " checked" : ""}> ${label}</label>`;
    $("#settings-body").innerHTML = `
      <section><h3>Appearance</h3>
        <div class="seg">${[["auto", "Auto"], ["paper", "Paper"], ["sepia", "Sepia"], ["night", "Night"]].map(([k, l]) =>
          `<button data-theme="${k}" class="${prefs.theme === k ? "on" : ""}">${l}</button>`).join("")}</div>
        <div class="size"><span>Text size</span><button data-size="-1" aria-label="Smaller">A−</button>
          <b>${prefs.font_size}</b><button data-size="1" aria-label="Larger">A+</button></div>
        ${check("verse_numbers", "Verse numbers")}${check("headings", "Section headings")}
        ${check("fn_markers", "Footnote markers")}${check("endnotes", "Notes and cross references")}
        ${check("red", "Red rubrics")}${check("gloria", "Gloria Patri after psalms")}
        <label class="row">Psalter pointing <select data-pref="prefs.pointing">
          <option value="*"${prefs.pointing === "*" ? " selected" : ""}>Asterisk (*)</option>
          <option value=":"${prefs.pointing === ":" ? " selected" : ""}>Prayer Book colon (:)</option></select></label>
      </section>
      <section><h3>Copying</h3>
        <label class="row">Reference <select data-pref="copy.ref_style">${Copy.REF_STYLES.map(([k, l]) =>
          `<option value="${k}"${c.ref_style === k ? " selected" : ""}>${l}</option>`).join("")}</select></label>
        ${check("verse_numbers", "Include verse numbers", "copy")}${check("layout", "Keep paragraph and poetry line breaks", "copy")}
        ${check("abbreviate", "Abbreviate book names", "copy")}${check("version", "Add the version (RSV-2CE, Coverdale)", "copy")}
        ${check("quotes", "Put the text in quotation marks", "copy")}${check("whole_verses", "Copy whole verses when only part is highlighted", "copy")}
      </section>
      <section><h3>Your RSV-2CE</h3>
        ${bible ? `<p class="drawer-note">Loaded in this browser (${bible.verses.length.toLocaleString()} verses). It stays on this device.</p>
          <p><button data-act="load">Replace…</button> <button data-act="forget">Remove from this device</button></p>`
                : `<p class="drawer-note">Not loaded.</p><p><button data-act="load">Load the RSV-2CE…</button></p>`}
      </section>
      <section><h3>Shortcuts</h3>
        <p class="drawer-note"><kbd>/</kbd> go to or search · <kbd>←</kbd> <kbd>→</kbd> turn the page ·
        click a verse number to select, <kbd>Shift</kbd>-click for a range · <kbd>Ctrl</kbd>+<kbd>C</kbd> copy with reference ·
        <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>C</kbd> text only · <kbd>Ctrl</kbd>+<kbd>D</kbd> bookmark · <kbd>Esc</kbd> clear.</p>
      </section>`;
  }

  function onSettingsInput(e) {
    const t = e.target;
    if (!t.dataset.pref) return;
    const [obj, key] = t.dataset.pref.split(".");
    const target = obj === "copy" ? prefs.copy : prefs;
    target[key] = t.type === "checkbox" ? t.checked : t.value;
    savePrefs(); applyPrefs(); rerender();
  }

  function rerender() {
    const keys = selectedKeys();
    render(scrollY);
    if (keys.length) setSelected(keys);
  }

  // ------------------------------------------------------------------ loading the Bible

  async function loadFile(file) {
    toast("Reading…", 60000);
    try {
      const buf = await file.arrayBuffer();
      const data = await Library.decode(buf);
      bible = new Bible(data);
      await Library.save(buf);
      buildBibleTab();
      toast(`Loaded ${bible.verses.length.toLocaleString()} verses`);
      if ($("#settings").open) buildSettings();
      if (route.t === "welcome") go(`#/chapter/1/1`); else rerender();
    } catch (e) {
      console.error(e);
      toast(e.message && e.message.includes("Lectern") ? e.message : "That file couldn't be read. Choose the lectern-rsv2ce.json.gz you exported.", 8000);
    }
  }

  async function forget() {
    if (!confirm("Remove the RSV-2CE from this browser? You can load the file again at any time.")) return;
    await Library.clear();
    bible = null;
    buildBibleTab(); buildSettings(); rerender();
  }

  // ------------------------------------------------------------------ misc

  let toastTimer = null;
  function toast(msg, ms = 3000) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, ms);
  }

  function todaysPsalms() {
    const now = new Date();
    go(`#/day/${Psalter.courseDay(now.getDate())}/${now.getHours() < 14 ? "morning" : "evening"}`);
  }

  function wireForms() {
    content().querySelectorAll("form.lesson-form").forEach(f => f.addEventListener("submit", e => {
      e.preventDefault();
      const key = `office.lessons.${route.date}.${route.office}`;
      const lessons = store.get(key, []);
      while (lessons.length <= +f.dataset.idx) lessons.push("");
      lessons[+f.dataset.idx] = f.elements.ref.value.trim();
      store.set(key, lessons);
      rerender();
    }));
    content().querySelectorAll("form.search-form").forEach(f => {
      f.addEventListener("submit", e => { e.preventDefault(); search(f.elements.q.value, f.elements.scope.value); });
      f.elements.scope.addEventListener("change", () => search(f.elements.q.value, f.elements.scope.value));
      if (!f.elements.q.value) f.elements.q.focus();
    });
  }

  function onAction(el, e) {
    e.preventDefault();
    switch (el.dataset.act) {
      case "load": $("#file").click(); break;
      case "forget": forget(); break;
      case "canticle": store.set(`office.canticle.${el.dataset.office}.${el.dataset.idx}`, el.dataset.key); rerender(); break;
      case "todays-psalms": todaysPsalms(); drawerAfterNav(); break;
      case "unmark": { const m = bookmarks(); m.splice(+el.dataset.i, 1); store.set("bookmarks", m); buildBookmarks(); break; }
      case "copy": copy("default"); break;
      case "copy-plain": copy("plain"); break;
      case "copy-ref": copy("ref"); break;
      case "bookmark": addBookmark(); break;
      case "clear": setSelected([]); break;
      case "settings": buildSettings(); $("#settings").showModal(); break;
      case "menu": openDrawer(!document.body.classList.contains("drawer-open")); break;
      case "prev": step(-1); break;
      case "next": step(1); break;
    }
  }

  // ------------------------------------------------------------------ start

  async function start() {
    applyPrefs();
    setTab(store.get("tab", "bible"));
    openDrawer(wide.matches && store.get("drawer", true));

    let lastPointer = "mouse";
    document.addEventListener("pointerdown", e => { lastPointer = e.pointerType; }, true);

    document.addEventListener("click", e => {
      const act = e.target.closest("[data-act]");
      if (act) return onAction(act, e);
      const tab = e.target.closest(".tabs button");
      if (tab) return setTab(tab.dataset.tab);
      const a = e.target.closest('a[href^="#"]');
      if (a) {
        e.preventDefault();
        hidePopover();
        if (a.getAttribute("href") === "#") return;
        if (a.closest("#drawer")) drawerAfterNav();
        const href = a.getAttribute("href");
        if (href.startsWith("#/verse/") && route.t === "chapter" && bible) {
          const r = bible.byId.get(Number(href.split("/")[2]));
          if (r && r.book === route.book && r.chapter === route.chapter) return scrollToKey("b:" + r.id, true);
        }
        return go(href);
      }
      const num = e.target.closest("#content .vn, #content .chapnum, #content .pvn, #content .pv:has(.dropcap) .dropcap");
      if (num) { e.preventDefault(); return clickVerse(num, e, lastPointer === "touch"); }
      const mark = e.target.closest(".fn, .dn");
      if (mark) {
        const h = noteHtml(mark);
        if (h) { showPopover(mark, h); e.stopPropagation(); return; }
      }
      if (!e.target.closest("#popover")) hidePopover();
    });

    let hoverTimer = null;
    document.addEventListener("mouseover", e => {
      const mark = e.target.closest?.(".fn, .dn");
      if (!mark) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => { const h = noteHtml(mark); if (h) showPopover(mark, h); }, 250);
    });
    document.addEventListener("mouseout", e => { if (e.target.closest?.(".fn, .dn")) clearTimeout(hoverTimer); });

    // Copy (Ctrl+C, the browser's Copy, or a button) puts the passage and its reference on the clipboard.
    document.addEventListener("copy", e => {
      if (!pendingCopy && e.target.closest && e.target.closest("input, textarea, #popover")) return;
      const data = pendingCopy || payload();
      if (!data) return;
      e.clipboardData.setData("text/plain", data.plain);
      if (data.html) e.clipboardData.setData("text/html", data.html);
      e.preventDefault();
      if (!pendingCopy) toast(`Copied ${data.label}`);
    });

    document.addEventListener("keydown", e => {
      const inField = e.target.closest("input, textarea, select, dialog");
      const mod = e.ctrlKey || e.metaKey;
      const k = e.key.toLowerCase();
      if (mod && k === "k") { e.preventDefault(); $("#omni input").focus(); $("#omni input").select(); return; }
      if (inField) return;
      if (e.key === "/") { e.preventDefault(); $("#omni input").focus(); $("#omni input").select(); }
      else if (mod && k === "c" && e.shiftKey) { e.preventDefault(); copy("plain"); }
      else if (mod && k === "c") {
        // No copy event fires when nothing is highlighted; copy the chosen verses instead.
        if (getSelection().isCollapsed && selectedKeys().length) { e.preventDefault(); copy("default"); }
      } else if (mod && k === "d") { e.preventDefault(); addBookmark(); }
      else if (mod && k === "a" && ["chapter", "coverdale", "day", "canticle"].includes(route.t)) { e.preventDefault(); setSelected(orderedKeys()); }
      else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !mod && !e.altKey && !e.shiftKey) {
        e.preventDefault(); step(e.key === "ArrowLeft" ? -1 : 1);
      } else if (e.key === "Escape") { setSelected([]); hidePopover(); getSelection().removeAllRanges(); }
    });

    addEventListener("scroll", hidePopover, { passive: true });
    addEventListener("popstate", e => render(e.state && typeof e.state.scroll === "number" ? e.state.scroll : 0));

    $("#omni").addEventListener("submit", e => {
      e.preventDefault();
      const input = $("#omni input"), text = input.value.trim();
      if (!text) return;
      input.value = "";
      input.blur();
      if (/^[?/]/.test(text)) return search(text.slice(1));
      if (!goText(text)) search(text);
    });
    $("#omni-books").innerHTML = Books.BOOKS.map(b => `<option value="${escHtml(b.name)}">`).join("");
    $("#scrim").addEventListener("click", () => openDrawer(false));
    $("#file").addEventListener("change", e => { const f = e.target.files[0]; e.target.value = ""; if (f) loadFile(f); });
    $("#settings").addEventListener("change", onSettingsInput);
    $("#settings").addEventListener("click", e => {
      const th = e.target.closest("[data-theme]"), sz = e.target.closest("[data-size]");
      if (th) { prefs.theme = th.dataset.theme; }
      else if (sz) { prefs.font_size = Math.max(12, Math.min(40, prefs.font_size + Number(sz.dataset.size))); }
      else if (e.target === $("#settings") || e.target.closest(".close")) { $("#settings").close(); return; }
      else return;
      savePrefs(); applyPrefs(); buildSettings(); rerender();
    });

    psalter = new Psalter(await (await fetch("coverdale.json")).json());
    buildPsalterTab();
    buildBookmarks();
    try {
      const buf = await Library.load();
      if (buf) bible = new Bible(await Library.decode(buf));
    } catch (e) { console.error(e); }
    buildBibleTab();

    if (!location.hash || location.hash === "#" || location.hash === "#/") {
      const last = store.get("last", null);
      history.replaceState({ scroll: 0 }, "", last || (bible ? "#/chapter/50/1" : "#/welcome"));
    }
    render(history.state?.scroll ?? 0);
    document.body.classList.remove("loading");

    if ("serviceWorker" in navigator && location.protocol === "https:")
      navigator.serviceWorker.register("sw.js").catch(() => {});
  }

  return { start };
})();

App.start();
