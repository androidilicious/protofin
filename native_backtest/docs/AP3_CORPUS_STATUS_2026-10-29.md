# AP3 evidence corpus: status — 2026-10-29

The documents were downloaded directly from the issuing agencies by the resumable fetcher (`scripts/ap3_corpus_fetch.py`). The download ran in this cloud environment, with no personal computer involved.

## Result

| Family | Documents | Build errors | Publication date checks | Status |
|---|---|---|---|---|
| FOMC statements | 99 | 0 | printed release time; statement date | ✅ validated |
| FOMC minutes | 94 | 0 | 94/94 match the Fed calendar release date | ✅ validated |
| Fed G.17 industrial production | 140 | 0 | 140/140 match the index date and the ALFRED INDPRO vintages | ✅ validated |
| Census advance retail sales | 141 | 0 | 141/141 printed release dates match the ALFRED RSAFS vintages | ✅ validated |
| BLS Employment Situation | 0 | — | — | ❌ blocked |
| BLS CPI | 0 | — | — | ❌ blocked |
| BLS PPI | 0 | — | — | ❌ blocked |

- **474 documents** are validated, giving 9,967 chunks plus canaries. The checks found:
  - 0 build errors;
  - 0 date mismatches and 0 ALFRED mismatches;
  - PDF metadata never used;
  - the point-in-time audit over every AP3 decision time from 2015-02 to 2026-08 passes (no chunk is eligible before it was public; no canary is ever eligible).
- **Coverage exceptions, explained from the data:**
  - the 2025 federal shutdown (G.17 and Census, 11 releases);
  - the December 2025 FOMC minutes, published 2025-12-30 within the same year, giving 9 releases that year;
  - partial first and last years.
- **Failed check: the BLS families are missing (about 420 documents).** BLS's CDN returned HTTP 403 for all three index pages. One logged attempt per index page used the configured User-Agent.
  - BLS's site policy says it "reserves the right to block robots that do not contain information that can be used to contact the owner".
  - The configured User-Agent gives no direct contact.
  - Nothing was retried with altered headers.
- **Parser fix (2026-10-29).** 26 Census PDFs initially failed to parse: the 2014-12..2016-11 layout prints the date before the time, and two PDFs have extraction spacing artefacts.
  - The rule is unchanged: the release time printed in the document.
  - The parser now normalises whitespace and reads the older layout.
  - All 141 resulting dates match ALFRED.

Records:
- `data/ap3_corpus/fetch_manifest_v1.json`: every document's source URL, SHA-256, size, retrieval time and index/release dates; the unreachable index pages; failed documents.
- `out/ap3/corpus_manifest_v1.json`: per document, `available_at` and its source, plus the text hash.
- `out/ap3/corpus_checks_v1.json`: all checks.

## Reconciliation: expected vs downloaded

The expected counts are checked against an independent record of release dates: the ALFRED vintage dates of each release's headline series, or the Fed's own calendar pages for the FOMC documents. The machine-readable version is the `reconciliation` block of `out/ap3/corpus_checks_v1.json`.

| Family | On official index | Downloaded and dated | ALFRED release dates in window | Missing |
|---|---|---|---|---|
| FOMC statements | 99 | 99 | (calendar) | 0 |
| FOMC minutes | 94 | 94 | (calendar) | 0 |
| G.17 industrial production | 140 | 140 | 150 (INDPRO) | 0; the 10 extra ALFRED dates are annual-revision vintages |
| Census advance retail sales | 141 | 141 | 148 (RSAFS) | 0; the 7 extra dates are annual-revision vintages (late April) |
| BLS Employment Situation | unreachable | 0 | 141 (PAYEMS) | ≤ 141 |
| BLS CPI | unreachable | 0 | 148 (CPIAUCSL) | ≤ 148 |
| BLS PPI | unreachable | 0 | 146 (PPIFIS) | ≤ 146 |
| **Total** | | **474** | | **≤ 435** (all BLS); expected corpus ≤ 909 documents |

Every downloaded document's publication date is an ALFRED release date (0 exceptions). The BLS rows use ALFRED as an upper bound, because it also records revision-only vintages; there is about one release per month. The exact missing BLS dates are listed in the checks file. An earlier estimate of 855 documents is superseded by this count.

## Storage (outside the repository history)

- The raw documents are packed into four deterministic ZIP archives (about 94 MB), listed with their SHA-256 in `data/ap3_corpus/archive_manifest_v1.json`. The round trip was verified: 474/474 documents identical.
- **Not yet published.** The plan was a release asset in the private repository, but this session is not permitted to create GitHub releases (HTTP 403). The archives were not put in any git branch, because the raw corpus stays out of the repository. They will not outlast this environment until someone publishes them.
- **Rebuilding needs no archive.** The fetcher re-downloads the same documents from the agencies, about 15 minutes for Fed and Census. A `git diff` of `data/ap3_corpus/fetch_manifest_v1.json` then shows any document whose SHA-256 differs from the validated set.
- **Publishing the release** (anyone with release rights, after confirming the repository is still private):

  ```bash
  python -m native_backtest.scripts.ap3_corpus_archive pack --out corpus_zips     # after a fetch or restore; identical bytes
  gh release create ap3-corpus-v1.0-partial --repo androidilicious/protofin --prerelease \
    --title "AP3 evidence corpus v1.0 (partial: Federal Reserve + Census)" --notes-file native_backtest/docs/AP3_CORPUS_STATUS_2026-10-29.md \
    corpus_zips/*.zip native_backtest/data/ap3_corpus/*.json
  ```

- **Restoring** from the release: `gh release download ap3-corpus-v1.0-partial --repo androidilicious/protofin --dir <folder>`, then `python -m native_backtest.scripts.ap3_corpus_archive restore --zips <folder>`. Every document is re-hashed against the committed fetch manifest.
- All sources are US government works in the public domain.

## Options for the BLS documents (decision needed; none applied)

1. **Recommended: identify the fetcher as BLS asks.** Set the User-Agent to a real project contact, a team email of your choice, which BLS's policy asks robots to provide. Then rerun `ap3_corpus_fetch --families bls_employment_situation,bls_cpi,bls_ppi` here. This needs your approval and the contact address. It may still be refused, because BLS can block cloud addresses.
2. **Download once in a browser.** Someone runs the existing browser-capture script (`scripts/browser/ap3_corpus_capture.js`) on the BLS pages and attaches the three archives. `ap3_corpus_import --zips` verifies the hashes and dates the same way.
3. **Use a mirror instead of the issuing agency (needs explicit approval).** The Federal Reserve Bank of St. Louis's FRASER archive holds the same BLS releases. This changes the pre-specified source, so it would be recorded as a deviation.

Until BLS is resolved, the With Historical Documents version cannot run as specified. The Reduced Evidence version does not depend on the corpus.
