/* AP3 evidence corpus: browser-assisted capture (runs in a normal browser tab on the issuer's own site).

   Why a browser: the backtest environment cannot reach federalreserve.gov, bls.gov or census.gov.
   What it does: lists the planned documents from the issuers' index pages, fetches each document from the
   same origin (at least `gapMs` apart), computes its SHA-256 in the page, and saves one uncompressed ZIP per
   family with a manifest. Nothing is parsed or altered; the importer (native_backtest/scripts/ap3_corpus_import.py)
   re-hashes every file and builds _corpus_raw/ and fetch_log.jsonl exactly as the direct fetcher would.

   Usage, pasted or injected into a tab open on the issuer's site (one family at a time):
     await AP3C.plan('bls_cpi')                 -> [{family, url, url_date, release_date}]   (index pages only)
     await AP3C.sizes(plan)                     -> plan with content_length from HEAD requests (no downloads)
     await AP3C.capture(plan, 'ap3_corpus_bls_cpi_v1')   -> saves ap3_corpus_bls_cpi_v1.zip, returns hashes
*/
(function (root) {
  'use strict';
  const SRC = {   // index rules copied from native_backtest/ap3/corpus_sources_v1.json (window 2015-01-01..2026-09-30)
    window: ['2015-01-01', '2026-09-30'],
    bls_employment_situation: { index: ['https://www.bls.gov/bls/news-release/empsit.htm'], link: /\/news\.release\/archives\/empsit_(\d{8})\.htm/g, url: d => `https://www.bls.gov/news.release/archives/empsit_${d}.htm`, mmddyyyy: true },
    bls_cpi: { index: ['https://www.bls.gov/bls/news-release/cpi.htm'], link: /\/news\.release\/archives\/cpi_(\d{8})\.htm/g, url: d => `https://www.bls.gov/news.release/archives/cpi_${d}.htm`, mmddyyyy: true },
    bls_ppi: { index: ['https://www.bls.gov/bls/news-release/ppi.htm'], link: /\/news\.release\/archives\/ppi_(\d{8})\.htm/g, url: d => `https://www.bls.gov/news.release/archives/ppi_${d}.htm`, mmddyyyy: true },
    fomc_minutes: { index: [2015, 2016, 2017, 2018, 2019, 2020].map(y => `https://www.federalreserve.gov/monetarypolicy/fomchistorical${y}.htm`).concat(['https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm']),
      link: /\/monetarypolicy\/fomcminutes(\d{8})\.htm/g, url: d => `https://www.federalreserve.gov/monetarypolicy/fomcminutes${d}.htm`, released: /Released ([A-Z][a-z]+ \d{1,2}, \d{4})/ },
    fed_g17_industrial_production: { index: ['https://www.federalreserve.gov/releases/g17/release_dates.htm'], dates: /(\d{1,2})-([A-Z][a-z]+)-(\d{4})/g, url: d => `https://www.federalreserve.gov/releases/g17/${d}/default.htm` },
    census_advance_retail_sales: { index: ['https://www.census.gov/retail/marts/historic_releases.html'], link: /https:\/\/www2\.census\.gov\/retail\/releases\/historical\/marts\/adv(\d{4})\.pdf/g },
    fomc_statement: { note: 'dates come from the vendored FOMC index (fomc_index.csv); pass them to AP3C.statementPlan(dates)',
      url: d => `https://www.federalreserve.gov/newsevents/pressreleases/monetary${d}a.htm` },
  };
  const MON = { January: 1, February: 2, March: 3, April: 4, May: 5, June: 6, July: 7, August: 8, September: 9, October: 10, November: 11, December: 12 };
  const iso = (y, m, d) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  const inWin = d => d && d >= SRC.window[0] && d <= SRC.window[1];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  const sha256 = async bytes => hex(await crypto.subtle.digest('SHA-256', bytes));
  const strip = h => h.replace(/<[^>]+>/g, ' ');
  const longDate = s => { const m = /([A-Z][a-z]+) (\d{1,2}), (\d{4})/.exec(s); return m ? iso(+m[3], MON[m[1]], +m[2]) : null; };

  async function getText(url) { const r = await fetch(url, { credentials: 'omit' }); if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`); return r.text(); }

  async function plan(family, gapMs = 2000) {
    const s = SRC[family], out = [], seen = new Set();
    if (family === 'fed_g17_industrial_production') {
      const t = strip(await getText(s.index[0]));
      for (const m of t.matchAll(s.dates)) { const d = iso(+m[3], MON[m[2]], +m[1]); if (inWin(d) && !seen.has(d)) { seen.add(d); out.push({ family, url: s.url(d.replace(/-/g, '')), url_date: d, release_date: d }); } }
      return out.sort((a, b) => a.url_date < b.url_date ? -1 : 1);
    }
    for (const pg of s.index) {
      const html = await getText(pg); await sleep(gapMs);
      for (const m of html.matchAll(s.link)) {
        const dg = m[1]; let url, d = null, rel = null;
        if (s.mmddyyyy) { d = iso(dg.slice(4, 8), dg.slice(0, 2), dg.slice(2, 4)); url = s.url(dg); rel = d; }
        else if (family === 'census_advance_retail_sales') {
          url = m[0]; const ref = iso('20' + dg.slice(0, 2), dg.slice(2, 4), 1);
          const next = new Date(ref + 'T00:00:00Z'); next.setUTCMonth(next.getUTCMonth() + 1);
          if (!inWin(next.toISOString().slice(0, 10))) continue;
          d = null;   // the release date is printed on page 1; the importer reads it from the document
        } else {
          d = iso(dg.slice(0, 4), dg.slice(4, 6), dg.slice(6, 8)); url = s.url(dg);
          const after = s.released.exec(strip(html.slice(m.index + m[0].length, m.index + m[0].length + 600)));
          const beforeAll = [...strip(html.slice(Math.max(0, m.index - 400), m.index)).matchAll(new RegExp(s.released, 'g'))];
          const before = beforeAll.length ? beforeAll[beforeAll.length - 1] : null;
          const pick = pg.includes('fomchistorical') ? (before || after) : (after || before);   // label placement differs by page
          rel = pick ? longDate(pick[1]) : null;
        }
        if (seen.has(url) || (d && !inWin(d))) continue;
        seen.add(url); out.push({ family, url, url_date: d, release_date: rel });
      }
    }
    return out;
  }

  function statementPlan(dates) {   // dates: 'YYYY-MM-DD' strings from fomc_index.csv
    return dates.filter(inWin).map(d => ({ family: 'fomc_statement', url: SRC.fomc_statement.url(d.replace(/-/g, '')), url_date: d, release_date: d }));
  }

  async function sizes(entries, gapMs = 500) {
    for (const e of entries) {
      try { const r = await fetch(e.url, { method: 'HEAD', credentials: 'omit' }); e.head_status = r.status; e.content_length = +(r.headers.get('content-length') || 0) || null; }
      catch (err) { e.head_status = 'error: ' + err.message; }
      await sleep(gapMs);
    }
    return entries;
  }

  // ---- minimal ZIP writer (stored entries, no compression), so the archive is reproducible and easy to verify
  const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = u8 => { let c = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) c = CRC[(c ^ u8[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  function zip(files) {   // files: [{name, data: Uint8Array}]
    const enc = new TextEncoder(), chunks = [], central = []; let off = 0;
    const u16 = v => [v & 255, (v >>> 8) & 255], u32 = v => [v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255];
    for (const f of files) {
      const nm = enc.encode(f.name), crc = crc32(f.data), n = f.data.length;
      const local = new Uint8Array([...u32(0x04034b50), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0x21), ...u32(crc), ...u32(n), ...u32(n), ...u16(nm.length), ...u16(0)]);
      chunks.push(local, nm, f.data);
      central.push(new Uint8Array([...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0x21), ...u32(crc), ...u32(n), ...u32(n), ...u16(nm.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(off)]), nm);
      off += local.length + nm.length + n;
    }
    const csize = central.reduce((a, c) => a + c.length, 0);
    const end = new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(files.length), ...u16(files.length), ...u32(csize), ...u32(off), ...u16(0)]);
    const all = new Uint8Array(off + csize + end.length); let p = 0;
    for (const c of chunks.concat(central, [end])) { all.set(c, p); p += c.length; }
    return all;
  }

  async function capture(entries, archiveName, gapMs = 2000, save = true) {
    const files = [], manifest = [];
    for (const e of entries) {
      let rec = { ...e, retrieved_utc: new Date().toISOString().replace(/\.\d+Z$/, 'Z') };
      try {
        const r = await fetch(e.url, { credentials: 'omit' });
        const body = new Uint8Array(await r.arrayBuffer());
        rec = { ...rec, status: r.status, bytes: body.length, sha256: await sha256(body), content_type: r.headers.get('content-type'), last_modified: r.headers.get('last-modified') };
        if (r.ok) { const name = `${e.family}/${(e.url_date || e.url.split('/').pop().replace(/\W/g, '_')).replace(/-/g, '')}${e.url.toLowerCase().endsWith('.pdf') ? '.pdf' : '.html'}`; rec.file = name; files.push({ name, data: body }); }
      } catch (err) { rec.status = 'error: ' + err.message; }
      manifest.push(rec);
      await sleep(gapMs);
    }
    const man = new TextEncoder().encode(JSON.stringify({ archive: archiveName, created_utc: new Date().toISOString(), page_origin: location.origin, user_agent: navigator.userAgent, documents: manifest }, null, 1));
    files.unshift({ name: 'manifest.json', data: man });
    const z = zip(files), digest = await sha256(z);
    if (save) { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([z], { type: 'application/zip' })); a.download = archiveName + '.zip'; a.click(); }
    return { archive: archiveName + '.zip', bytes: z.length, sha256: digest, manifest_sha256: await sha256(man), documents: manifest.length, ok: manifest.filter(m => m.status === 200).length };
  }

  root.AP3C = { SRC, plan, statementPlan, sizes, capture, zip, sha256 };
})(typeof window !== 'undefined' ? window : globalThis);
