// Format passages for the clipboard (plain text and rich text). A port of lectern/copyfmt.py.
"use strict";

const Copy = (() => {
  const DEFAULTS = {
    verse_numbers: false,
    layout: true,          // keep paragraph and poetry line breaks
    ref_style: "after",    // after | inline | before | none
    abbreviate: false,
    version: true,         // add "RSV-2CE" / "Coverdale" to the reference
    quotes: false,
    whole_verses: true,    // expand a partial selection to whole verses
  };
  const REF_STYLES = [["after", "Reference after the text"], ["inline", "Reference in brackets at the end"],
                      ["before", "Reference before the text"], ["none", "No reference"]];

  const stripFn = h => h.replace(/<sup class="fn"[^>]*>.*?<\/sup>/g, "");
  function clean(h) {
    h = stripFn(h).replace(/<span class="selah">(.*?)<\/span>/g, " $1");
    const d = document.createElement("div");
    d.innerHTML = h;
    return d.textContent.replace(/\s+/g, " ").trim();
  }
  const inlineHtml = h => stripFn(h).replace(/<span class="selah">(.*?)<\/span>/g, " <i>$1</i>")
    .replace(/<(?!\/?i>)[^>]+>/g, "").replace(/\s+/g, " ").trim();

  const refText = (ref, version, o) =>
    !(o.version && version) ? ref : o.ref_style === "inline" ? `${ref} ${version}` : `${ref} (${version})`;

  // blocks: paragraphs/stanzas -> lines -> [[num|null, text, html], ...]
  class Passage {
    constructor(blocks, reference, version = "") { Object.assign(this, { blocks, reference, version }); }

    plain(o) {
      const nl = o.layout ? "\n" : " ";
      let body = this.blocks.map(block => block.map(line =>
        line.map(([num, text]) => (num && o.verse_numbers ? `${num} ${text}` : text)).filter(Boolean).join(" ")
      ).filter(Boolean).join(nl)).filter(Boolean).join(nl).trim();
      if (o.quotes) body = `“${body}”`;
      if (o.ref_style === "none" || !this.reference) return body;
      const ref = refText(this.reference, this.version, o);
      if (o.ref_style === "before") return `${ref}\n${body}`;
      if (o.ref_style === "inline") return `${body} (${ref})`;
      return `${body}\n— ${ref}`;
    }

    html(o) {
      const paras = this.blocks.map(block => block.map(line =>
        line.map(([num, , h]) => (num && o.verse_numbers ? `<sup>${num}</sup>${h}` : h)).filter(Boolean).join(" ")
      ).filter(Boolean).join(o.layout ? "<br>" : " ")).filter(Boolean);
      let body = o.layout ? paras.map(p => `<p>${p}</p>`).join("") : `<p>${paras.join(" ")}</p>`;
      if (o.quotes) body = body.replace(/^<p>/, "<p>“").replace(/<\/p>$/, "”</p>");
      if (o.ref_style === "none" || !this.reference) return body;
      const ref = escHtml(refText(this.reference, this.version, o));
      if (o.ref_style === "before") return `<p><b>${ref}</b></p>${body}`;
      if (o.ref_style === "inline") return body.replace(/<\/p>$/, ` (${ref})</p>`);
      return `${body}<p>— ${ref}</p>`;
    }
  }

  function biblePassage(bible, rows, o, partialText) {
    const ref = bible.refLabel(rows, o.abbreviate);
    if (partialText && !o.whole_verses) {
      const lines = partialText.split("\n").map(l => l.trim()).filter(Boolean).map(l => [[null, l, escHtml(l)]]);
      return new Passage([lines], ref, "RSV-2CE");
    }
    const blocks = [], poetry = [];
    for (const r of rows) {
      let first = true;
      for (const [kind, h] of r.segs) {
        if (kind === "h" || (kind === "t" && r.verse !== 0)) continue;
        const text = clean(h);
        if (!text) continue;
        const piece = [first && r.verse > 0 ? Bible.label(r) : null, text, inlineHtml(h)];
        first = false;
        if (kind === "l" || kind === "i") {
          if (blocks.length && poetry[poetry.length - 1]) blocks[blocks.length - 1].push([piece]);
          else { blocks.push([[piece]]); poetry.push(true); }
        } else if (kind === "p" || kind === "t" || !blocks.length) { blocks.push([[piece]]); poetry.push(false); }
        else { const b = blocks[blocks.length - 1]; b[b.length - 1].push(piece); }
      }
    }
    return new Passage(blocks, ref, "RSV-2CE");
  }

  function psalterPassage(psalter, keys, o, pointing) {
    if (!keys.length) return new Passage([], "");
    const sep = pointing === "*" ? " * " : ": ";
    const lines = keys.map(([n, v]) => {
      const [, a, b] = psalter.psalms[n].verses[v - 1];
      return [[String(v), clean(a) + sep + clean(b), a + sep + b]];
    });
    const ps = [...new Set(keys.map(k => k[0]))].sort((a, b) => a - b);
    let ref;
    if (ps.length === 1) {
      const n = ps[0], vs = keys.map(k => k[1]), full = psalter.psalms[n].verses.length;
      if (vs.length === full && vs.every((v, i) => v === i + 1)) ref = `Psalm ${n}`;
      else if (vs.length === 1) ref = `Psalm ${n}:${vs[0]}`;
      else ref = `Psalm ${n}:${vs[0]}–${vs[vs.length - 1]}`;
    } else ref = `Psalms ${ps[0]}–${ps[ps.length - 1]}`;
    if (o.abbreviate) ref = ref.replace("Psalms", "Pss").replace("Psalm", "Ps");
    return new Passage([lines], ref, "Coverdale");
  }

  function canticlePassage(psalter, key, verses, pointing) {
    const c = psalter.canticles[key];
    const sep = pointing === "*" ? " * " : ": ";
    const lines = verses.map(i => [[String(i), clean(c.verses[i - 1][0]) + sep + clean(c.verses[i - 1][1]),
                                    c.verses[i - 1][0] + sep + c.verses[i - 1][1]]]);
    return new Passage([lines], c.title, "BCP");
  }

  return { DEFAULTS, REF_STYLES, Passage, biblePassage, psalterPassage, canticlePassage };
})();
