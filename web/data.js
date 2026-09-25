// Text access for Lectern on the web: the RSV-2CE (loaded from the user's own export and kept in
// this browser's IndexedDB) and the bundled Coverdale Psalter. A port of lectern/store.py.
"use strict";

// ------------------------------------------------------------------ local storage of the Bible file

const Library = (() => {
  const DB = "lectern", STORE = "files", KEY = "rsv2ce";

  function open() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function tx(mode, fn) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode);
      const req = fn(t.objectStore(STORE));
      t.oncomplete = () => resolve(req && req.result);
      t.onerror = () => reject(t.error);
    });
  }
  const load = () => tx("readonly", s => s.get(KEY));
  const save = buf => tx("readwrite", s => s.put(buf, KEY));
  const clear = () => tx("readwrite", s => s.delete(KEY));

  // Accepts the export as .json.gz or plain .json; returns the parsed object.
  async function decode(buf) {
    const bytes = new Uint8Array(buf);
    let text;
    if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
      text = await new Response(stream).text();
    } else {
      text = new TextDecoder().decode(bytes);
    }
    const data = JSON.parse(text);
    if (data.format !== "lectern-web" || !Array.isArray(data.verses))
      throw new Error("This isn't a Lectern export. Make one with tools/export_web.py.");
    return data;
  }

  return { load, save, clear, decode };
})();

// ------------------------------------------------------------------ the RSV-2CE

const SCOPES = [
  ["all", "Whole Bible"], ["ot", "Old Testament"], ["nt", "New Testament"], ["pentateuch", "Pentateuch"],
  ["history", "Historical books"], ["wisdom", "Wisdom books"], ["prophets", "Prophets"], ["gospels", "Gospels"],
  ["epistles", "Acts, Letters & Revelation"], ["deutero", "Deuterocanonical books"], ["psalter", "Coverdale Psalter"],
];
const SCOPE_TEST = {
  all: () => true,
  ot: b => b <= 46, nt: b => b >= 47,
  pentateuch: b => b >= 1 && b <= 5,
  history: b => (b >= 6 && b <= 19) || b === 45 || b === 46,
  wisdom: b => b >= 20 && b <= 26,
  prophets: b => b >= 27 && b <= 44,
  gospels: b => b >= 47 && b <= 50,
  epistles: b => b >= 51,
  deutero: b => [17, 18, 25, 26, 30, 45, 46].includes(b),
};

const escHtml = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const reEscape = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// How searchable text is normalised: Melchiz'edek -> Melchizedek, accents dropped.
const searchForm = s => s.replace(/(?<=\w)'(?=\w)/g, "").normalize("NFD").replace(/\p{M}/gu, "").replace(/\n/g, " ");

// A friendly query ("exact phrase", forgiv*, -exclude, mercy OR compassion) -> {pos: [[term, ...]], neg: [term]}
function parseQuery(user) {
  const parts = user.match(/-?"[^"]+"|\S+/g) || [];
  const pos = [], neg = [];
  let pendingOr = false;
  for (let p of parts) {
    if (p === "OR") { pendingOr = pos.length > 0; continue; }
    const negate = p.startsWith("-") && p.length > 1;
    if (negate) p = p.slice(1);
    const star = p.endsWith("*");
    let core = p.replace(/^"|"$/g, "").replace(/\*+$/, "");
    core = searchForm(core).replace(/[^\p{L}\p{N}\s']/gu, " ").replace(/'/g, "").trim();
    if (!core) continue;
    const words = core.split(/\s+/);
    const src = words.map(reEscape).join("[^\\p{L}\\p{N}]+") + (star ? "[\\p{L}\\p{N}]*" : "");
    const term = new RegExp(`(?<![\\p{L}\\p{N}])${src}(?![\\p{L}\\p{N}])`, "giu");
    if (negate) neg.push(term);
    else if (pendingOr && pos.length) { pos[pos.length - 1].push(term); pendingOr = false; }
    else pos.push([term]);
  }
  return pos.length ? { pos, neg } : null;
}

// Wrap every match of the given patterns in <mark>, escaping the rest.
function highlight(text, patterns) {
  const ranges = [];
  for (const re of patterns) {
    re.lastIndex = 0;
    for (const m of text.matchAll(re)) if (m[0]) ranges.push([m.index, m.index + m[0].length]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  let out = "", at = 0;
  for (const [a, b] of ranges) {
    if (a < at) continue;
    out += escHtml(text.slice(at, a)) + "<mark>" + escHtml(text.slice(a, b)) + "</mark>";
    at = b;
  }
  return out + escHtml(text.slice(at));
}

class Bible {
  constructor(data) {
    this.source = data.source;
    this.books = data.books.map(([id, code, name, abbr, testament, deutero, title]) =>
      ({ id, code, name, abbr, testament, deutero: !!deutero, title: title || name }));
    this.bookById = Object.fromEntries(this.books.map(b => [b.id, b]));
    this.verses = data.verses.map(([id, book, chapter, verse, verseEnd, segs, text]) =>
      ({ id, book, chapter, verse, verseEnd, segs, text }));
    this.byId = new Map(this.verses.map(v => [v.id, v]));
    this.byChapter = new Map();
    this._chapters = new Map();
    for (const v of this.verses) {
      const k = v.book * 1000 + v.chapter;
      if (!this.byChapter.has(k)) {
        this.byChapter.set(k, []);
        if (!this._chapters.has(v.book)) this._chapters.set(v.book, []);
        this._chapters.get(v.book).push(v.chapter);
      }
      this.byChapter.get(k).push(v);
    }
    for (const list of this._chapters.values()) list.sort((a, b) => a - b);
    this.seq = [...this._chapters.keys()].sort((a, b) => a - b)
      .flatMap(b => this._chapters.get(b).map(c => [b, c]));
    this.alt = new Map(data.alt.map(([b, c, a]) => [b * 1000 + c, a]));
    this.notes = data.notes;
    this.verseNotes = new Map();
    for (const [vid, kind, noteId, marker] of data.verse_notes) {
      if (!this.verseNotes.has(vid)) this.verseNotes.set(vid, []);
      this.verseNotes.get(vid).push({ verse_id: vid, kind, marker, note_id: noteId });
    }
    this._search = null;
  }

  static label(r) {
    if (r.verse === 0) return "title";
    return r.verseEnd > r.verse ? `${r.verse}–${r.verseEnd}` : String(r.verse);
  }

  chapters(book) { return this._chapters.get(book) || []; }
  altNumber(book, chapter) { return this.alt.get(book * 1000 + chapter); }
  chapter(book, chapter) { return this.byChapter.get(book * 1000 + chapter) || []; }

  neighbour(book, chapter, step) {
    const i = this.seq.findIndex(([b, c]) => b === book && c === chapter);
    if (i < 0) return null;
    return this.seq[i + step] || null;
  }

  versesByIds(ids) {
    return [...new Set(ids)].map(i => this.byId.get(i)).filter(Boolean).sort((a, b) => a.id - b.id);
  }

  versesForRef(ref) {
    const b = ref.book.id;
    const inBook = () => this.chapters(b).flatMap(c => this.chapter(b, c));
    if (ref.chapter === null) return inBook();
    const c1 = ref.chapter, v1 = ref.verse;
    const c2 = ref.endChapter !== null ? ref.endChapter : c1;
    let v2 = ref.endVerse;
    const range = [];
    for (const c of this.chapters(b)) if (c >= c1 && c <= c2) range.push(...this.chapter(b, c));
    if (v1 === null) return range;
    if (v2 === null) v2 = ref.endChapter !== null && ref.endChapter !== c1 ? 10000 : v1;
    return range.filter(r => r.verse > 0 &&
      (r.chapter > c1 || (r.chapter === c1 && r.verseEnd >= v1)) &&
      (r.chapter < c2 || (r.chapter === c2 && r.verse <= v2)));
  }

  notesFor(ids) {
    const out = [];
    for (const id of ids) for (const n of this.verseNotes.get(id) || []) {
      const note = this.notes[n.note_id];
      if (note) out.push({ ...n, html: note[1] });
    }
    return out;
  }

  refLabel(rows, abbreviate = false) {
    rows = rows.filter(r => r.verse > 0).length ? rows.filter(r => r.verse > 0) : rows;
    if (!rows.length) return "";
    const first = rows[0], last = rows[rows.length - 1];
    const b = Books.BY_ID[first.book];
    let name = abbreviate ? b.abbr : b.name;
    if (first.book === 21 && !abbreviate) name = first.chapter === last.chapter ? "Psalm" : "Psalms";
    const endV = Math.max(last.verse, last.verseEnd);
    const chap = this.chapter(first.book, first.chapter).filter(r => r.verse > 0);
    let whole = false;
    if (first.chapter === last.chapter && chap.length && first.id === chap[0].id && last.id === chap[chap.length - 1].id)
      whole = rows.length > 1 || chap.length === 1;
    if (whole) return `${name} ${first.chapter}`;
    if (first.chapter === last.chapter)
      return first.verse === endV ? `${name} ${first.chapter}:${first.verse}` : `${name} ${first.chapter}:${first.verse}–${endV}`;
    return `${name} ${first.chapter}:${first.verse}–${last.chapter}:${endV}`;
  }

  search(query, scope = "all", book = null, limit = 400) {
    const q = parseQuery(query);
    if (!q) return { total: 0, rows: [], books: {}, error: null };
    if (!this._search) this._search = this.verses.map(v => searchForm(v.text));
    const inScope = book ? b => b === book : (SCOPE_TEST[scope] || SCOPE_TEST.all);
    const hit = (re, s) => { re.lastIndex = 0; return re.test(s); };
    const rows = [], books = {};
    let total = 0;
    this.verses.forEach((v, i) => {
      if (!inScope(v.book)) return;
      const s = this._search[i];
      if (!q.pos.every(group => group.some(re => hit(re, s)))) return;
      if (q.neg.some(re => hit(re, s))) return;
      total++;
      books[v.book] = (books[v.book] || 0) + 1;
      if (rows.length < limit)
        rows.push({ id: v.id, book: v.book, chapter: v.chapter, verse: v.verse, verseEnd: v.verseEnd,
                    html: highlight(s, q.pos.flat()) });
    });
    return { total, rows, books, error: null };
  }
}

// ------------------------------------------------------------------ the Coverdale Psalter

class Psalter {
  constructor(data) {
    this.data = data;
    this.psalms = Object.fromEntries(Object.entries(data.psalms).map(([k, v]) => [Number(k), v]));
    this.days = Object.fromEntries(Object.entries(data.days).map(([k, v]) => [Number(k), v]));
    this.canticles = Object.fromEntries(data.canticles.map(c => [c.key, c]));
    this.gloria = data.gloria;
  }

  // 1662: on the 31st the psalms of the 30th are repeated.
  static courseDay(day) { return Math.min(day, 30); }

  appointed(day, office) {
    return this.days[Psalter.courseDay(day)][office].map(e =>
      Array.isArray(e) ? e : [e, 1, this.psalms[e].verses.length]);
  }

  search(query, limit = 400) {
    const words = (query.match(/"[^"]+"|\S+/g) || []).map(w => w.toLowerCase())
      .filter(w => !w.startsWith("-") && w !== "or").map(w => w.replace(/"/g, ""));
    if (!words.length) return { total: 0, rows: [], books: {}, error: null };
    const pats = words.map(w => new RegExp("\\b" + reEscape(w.replace(/\*+$/, "")) + (w.endsWith("*") ? "\\w*" : "\\b"), "gi"));
    const rows = [];
    let total = 0;
    for (const n of Object.keys(this.psalms).map(Number).sort((a, b) => a - b)) {
      for (const [num, first, second] of this.psalms[n].verses) {
        const plain = `${first}: ${second}`.replace(/<[^>]+>/g, "");
        if (pats.every(p => { p.lastIndex = 0; return p.test(plain); })) {
          total++;
          if (rows.length < limit) rows.push({ psalm: n, verse: num, html: highlight(plain, pats) });
        }
      }
    }
    return { total, rows, books: {}, error: null };
  }
}
