// Canonical book list (Catholic canon, RSV-2CE order) and reference parsing.
// A port of lectern/books.py: keep the two in step.
"use strict";

const Books = (() => {
  const RAW = [
    ["Gen", "Genesis", "Gen", "OT", false, ["gn", "ge"]],
    ["Exod", "Exodus", "Ex", "OT", false, ["exo", "exod"]],
    ["Lev", "Leviticus", "Lev", "OT", false, ["lv", "le"]],
    ["Num", "Numbers", "Num", "OT", false, ["nm", "nu", "nb"]],
    ["Deut", "Deuteronomy", "Deut", "OT", false, ["dt", "de"]],
    ["Josh", "Joshua", "Josh", "OT", false, ["jos", "jsh", "josue"]],
    ["Judg", "Judges", "Judg", "OT", false, ["jdg", "jg", "jgs"]],
    ["Ruth", "Ruth", "Ruth", "OT", false, ["ru", "rth"]],
    ["1Sam", "1 Samuel", "1 Sam", "OT", false, ["1 sm", "1 sa", "1 kingdoms"]],
    ["2Sam", "2 Samuel", "2 Sam", "OT", false, ["2 sm", "2 sa", "2 kingdoms"]],
    ["1Kgs", "1 Kings", "1 Kings", "OT", false, ["1 kgs", "1 ki", "1 kg"]],
    ["2Kgs", "2 Kings", "2 Kings", "OT", false, ["2 kgs", "2 ki", "2 kg"]],
    ["1Chr", "1 Chronicles", "1 Chron", "OT", false, ["1 chr", "1 ch", "1 paralipomenon", "1 par"]],
    ["2Chr", "2 Chronicles", "2 Chron", "OT", false, ["2 chr", "2 ch", "2 paralipomenon", "2 par"]],
    ["Ezra", "Ezra", "Ezra", "OT", false, ["ezr", "1 esdras"]],
    ["Neh", "Nehemiah", "Neh", "OT", false, ["ne", "2 esdras"]],
    ["Tob", "Tobit", "Tob", "OT", true, ["tb", "tobias"]],
    ["Jdt", "Judith", "Jud", "OT", true, ["jdt", "jdth"]],
    ["Esth", "Esther", "Esther", "OT", false, ["est", "esth", "es"]],
    ["Job", "Job", "Job", "OT", false, ["jb"]],
    ["Ps", "Psalms", "Ps", "OT", false, ["psalm", "pss", "psa", "psalter"]],
    ["Prov", "Proverbs", "Prov", "OT", false, ["pr", "prv", "pro"]],
    ["Eccl", "Ecclesiastes", "Eccles", "OT", false, ["eccl", "ecc", "qoh", "qoheleth", "ec"]],
    ["Song", "Song of Solomon", "Song", "OT", false,
      ["song of songs", "sg", "canticle of canticles", "canticles", "cant", "sos", "ss"]],
    ["Wis", "Wisdom", "Wis", "OT", true, ["wisdom of solomon", "ws"]],
    ["Sir", "Sirach", "Sir", "OT", true, ["ecclesiasticus", "ecclus"]],
    ["Isa", "Isaiah", "Is", "OT", false, ["isa", "isaias"]],
    ["Jer", "Jeremiah", "Jer", "OT", false, ["jr", "jeremias"]],
    ["Lam", "Lamentations", "Lam", "OT", false, ["la"]],
    ["Bar", "Baruch", "Bar", "OT", true, ["ba"]],
    ["Ezek", "Ezekiel", "Ezek", "OT", false, ["ez", "eze", "ezk", "ezechiel"]],
    ["Dan", "Daniel", "Dan", "OT", false, ["dn", "da"]],
    ["Hos", "Hosea", "Hos", "OT", false, ["ho", "osee"]],
    ["Joel", "Joel", "Joel", "OT", false, ["jl"]],
    ["Amos", "Amos", "Amos", "OT", false, ["am"]],
    ["Obad", "Obadiah", "Obad", "OT", false, ["ob", "abdias"]],
    ["Jonah", "Jonah", "Jon", "OT", false, ["jnh", "jonas"]],
    ["Mic", "Micah", "Mic", "OT", false, ["mi", "michaeas", "micheas"]],
    ["Nah", "Nahum", "Nahum", "OT", false, ["na", "nah"]],
    ["Hab", "Habakkuk", "Hab", "OT", false, ["hb", "habacuc"]],
    ["Zeph", "Zephaniah", "Zeph", "OT", false, ["zep", "zph", "sophonias"]],
    ["Hag", "Haggai", "Hag", "OT", false, ["hg", "aggeus", "aggaeus"]],
    ["Zech", "Zechariah", "Zech", "OT", false, ["zec", "zc", "zacharias"]],
    ["Mal", "Malachi", "Mal", "OT", false, ["ml", "malachias"]],
    ["1Macc", "1 Maccabees", "1 Mac", "OT", true, ["1 macc", "1 mc", "1 machabees", "1 ma"]],
    ["2Macc", "2 Maccabees", "2 Mac", "OT", true, ["2 macc", "2 mc", "2 machabees", "2 ma"]],
    ["Matt", "Matthew", "Mt", "NT", false, ["matt", "mat"]],
    ["Mark", "Mark", "Mk", "NT", false, ["mrk", "mar", "mr"]],
    ["Luke", "Luke", "Lk", "NT", false, ["luk", "lu"]],
    ["John", "John", "Jn", "NT", false, ["jhn", "joh"]],
    ["Acts", "Acts", "Acts", "NT", false, ["ac", "act", "the acts", "acts of the apostles"]],
    ["Rom", "Romans", "Rom", "NT", false, ["ro", "rm"]],
    ["1Cor", "1 Corinthians", "1 Cor", "NT", false, ["1 co"]],
    ["2Cor", "2 Corinthians", "2 Cor", "NT", false, ["2 co"]],
    ["Gal", "Galatians", "Gal", "NT", false, ["ga"]],
    ["Eph", "Ephesians", "Eph", "NT", false, ["ep"]],
    ["Phil", "Philippians", "Phil", "NT", false, ["php", "pp"]],
    ["Col", "Colossians", "Col", "NT", false, ["co"]],
    ["1Thess", "1 Thessalonians", "1 Thess", "NT", false, ["1 th", "1 thes"]],
    ["2Thess", "2 Thessalonians", "2 Thess", "NT", false, ["2 th", "2 thes"]],
    ["1Tim", "1 Timothy", "1 Tim", "NT", false, ["1 ti", "1 tm"]],
    ["2Tim", "2 Timothy", "2 Tim", "NT", false, ["2 ti", "2 tm"]],
    ["Titus", "Titus", "Tit", "NT", false, ["ti"]],
    ["Phlm", "Philemon", "Philem", "NT", false, ["phm", "phlm", "philem"]],
    ["Heb", "Hebrews", "Heb", "NT", false, ["he"]],
    ["Jas", "James", "Jas", "NT", false, ["jm", "ja"]],
    ["1Pet", "1 Peter", "1 Pet", "NT", false, ["1 pt", "1 pe"]],
    ["2Pet", "2 Peter", "2 Pet", "NT", false, ["2 pt", "2 pe"]],
    ["1John", "1 John", "1 Jn", "NT", false, ["1 jo", "1 jhn", "1 john"]],
    ["2John", "2 John", "2 Jn", "NT", false, ["2 jo", "2 jhn", "2 john"]],
    ["3John", "3 John", "3 Jn", "NT", false, ["3 jo", "3 jhn", "3 john"]],
    ["Jude", "Jude", "Jude", "NT", false, ["jud"]],
    ["Rev", "Revelation", "Rev", "NT", false, ["apocalypse", "apoc", "re", "rv", "revelation of john"]],
  ];

  const BOOKS = RAW.map(([code, name, abbr, testament, deutero, aliases], i) =>
    ({ id: i + 1, code, name, abbr, testament, deutero, aliases }));
  const BY_ID = Object.fromEntries(BOOKS.map(b => [b.id, b]));
  const BY_CODE = Object.fromEntries(BOOKS.map(b => [b.code, b]));

  function norm(s) {
    s = s.toLowerCase().replace(/\./g, " ");
    s = s.replace(/^(i{1,3})\s+/, (m, g) => g.length + " ");   // II Kings -> 2 kings
    s = s.replace(/^(first|1st)\s+/, "1 ").replace(/^(second|2nd)\s+/, "2 ").replace(/^(third|3rd)\s+/, "3 ");
    s = s.replace(/^([123])\s*/, "$1 ");
    return s.replace(/\s+/g, " ").trim();
  }

  const ALIASES = new Map();
  for (const b of BOOKS)
    for (const a of [b.name, b.abbr, b.code, ...b.aliases]) if (!ALIASES.has(norm(a))) ALIASES.set(norm(a), b);
  // "Jud" is ambiguous (Judith vs Jude); prefer Judith as the RSV-2CE notes do, "jude" stays Jude.
  ALIASES.set("jud", BY_CODE.Jdt);

  function findBook(name) {
    const n = norm(name);
    if (!n) return null;
    if (ALIASES.has(n)) return ALIASES.get(n);
    const hits = new Map();
    for (const [k, b] of ALIASES) if (k.startsWith(n)) hits.set(b.id, b);
    if (hits.size === 1) return [...hits.values()][0];
    const named = BOOKS.filter(b => norm(b.name).startsWith(n));
    return named.length === 1 ? named[0] : null;
  }

  const REF_RE = new RegExp(
    String.raw`^\s*(?<book>(?:[1-3]|i{1,3}|first|second|third)?\s*[a-z][a-z .]*?)\.?\s*` +
    String.raw`(?:(?<c1>\d+)(?:\s*[:.,]\s*(?<v1>\d+)[a-z]?)?` +
    String.raw`(?:\s*[-–—]\s*(?<c2>\d+)(?:\s*[:.,]\s*(?<v2>\d+)[a-z]?)?)?)?\s*$`, "i");

  // "Jn 3:16", "ps 23", "Rom 8:28-39", "1 Cor 13", "Gen 1:1-2:3" -> {book, chapter, verse, endChapter, endVerse}
  function parseRef(text) {
    const m = REF_RE.exec(text.trim());
    if (!m) return null;
    const book = findBook(m.groups.book);
    if (!book) return null;
    const num = s => (s ? parseInt(s, 10) : null);
    const c1 = num(m.groups.c1), v1 = num(m.groups.v1), c2 = num(m.groups.c2), v2 = num(m.groups.v2);
    const ref = { book, chapter: c1, verse: v1, endChapter: null, endVerse: null };
    if (c2 !== null) {
      if (v1 !== null && v2 === null) { ref.endChapter = c1; ref.endVerse = c2; }
      else if (v1 === null && v2 === null) ref.endChapter = c2;
      else { ref.endChapter = c2; ref.endVerse = v2; }
    }
    return ref;
  }

  return { BOOKS, BY_ID, BY_CODE, findBook, parseRef };
})();
