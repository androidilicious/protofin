"""News and policy-text features for Protofin, as a point-in-time table.

Sources
  FOMC statements   federalreserve.gov archive (1994+), scored with FOMC-RoBERTa
                    (Shah, Paturi & Chava 2023, "Trillion Dollar Words"): hawkish / dovish / neutral
  Headlines         live: Google News RSS (no archive, display + live view only)
                    archive: GDELT DOC API (2015+), cached, polite backoff; throttled at times
                    scored with FinBERT (ProsusAI) sentiment, then LLM structured extraction
                    (BIS "Parsing the Pulse" style: growth/inflation direction, demand vs supply,
                    driver, with the supporting quote; "insufficient evidence" allowed)

Everything downloaded is cached under data/news/. Model weights download once (~1 GB total).

    python news_pipeline.py            # prints today's snapshot
    python news_pipeline.py --backfill # builds data/news/fomc_index.csv for all statements
"""
import argparse
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR = os.path.join(BASE_DIR, "data", "news")
FOMC_DIR = os.path.join(NEWS_DIR, "fomc")
FOMC_INDEX = os.path.join(NEWS_DIR, "fomc_index.csv")
GDELT_DIR = os.path.join(NEWS_DIR, "gdelt")
HEADERS = {"User-Agent": "Mozilla/5.0 protofin-research"}
FED = "https://www.federalreserve.gov"
MACRO_QUERY = '("federal reserve" OR inflation OR "treasury yields" OR recession OR "jobs report" OR tariffs OR "rate cut" OR "rate hike")'
MACRO_TERMS = re.compile(r"fed\b|federal reserve|fomc|inflation|cpi|treasur|yield|recession|gdp|jobs report|payroll|"
                         r"unemployment|tariff|rate (cut|hike)|powell|central bank|bond market|economy", re.I)

FOMC_MODEL = os.getenv("FOMC_MODEL", "tim9510019/FOMC-RoBERTa")  # ungated re-train of the gated gtfintechlab model; labels 0 dovish, 1 hawkish, 2 neutral
_models = {}


def _get(url, timeout=60, retries=3):
    last = None
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout).read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 * (attempt + 1))
    raise last


def _strip_html(html):
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# ------------------------------------------------------------------ FOMC statements
def fomc_meeting_dates(years):
    """Meeting dates (YYYYMMDD) from the Fed's calendar pages."""
    dates = set()
    pages = [f"{FED}/monetarypolicy/fomccalendars.htm"] + \
            [f"{FED}/monetarypolicy/fomchistorical{y}.htm" for y in years if y < 2021]
    for url in pages:
        try:
            html = _get(url).decode("utf-8", "ignore")
        except Exception:
            continue
        for d in re.findall(r"(?:monetary|fomcminutes|/monetary/|/monetary/\d{4}/)(\d{8})", html):
            if int(d[:4]) in years:
                dates.add(d)
    return sorted(dates)


def fomc_statement(date8):
    """Statement text for a meeting date, cached. Tries the three URL patterns the Fed has used."""
    os.makedirs(FOMC_DIR, exist_ok=True)
    path = os.path.join(FOMC_DIR, f"{date8}.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read() or None
    candidates = [f"{FED}/newsevents/pressreleases/monetary{date8}a.htm",
                  f"{FED}/newsevents/pressreleases/monetary{date8}b.htm",   # unscheduled meetings
                  f"{FED}/boarddocs/press/monetary/{date8[:4]}/{date8}/default.htm"]
    text = ""
    for url in candidates:
        try:
            html = _get(url, retries=1).decode("utf-8", "ignore")
        except Exception:
            continue
        body = _strip_html(html)
        m = re.search(r"(Information received|Recent indicators|The Federal Open Market Committee|The Committee)(.*?)(Voting for|In taking the discount rate|Implementation Note|Last Update)", body, re.S)
        if m:
            text = (m.group(1) + m.group(2)).strip()
            break
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text or None


def _load_model(name):
    if name in _models:
        return _models[name]
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    import torch
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSequenceClassification.from_pretrained(name)
    model.eval()
    _models[name] = (tok, model, torch)
    return _models[name]


def _classify(name, texts, batch=16):
    tok, model, torch = _load_model(name)
    labels = [model.config.id2label[i].lower() for i in range(model.config.num_labels)]
    out = []
    for i in range(0, len(texts), batch):
        enc = tok(texts[i:i + batch], padding=True, truncation=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            probs = torch.softmax(model(**enc).logits, dim=-1).tolist()
        out.extend(dict(zip(labels, p)) for p in probs)
    return out


def hawkishness(text):
    """FOMC-RoBERTa per sentence; returns mean(hawkish) - mean(dovish) in [-1, 1] and counts."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 25]
    if not sents:
        return None
    probs = _classify(FOMC_MODEL, sents)
    h = sum(p.get("label_1", p.get("hawkish", 0)) for p in probs) / len(probs)
    d = sum(p.get("label_0", p.get("dovish", 0)) for p in probs) / len(probs)
    return {"score": round(h - d, 3), "hawkish": round(h, 3), "dovish": round(d, 3), "sentences": len(sents)}


def build_fomc_index(years=range(2008, 2027)):
    """Hawkishness per statement -> data/news/fomc_index.csv (dated, point-in-time)."""
    rows = []
    for d in fomc_meeting_dates(set(years)):
        text = fomc_statement(d)
        if not text:
            continue
        hk = hawkishness(text)
        rows.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", **hk, "chars": len(text)})
        print(f"  {d} hawkish-dovish {hk['score']:+.3f} ({hk['sentences']} sentences)")
    df = pd.DataFrame(rows).sort_values("date")
    os.makedirs(NEWS_DIR, exist_ok=True)
    df.to_csv(FOMC_INDEX, index=False)
    return df


def latest_fomc(as_of=None):
    """Most recent statement on or before as_of from the cached index (builds one if missing)."""
    if not os.path.exists(FOMC_INDEX):
        build_fomc_index()
    df = pd.read_csv(FOMC_INDEX, parse_dates=["date"])
    if as_of is not None:
        df = df[df["date"] <= pd.Timestamp(as_of)]
    if df.empty:
        return None
    r = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    return {"date": str(r["date"].date()), "score": float(r["score"]), "hawkish": float(r["hawkish"]),
            "dovish": float(r["dovish"]),
            "change_vs_prev": None if prev is None else round(float(r["score"] - prev["score"]), 3)}


# ------------------------------------------------------------------ headlines
def google_news(query=MACRO_QUERY, limit=40):
    """Live headlines from Google News RSS (no archive; display and live view only)."""
    import feedparser
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(_get(url))
    items = []
    for e in feed.entries[:limit]:
        title = re.sub(r"\s+-\s+[^-]+$", "", e.title)     # strip trailing " - Publisher"
        pub = getattr(e, "published", "")
        try:
            ts = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        except Exception:
            ts = None
        items.append({"title": title, "source": getattr(e, "source", {}).get("title", ""), "published": ts.isoformat() if ts else pub})
    return items


def gdelt_headlines(start, end, query=MACRO_QUERY, maxrecords=75):
    """Dated headlines from the GDELT DOC API (2015+), cached per (start,end,query)."""
    os.makedirs(GDELT_DIR, exist_ok=True)
    key = hashlib.sha1(f"{start}{end}{query}{maxrecords}".encode()).hexdigest()[:16]
    path = os.path.join(GDELT_DIR, f"{key}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + urllib.parse.quote(query + " sourcelang:english")
           + f"&mode=artlist&maxrecords={maxrecords}&format=json&sort=datedesc"
           + f"&startdatetime={s:%Y%m%d}000000&enddatetime={e:%Y%m%d}235959")
    data = json.loads(_get(url, retries=4).decode("utf-8", "ignore") or "{}")
    items = [{"title": a["title"], "source": a.get("domain", ""), "published": a.get("seendate", "")}
             for a in data.get("articles", [])]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(items, fh)
    time.sleep(5)   # be polite; the endpoint throttles by IP
    return items


def macro_filter(items):
    return [i for i in items if MACRO_TERMS.search(i["title"])]


def headline_sentiment(items):
    """FinBERT on titles; returns per-item labels and an aggregate in [-1, 1]."""
    if not items:
        return [], None
    probs = _classify("ProsusAI/finbert", [i["title"] for i in items])
    scored = []
    for i, p in zip(items, probs):
        scored.append({**i, "positive": round(p.get("positive", 0), 3), "negative": round(p.get("negative", 0), 3),
                       "neutral": round(p.get("neutral", 0), 3),
                       "label": max(("positive", "negative", "neutral"), key=lambda k: p.get(k, 0))})
    agg = sum(s["positive"] - s["negative"] for s in scored) / len(scored)
    return scored, round(agg, 3)


EXTRACT_PROMPT = """You are an economist classifying news headlines. For the headlines below, decide what they say about the US macro outlook. Use ONLY the headlines; do not add outside knowledge.

Headlines:
{headlines}

Return JSON only, with this shape:
{{"growth": "up"|"down"|"mixed"|"insufficient", "inflation": "up"|"down"|"mixed"|"insufficient",
  "policy": "tighter"|"easier"|"mixed"|"insufficient", "nature": "demand"|"supply"|"policy"|"mixed"|"insufficient",
  "drivers": ["short phrase", ...], "evidence": ["exact headline quoted", ...], "summary": "one sentence"}}
Say "insufficient" whenever the headlines do not support a call."""


def extract_shocks(items, client, model="gpt-4o"):
    """LLM structured extraction with quotes kept. Returns dict or None."""
    if not items:
        return None
    text = "\n".join(f"- {i['title']}" for i in items[:40])
    r = client.chat.completions.create(model=model, temperature=0.0, seed=42, max_tokens=400,
                                       messages=[{"role": "user", "content": EXTRACT_PROMPT.format(headlines=text)}])
    raw = r.choices[0].message.content or ""
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


# ------------------------------------------------------------------ snapshot
def news_snapshot(client=None, as_of=None, live=True, headlines=True):
    """All text features for a date. live=True uses Google News for today; otherwise GDELT.
    headlines=False skips the headline fetch entirely (FOMC index only)."""
    snap = {"as_of": as_of or str(datetime.now(timezone.utc).date())}
    try:
        snap["fomc"] = latest_fomc(as_of)
    except Exception as exc:  # noqa: BLE001
        snap["fomc"] = None
        snap["fomc_error"] = str(exc)[:120]
    if not headlines:
        snap.update({"headlines": [], "headline_count": 0, "sentiment": None})
        return snap
    try:
        if live and as_of is None:
            items = macro_filter(google_news())
            snap["headline_source"] = "Google News RSS (live)"
        else:
            end = pd.Timestamp(as_of)
            items = macro_filter(gdelt_headlines(end - timedelta(days=3), end))
            snap["headline_source"] = "GDELT DOC API"
        scored, agg = headline_sentiment(items)
        snap["headlines"] = scored[:25]
        snap["headline_count"] = len(scored)
        snap["sentiment"] = agg
    except Exception as exc:  # noqa: BLE001
        snap["headlines"], snap["headline_count"], snap["sentiment"] = [], 0, None
        snap["headline_error"] = str(exc)[:120]
    if client is not None and snap.get("headlines"):
        try:
            snap["extraction"] = extract_shocks(snap["headlines"], client)
        except Exception as exc:  # noqa: BLE001
            snap["extraction"] = None
            snap["extraction_error"] = str(exc)[:120]
    return snap


def snapshot_text(snap):
    """Compact text for the committee prompt."""
    parts = []
    f = snap.get("fomc")
    if f:
        parts.append(f"Latest FOMC statement ({f['date']}) hawkish-minus-dovish score {f['score']:+.2f} on a -1..+1 scale"
                     + (f", change vs previous statement {f['change_vs_prev']:+.2f}" if f.get("change_vs_prev") is not None else "") + ".")
    if snap.get("headline_count"):
        parts.append(f"{snap['headline_count']} macro headlines in the last 3 days, FinBERT net sentiment {snap['sentiment']:+.2f}.")
    ex = snap.get("extraction")
    if ex:
        parts.append(f"Headline read: growth {ex.get('growth')}, inflation {ex.get('inflation')}, policy {ex.get('policy')}, "
                     f"nature {ex.get('nature')}. {ex.get('summary', '')}")
    return " ".join(parts) if parts else "No news features available."


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    args = ap.parse_args()
    if args.backfill:
        df = build_fomc_index()
        print(df.tail())
    else:
        s = news_snapshot()
        print(json.dumps({k: v for k, v in s.items() if k != "headlines"}, indent=2))
        for h in s.get("headlines", [])[:8]:
            print(f"  [{h['label']:8s}] {h['title'][:90]}")
        print("\nprompt text:", snapshot_text(s))
