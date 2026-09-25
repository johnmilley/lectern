// HTML for the reading pane: Bible chapters, the Psalter, the Office, search results.
// A port of lectern/render.py; links are hash routes (#/chapter/50/3) instead of lectern: URLs.
"use strict";

const Render = (() => {
  const esc = escHtml;

  // LORD / GOD (the divine name) set in small capitals, as in the printed edition.
  const divine = s => s.replace(/\b(LORD|GOD)(’s|'s)?\b/g,
    (m, w, poss) => `<span class="sc">${w[0]}${w.slice(1).toLowerCase()}</span>${poss || ""}`);
  const links = h => h.replace(/href="ref:(\d+)\.(\d+)\.(\d+)"/g, 'href="#/ref/$1/$2/$3"');

  function ordinal(n) {
    const suf = n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th");
    return n + suf;
  }

  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                  "October", "November", "December"];
  const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const isoDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const parseDate = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const addDays = (s, n) => { const d = parseDate(s); d.setDate(d.getDate() + n); return isoDate(d); };

  function chapLabel(bible, book, chapter) {
    return book === 21 ? `Psalm ${chapter}` : `${bible.bookById[book].name} ${chapter}`;
  }

  // ------------------------------------------------------------------ Bible chapters

  function chapter(bible, book, chap, opts) {
    const rows = bible.chapter(book, chap);
    const b = bible.bookById[book];
    const notes = bible.notesFor(rows.map(r => r.id));
    const alt = bible.altNumber(book, chap);
    const chapters = bible.chapters(book);
    const out = ['<header class="chap-head">'];
    out.push(chap === chapters[0] ? `<div class="book-title">${esc(b.title)}</div>`
                                   : `<div class="running-title">${esc(b.title)}</div>`);
    const altHtml = alt ? ` <span class="alt">[${alt}]</span>` : "";
    out.push(`<h1 class="chap-title">${book === 21 ? "Psalm" : "Chapter"} ${chap}${altHtml}</h1>`);
    if (book === 21) out.push(`<div class="crosslink"><a href="#/coverdale/${chap}">Read in the Coverdale Psalter &#x203A;</a></div>`);
    out.push("</header>");
    const docIds = new Set(notes.filter(n => n.kind === "doc").map(n => n.verse_id));
    const noteMap = Object.fromEntries(notes.map(n => [n.note_id, { kind: n.kind, html: n.html }]));
    out.push('<article class="text">', versesHtml(rows, docIds, true), "</article>");
    if (opts.endnotes && notes.length) out.push(endnotes(rows, notes));
    const prev = bible.neighbour(book, chap, -1), next = bible.neighbour(book, chap, 1);
    out.push('<nav class="pager">');
    out.push(prev ? `<a href="#/chapter/${prev[0]}/${prev[1]}">&#x2039; ${esc(chapLabel(bible, ...prev))}</a>` : "<span></span>");
    if (next) out.push(`<a href="#/chapter/${next[0]}/${next[1]}">${esc(chapLabel(bible, ...next))} &#x203A;</a>`);
    out.push("</nav>");
    return { html: out.join("\n"), data: { kind: "bible", notes: noteMap } };
  }

  function versesHtml(rows, docIds, chapterNumerals = false) {
    const out = [];
    let mode = null, lineOpen = false;
    const close = () => {
      if (mode === "prose") out.push("</p>");
      else if (mode === "poetry") { if (lineOpen) out.push("</div>"); out.push("</div>"); }
      mode = null; lineOpen = false;
    };
    const openProse = () => { close(); out.push('<p class="prose">'); mode = "prose"; };
    const newLine = indent => {
      if (mode !== "poetry") { close(); out.push('<div class="poetry">'); mode = "poetry"; }
      else if (lineOpen) out.push("</div>");
      out.push(`<div class="line${indent ? " indent" : ""}">`);
      lineOpen = true;
    };
    let prevChapter = null;
    for (const r of rows) {
      let started = false;
      for (const [kind, raw] of r.segs) {
        const h = divine(raw);
        if (kind === "h") { close(); out.push(`<h3 class="heading">${h}</h3>`); continue; }
        if (kind === "t") { close(); out.push(`<p class="title"><span class="v" data-id="${r.id}">${h}</span></p>`); continue; }
        if (kind === "p") openProse();
        else if (kind === "l" || kind === "i") newLine(kind === "i");
        else if (mode === null) openProse();
        let marker = "";
        if (!started && r.verse > 0) {
          started = true;
          if (r.verse === 1 && r.chapter !== prevChapter && chapterNumerals)
            marker = `<span class="chapnum" data-id="${r.id}">${r.chapter}</span>`;
          else marker = `<sup class="vn" data-id="${r.id}">${esc(Bible.label(r))}</sup>`;
          if (docIds.has(r.id)) marker += `<sup class="dn" data-verse="${r.id}" title="Doctrinal note">*</sup>`;
          prevChapter = r.chapter;
        }
        out.push(`<span class="v" data-id="${r.id}">${marker}${h} </span>`);
      }
    }
    close();
    return out.join("\n");
  }

  function endnotes(rows, notes) {
    const byId = new Map(rows.map(r => [r.id, r]));
    const ref = n => { const r = byId.get(n.verse_id); return `<a class="nref" href="#/verse/${r.id}">${r.chapter}:${esc(Bible.label(r))}</a>`; };
    const fn = notes.filter(n => n.kind === "fn"), dn = notes.filter(n => n.kind === "doc"), xr = notes.filter(n => n.kind === "xref");
    const out = ['<section class="endnotes">'];
    if (fn.length) {
      out.push('<h4>Notes</h4><ol class="notes notes-fn">');
      for (const n of fn) out.push(`<li id="n-${esc(n.note_id)}">${ref(n)} <span class="mk">${esc(n.marker)}</span> ${divine(n.html)}</li>`);
      out.push("</ol>");
    }
    if (xr.length) {
      out.push('<h4>Cross References</h4><ol class="notes notes-xr">');
      for (const n of xr) out.push(`<li>${ref(n)} ${links(n.html.replace(/^<b>[^<]*<\/b>\s*/, ""))}</li>`);
      out.push("</ol>");
    }
    if (dn.length) {
      out.push('<h4>Doctrinal Notes</h4><ol class="notes notes-dn">');
      for (const n of dn) out.push(`<li id="d-${n.verse_id}">${ref(n)} ${links(divine(n.html))}</li>`);
      out.push("</ol>");
    }
    out.push("</section>");
    return out.join("\n");
  }

  // Office lessons: drop section headings inside lessons, as a lectionary does.
  function passage(rows) {
    if (!rows.length) return '<p class="rubric">That passage could not be found.</p>';
    return versesHtml(rows.map(r => ({ ...r, segs: r.segs.filter(s => s[0] !== "h") })), new Set());
  }

  // ------------------------------------------------------------------ Coverdale Psalter

  const star = opts => opts.pointing === "*" ? '<span class="star">*</span>' : '<span class="colon">:</span>';
  function dropcap(a) {
    const m = /^(\W*)(\w)(\w*)([\s\S]*)$/.exec(a);
    return m ? `${m[1]}<span class="dropcap">${m[2]}</span><span class="lead">${m[3]}</span>${m[4]}` : a;
  }

  function covVerse(n, [num, a, b], opts, first) {
    a = divine(a); b = divine(b);
    if (first) a = dropcap(a);
    return `<p class="pv" data-ps="${n}" data-v="${num}"><span class="pvn">${num}</span>` +
           `<span class="pvt">${a} ${star(opts)} ${b}</span></p>`;
  }

  function gloria(psalter) {
    const g = psalter.gloria;
    return `<div class="gloria"><p>${g[0]} <span class="star">*</span> ${g[1]}</p>` +
           `<p>${g[2]} <span class="star">*</span> ${g[3]}</p></div>`;
  }

  function psalm(psalter, n, opts, first = 1, last = null, bible = null, compare = false) {
    const ps = psalter.psalms[n], verses = ps.verses;
    last = last || verses.length;
    const out = [`<section class="psalm" id="ps-${n}">`];
    const range = first === 1 && last === verses.length ? "" : `<span class="range">vv. ${first}–${last}</span>`;
    out.push(`<div class="ps-head"><span class="ps-num">Psalm ${n}.</span><span class="ps-latin">${esc(ps.latin)}.</span>${range}</div>`);
    const sections = Object.fromEntries((ps.sections || []).map(s => [s.start, s]));
    const rsv = {};
    if (compare && bible) for (const r of bible.chapter(21, n)) if (r.verse > 0) rsv[r.verse] = r;
    let started = false;
    for (const v of verses.slice(first - 1, last)) {
      const num = v[0];
      if (n === 119 && sections[num]) {
        const s = sections[num];
        out.push(`<div class="ps-section"><span class="hebrew">${esc(s.hebrew)}.</span> <span class="ps-latin">${esc(s.latin)}</span></div>`);
        started = false;
      }
      const firstVerse = !started;
      started = true;
      if (compare) {
        const r = rsv[num];
        out.push(`<div class="compare-row"><div class="cov">${covVerse(n, v, opts, firstVerse)}</div>` +
                 `<div class="rsv">${r ? versesHtml([r], new Set()) : ""}</div></div>`);
      } else out.push(covVerse(n, v, opts, firstVerse));
    }
    if (opts.gloria && (last === verses.length || n === 119)) out.push(gloria(psalter));
    out.push("</section>");
    return out.join("\n");
  }

  function psalmPage(psalter, n, opts, bible, compare) {
    const out = ['<header class="chap-head"><div class="running-title">The Psalter · Coverdale</div>' +
                 `<h1 class="chap-title">Psalm ${n}</h1>`];
    if (bible) out.push(`<div class="crosslink"><a href="#/chapter/21/${n}">Read in the RSV-2CE &#x203A;</a> · ` +
                        `<a href="#/coverdale/${n}${compare ? "" : "?compare=1"}">${compare ? "Hide" : "Show"} RSV-2CE alongside</a></div>`);
    out.push("</header>", `<article class="psalter${compare ? " compare" : ""}">`,
             psalm(psalter, n, opts, 1, null, bible, compare), "</article>", '<nav class="pager">');
    out.push(n > 1 ? `<a href="#/coverdale/${n - 1}">&#x2039; Psalm ${n - 1}</a>` : "<span></span>");
    if (n < 150) out.push(`<a href="#/coverdale/${n + 1}">Psalm ${n + 1} &#x203A;</a>`);
    out.push("</nav>");
    return { html: out.join("\n"), data: { kind: "psalter" } };
  }

  const nextOffice = (day, office, step) => step > 0
    ? (office === "morning" ? [day, "evening"] : [day === 30 ? 1 : day + 1, "morning"])
    : (office === "evening" ? [day, "morning"] : [day === 1 ? 30 : day - 1, "evening"]);

  function psalterDay(psalter, day, office, opts) {
    const cday = Psalter.courseDay(day);
    const name = office === "morning" ? "Morning Prayer" : "Evening Prayer";
    const out = ['<header class="chap-head"><div class="running-title">The Psalter · Coverdale</div>' +
                 `<h1 class="chap-title">The ${ordinal(cday)} Day</h1><div class="subtitle">${name}</div></header>`,
                 '<article class="psalter">'];
    for (const [n, a, b] of psalter.appointed(cday, office)) out.push(psalm(psalter, n, opts, a, b));
    out.push("</article>");
    const lbl = { morning: "Morning", evening: "Evening" };
    const [pd, po] = nextOffice(cday, office, -1), [nd, no] = nextOffice(cday, office, 1);
    out.push(`<nav class="pager"><a href="#/day/${pd}/${po}">&#x2039; Day ${pd}, ${lbl[po]}</a>` +
             `<a href="#/day/${nd}/${no}">Day ${nd}, ${lbl[no]} &#x203A;</a></nav>`);
    return { html: out.join("\n"), data: { kind: "psalter" } };
  }

  function canticle(psalter, key, opts) {
    const c = psalter.canticles[key];
    const out = [`<section class="canticle" id="c-${key}">`];
    const src = c.source ? `<span class="range">${esc(c.source)}</span>` : "";
    out.push(`<div class="ps-head"><span class="ps-latin big">${esc(c.title)}.</span>${src}</div>`);
    c.verses.forEach(([a, b], i) => {
      let a2 = divine(a);
      if (i === 0) a2 = dropcap(a2);
      out.push(`<p class="pv" data-cant="${key}" data-v="${i + 1}"><span class="pvt">${a2} ${star(opts)} ${divine(b)}</span></p>`);
    });
    if (key !== "te_deum" && opts.gloria) out.push(gloria(psalter));
    out.push("</section>");
    return out.join("\n");
  }

  function canticlePage(psalter, key, opts) {
    return { html: '<header class="chap-head"><div class="running-title">Canticles · Book of Common Prayer</div></header>' +
                   `<article class="psalter">${canticle(psalter, key, opts)}</article>`, data: { kind: "psalter" } };
  }

  // ------------------------------------------------------------------ Daily Office

  const OFFICE_CANTICLES = {
    morning: [["te_deum", "benedicite"], ["benedictus", "jubilate"]],
    evening: [["magnificat", "cantate"], ["nunc_dimittis", "deus_misereatur"]],
  };

  function office(psalter, bible, date, off, lessons, cants, opts) {
    const d = parseDate(date);
    const day = Psalter.courseDay(d.getDate());
    const name = off === "morning" ? "Morning Prayer" : "Evening Prayer";
    const other = off === "morning" ? "evening" : "morning";
    const datestr = `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
    const out = ['<header class="chap-head office-head"><div class="running-title">The Daily Office</div>' +
      `<h1 class="chap-title">${name}</h1><div class="subtitle">${esc(datestr)}</div>` +
      `<div class="office-nav"><a href="#/office/${addDays(date, -1)}/${off}">&#x2039; Previous day</a>` +
      `<a href="#/office/${date}/${other}">${other === "evening" ? "Evening" : "Morning"} Prayer</a>` +
      `<a href="#/office/today/${off}">Today</a>` +
      `<a href="#/office/${addDays(date, 1)}/${off}">Next day &#x203A;</a></div></header>`,
      '<article class="psalter office">'];
    if (off === "morning") {
      out.push('<p class="rubric">The Invitatory. <i>Except on the nineteenth day of the month, when it is read ' +
               "in the course of the Psalms.</i></p>");
      if (day !== 19) out.push(canticle(psalter, "venite", opts));
    }
    out.push(`<h2 class="office-section">The Psalms</h2><p class="rubric">Appointed for the ${ordinal(day)} day of the month, at ${name}.</p>`);
    for (const [n, a, b] of psalter.appointed(day, off)) out.push(psalm(psalter, n, opts, a, b));
    ["The First Lesson", "The Second Lesson"].forEach((title, i) => {
      const refTxt = (lessons[i] || "").trim();
      out.push(`<h2 class="office-section">${title}</h2>`);
      out.push(`<form class="lesson-form" data-idx="${i}"><input type="text" name="ref" enterkeyhint="done" ` +
               `placeholder="Enter the lesson, e.g. Isaiah 40:1-11" value="${esc(refTxt)}"><button type="submit">Set</button></form>`);
      if (refTxt && bible) {
        const rows = [];
        for (const piece of refTxt.split(/\s*;\s*/)) {
          const ref = Books.parseRef(piece);
          if (ref) rows.push(...bible.versesForRef(ref));
        }
        if (rows.length) {
          out.push(`<div class="lesson">${passage(rows)}</div>`);
          out.push(`<p class="rubric">Here endeth the ${i === 0 ? "First" : "Second"} Lesson.</p>`);
        } else out.push('<p class="rubric">That reference could not be read. Try a form such as “Romans 8:28-39”.</p>');
      } else if (refTxt) out.push('<p class="rubric">Load your RSV-2CE file to read the lessons here.</p>');
      const choices = OFFICE_CANTICLES[off][i];
      const chosen = choices.includes(cants[i]) ? cants[i] : choices[0];
      out.push('<div class="canticle-choice">' + choices.map(k =>
        `<a class="${k === chosen ? "on" : ""}" href="#" data-act="canticle" data-office="${off}" data-idx="${i}" data-key="${k}">` +
        `${esc(psalter.canticles[k].title)}</a>`).join("") + "</div>");
      out.push(canticle(psalter, chosen, opts));
    });
    out.push('<p class="rubric office-foot">The Creed, the Prayers and the Collects follow, as appointed ' +
             "in <i>Divine Worship: Daily Office</i>.</p></article>");
    return { html: out.join("\n"), data: { kind: "office" } };
  }

  // ------------------------------------------------------------------ search

  function search(bible, psalter, query, scope, book) {
    let res;
    if (scope === "psalter") res = psalter.search(query);
    else if (!bible) res = { total: 0, rows: [], books: {}, error: "Load your RSV-2CE file to search the Bible." };
    else res = bible.search(query, scope, book);
    const out = ['<header class="search-head"><h1 class="chap-title">Search</h1>',
                 `<form class="search-form"><input type="search" name="q" value="${esc(query)}" enterkeyhint="search"><select name="scope">`];
    for (const [key, label] of SCOPES) out.push(`<option value="${key}"${key === scope && !book ? " selected" : ""}>${esc(label)}</option>`);
    if (book && bible) out.push(`<option value="book:${book}" selected>${esc(bible.bookById[book].name)}</option>`);
    out.push('</select><button type="submit">Search</button></form>');
    if (res.error) out.push(`<p class="rubric">${esc(res.error)}</p>`);
    const shown = res.rows.length;
    const more = shown < res.total ? ` — showing the first ${shown}; choose a book below to narrow` : "";
    out.push(`<p class="search-count">${res.total} ${res.total === 1 ? "verse" : "verses"}${more}</p>`);
    const bookIds = Object.keys(res.books).map(Number).sort((a, b) => a - b);
    if (bible && bookIds.length > 1)
      out.push('<div class="chips">' + bookIds.map(b =>
        `<a class="chip" href="#/search?q=${encodeURIComponent(query)}&book=${b}">${esc(Books.BY_ID[b].abbr)} <span>${res.books[b]}</span></a>`).join("") + "</div>");
    out.push('<p class="search-tips">Tips: all words must match · use <code>"quotes"</code> for a phrase · ' +
             "<code>lov*</code> for word beginnings · <code>-word</code> to exclude · <code>OR</code> for either.</p>");
    out.push("</header><ol class='results'>");
    for (const r of res.rows) {
      let ref, href;
      if (scope === "psalter") { ref = `Psalm ${r.psalm}:${r.verse}`; href = `#/coverdale/${r.psalm}/${r.verse}`; }
      else {
        const b = Books.BY_ID[r.book];
        const v = r.verseEnd > r.verse ? `${r.verse}–${r.verseEnd}` : String(r.verse);
        ref = r.verse ? `${b.name} ${r.chapter}:${v}` : `${b.name} ${r.chapter} (title)`;
        href = `#/verse/${r.id}`;
      }
      out.push(`<li><a class="rref" href="${href}">${esc(ref)}</a> <span class="rtext">${divine(r.html)}</span></li>`);
    }
    out.push("</ol>");
    return { html: out.join("\n"), data: { kind: "search" } };
  }

  // ------------------------------------------------------------------ welcome

  function welcome(hasBible) {
    const load = hasBible
      ? '<p>Your RSV-2CE is loaded in this browser. Open a book from the <b>Contents</b>, or type a reference above.</p>'
      : `<p>The RSV-2CE is under copyright, so this site doesn't include it. Load the file you exported from the Lectern
desktop app (<code>lectern-rsv2ce.json.gz</code>). It is read here, in your browser, and kept in this browser's storage
on this device only. Nothing is uploaded.</p>
<p class="center"><button class="button" data-act="load">Load the RSV-2CE…</button></p>
<p class="small">To make the file, run <code>python tools/export_web.py</code> in the Lectern folder on the computer
where you imported the ebook. Copy it to your phone or tablet the way you'd copy any private document.</p>`;
    return { html: `
<header class="chap-head"><div class="running-title">Welcome</div><h1 class="chap-title">Lectern</h1>
<div class="subtitle">The Holy Bible · RSV Second Catholic Edition · with the Coverdale Psalter</div></header>
<article class="welcome">
${load}
<p>The Coverdale Psalter and the Prayer Book canticles are in the public domain and are included already.
<a href="#/office/today/morning">Morning Prayer</a> · <a href="#/office/today/evening">Evening Prayer</a> ·
<a href="#/coverdale/1">The Psalter</a></p>
</article>`, data: {} };
  }

  return { chapter, passage, psalmPage, psalterDay, canticlePage, office, search, welcome,
           ordinal, isoDate, parseDate, divine, links, OFFICE_CANTICLES };
})();
