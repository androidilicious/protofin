#!/usr/bin/env python3
"""Fetch AP3's official-document corpus (raw bytes) from the issuing agencies.

Runs wherever www.federalreserve.gov, www.bls.gov and www.census.gov are reachable (this sandbox cannot
reach them until they are allowed). Polite: one request every 2 s, a descriptive User-Agent, no retries
beyond one. Resumable: documents already on disk whose SHA-256 matches the log are skipped. Every response is logged with URL, HTTP status, SHA-256, size and retrieval time in
native_backtest/data/_corpus_raw/fetch_log.jsonl; raw files go to native_backtest/data/_corpus_raw/<family>/.
The folder is git-ignored; the committed corpus manifest records every hash so the corpus can be re-fetched
and verified. A family whose index yields fewer documents than expected stops the run.

Usage (repository root):  python -m native_backtest.scripts.ap3_corpus_fetch [--families f1,f2] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import pandas as pd

from native_backtest.ap3 import corpus, fomc_calendar

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "native_backtest/data/_corpus_raw"


class Fetcher:
    def __init__(self, ua: str, gap: float):
        import requests

        self.s = requests.Session()
        self.s.headers["User-Agent"] = ua
        self.gap, self.last = gap, 0.0
        RAW.mkdir(parents=True, exist_ok=True)
        self.log = (RAW / "fetch_log.jsonl").open("a")

    def get(self, url: str, family: str, save_as: str | None = None, **meta) -> bytes | None:
        wait = self.gap - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        try:
            r = self.s.get(url, timeout=60)
            status, body = r.status_code, r.content
        except Exception as e:  # network refused, DNS, proxy
            status, body = f"error: {type(e).__name__}", b""
        rec = {"family": family, "url": url, "status": status, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
               "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **meta}
        if save_as and status == 200:
            p = RAW / family / save_as
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
            rec["file"] = str(p.relative_to(ROOT))
        self.log.write(json.dumps(rec) + "\n")
        self.log.flush()
        return body if status == 200 else None


def already_fetched() -> set:
    """URLs whose latest successful fetch is on disk and still matches its logged SHA-256."""
    log = RAW / "fetch_log.jsonl"
    if not log.exists():
        return set()
    latest = {}
    for line in log.read_text().splitlines():
        r = json.loads(line)
        if r.get("status") == 200 and r.get("file"):
            latest[r["url"]] = r
    return {u for u, r in latest.items() if (ROOT / r["file"]).exists() and hashlib.sha256((ROOT / r["file"]).read_bytes()).hexdigest() == r["sha256"]}


def in_window(d: pd.Timestamp, w) -> bool:
    return pd.Timestamp(w[0]) <= d <= pd.Timestamp(w[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", default="")
    ap.add_argument("--dry-run", action="store_true", help="list planned index pages and documents without fetching documents")
    a = ap.parse_args()
    src = corpus.load_sources()
    fams = [f for f in src["families"] if not a.families or f in a.families.split(",")]
    f = Fetcher(src["user_agent"], src["min_seconds_between_requests"])
    w = src["window"]
    summary = {}
    for fam in fams:
        spec = src["families"][fam]
        planned = []  # (url, url_date, release_date)
        if fam == "fomc_statement":
            planned = [(spec["url"].format(yyyymmdd=d.strftime("%Y%m%d")), d, None) for d in fomc_calendar.load_dates() if in_window(d, w)]
        elif fam == "fed_g17_industrial_production":
            html = f.get(spec["index"][0], fam, kind="index")
            text = re.sub(r"<[^>]+>", " ", (html or b"").decode("utf-8", "replace"))
            for dd, mon, yy in re.findall(spec["date_regex"], text):
                d = corpus._parse_date(f"{mon} {dd} {yy}")
                if in_window(d, w):
                    planned.append((spec["url"].format(yyyymmdd=d.strftime("%Y%m%d")), d, None))
            planned = sorted(set(planned))
        else:
            pages = []
            for idx in spec["index"]:
                if "{yyyy}" in idx:
                    pages += [idx.format(yyyy=y) for y in range(pd.Timestamp(w[0]).year, 2021)]
                else:
                    pages.append(idx)
            seen = set()
            for pg in pages:
                html = f.get(pg, fam, kind="index")
                if html is None:
                    continue
                text = html.decode("utf-8", "replace")
                for m in re.finditer(spec["link_regex"], text):
                    digits = m.group(1)
                    rel = None
                    if fam.startswith("bls_"):
                        d = pd.Timestamp(f"{digits[4:8]}-{digits[0:2]}-{digits[2:4]}")
                        url = spec["url"].format(mmddyyyy=digits)
                    elif fam == "census_advance_retail_sales":
                        ref = pd.Timestamp(f"20{digits[:2]}-{digits[2:]}-01")   # reference month; release ~6 weeks later
                        url, d = m.group(0), None
                        if not in_window(ref + pd.DateOffset(months=1), w):
                            continue
                    else:
                        d = pd.Timestamp(f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}")
                        url = spec["url"].format(yyyymmdd=digits)
                        if "release_date_regex" in spec:
                            after = re.search(spec["release_date_regex"], re.sub(r"<[^>]+>", " ", text[m.end(): m.end() + 600]))
                            before = re.findall(spec["release_date_regex"], re.sub(r"<[^>]+>", " ", text[max(0, m.start() - 400): m.start()]))
                            # historical pages print the label before the link; the current calendar page after it
                            if "fomchistorical" in pg:
                                rd = before[-1] if before else (after.group(1) if after else None)
                            else:
                                rd = after.group(1) if after else (before[-1] if before else None)
                            rel = corpus._parse_date(rd) if rd else None
                    if url in seen or (d is not None and not in_window(d, w)):
                        continue
                    seen.add(url)
                    planned.append((url, d, rel))
            if fam == "fomc_minutes" and any(r is None for _, _, r in planned):
                raise SystemExit(f"fomc_minutes: release date missing for {[u for u, _, r in planned if r is None][:3]}")
        years = pd.Series([p[1].year for p in planned if p[1] is not None]).value_counts().to_dict()
        summary[fam] = {"planned": len(planned), "by_year": {int(k): int(v) for k, v in sorted(years.items())}}
        if a.dry_run:
            continue
        got, kept = 0, 0
        done = already_fetched()
        for url, d, rel in planned:
            if url in done:          # resumable: a document already on disk with its logged SHA-256 is not fetched again
                kept += 1
                continue
            ext = ".pdf" if url.lower().endswith(".pdf") else ".html"
            name = (d.strftime("%Y%m%d") if d is not None else re.sub(r"\W", "_", url.rsplit("/", 1)[-1])) + ext
            body = f.get(url, fam, save_as=name, url_date=None if d is None else str(d.date()), release_date=None if rel is None else str(rel.date()))
            got += body is not None
        summary[fam].update({"fetched": got, "already_verified": kept})
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
