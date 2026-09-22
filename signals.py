"""Everything the pipeline needs before the LLM call, as one JSON-serialisable dict.

Used by server.py (live) and scripts/build_signals.py (GitHub Action -> site/data/signals.json).
The committee prompt is built here too, so the static site and the server send the same text.
"""
import hashlib
import json
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

import committee
import macro_indexes
import news_pipeline

HORIZON_MONTHS = 12


def latest_headline_from(news):
    """yfinance has changed its news schema more than once; handle both shapes."""
    if not isinstance(news, list):
        return None
    for item in news:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not title and isinstance(item.get("content"), dict):
            title = item["content"].get("title")
        if title:
            return re.sub(r"\s+", " ", str(title).replace("�", "")).strip()
    return None


def build_prompt(data_payload, svar_shock_text):
    return (
        "You are an investment committee producing inputs for a Black-Litterman allocation "
        "between SPY (US equities) and TLT (long Treasuries).\n"
        "Evaluate this point-in-time data only; do not assume facts not given:\n"
        f"{data_payload}\n"
        f"Rate-shock signal: {svar_shock_text}\n\n"
        f"Expected returns must be TOTAL returns over the next {HORIZON_MONTHS} months, in percent "
        "(e.g. 7.5 or -2.0). Judge them against the cash yield given above: a return below cash is a "
        "bearish view on that asset.\n"
        "Confidence describes how much the evidence above justifies deviating from those references, "
        "not how strongly the argument is worded.\n\n"
        "Format EXACTLY like this (no markdown):\n"
        "Economist: [2 concise sentences arguing a specific view]\n"
        "Risk_Manager: [2 concise sentences pushing back on the Economist]\n"
        "CIO_Decision: [2 sentence final synthesis]\n"
        "Grounding_Summary: [1 sentence naming the specific data points that drove this decision]\n"
        "SPY_Expected_Return_Percent: [number]\n"
        "TLT_Expected_Return_Percent: [number]\n"
        "CIO_Confidence: [High, Medium, or Low]\n"
    )


def collect(headlines=True, headlines_in_decision=False, model_name="gpt-4o", log=None):
    """Fetch market data, signals and policy text; build the prompt. No LLM call."""
    warn = log or (lambda *a: None)

    # 1. Market data
    tnx_hist = yf.Ticker("^TNX").history(period="3mo")["Close"].dropna()
    spy_tk = yf.Ticker("SPY")
    spy_hist = spy_tk.history(period="1y")["Close"].dropna()
    tlt_hist = yf.Ticker("TLT").history(period="1y")["Close"].dropna()
    if len(tnx_hist) < 5 or len(spy_hist) < 30 or len(tlt_hist) < 30:
        raise RuntimeError("Insufficient price history returned by Yahoo Finance")
    current_yield = float(tnx_hist.iloc[-1])
    yield_3mo_avg = float(tnx_hist.mean())
    try:
        rf_pct = float(yf.Ticker("^IRX").history(period="5d")["Close"].dropna().iloc[-1])
    except Exception:
        rf_pct = current_yield
    spy_return_1m = float((spy_hist.iloc[-1] / spy_hist.iloc[-21] - 1) * 100)
    as_of = str(spy_hist.index[-1].date())
    headline = latest_headline_from(spy_tk.news)
    headline_available = headline is not None
    if not headline_available:
        headline = "No headline available from the news feed."
    df = pd.DataFrame({"SPY": spy_hist, "TLT": tlt_hist}).dropna()
    sigma = df.pct_change().dropna().cov().values * 252

    # 2. Rate shock (bps)
    rate_shock_bps = (current_yield - yield_3mo_avg) * 100.0
    direction = "Hawkish (Tightening)" if rate_shock_bps > 0 else "Dovish (Easing)"
    svar_shock_text = (f"{direction} rate shock: 10Y yield is {rate_shock_bps:+.0f} bps "
                       f"from its 3-month average ({yield_3mo_avg:.2f}%).")

    # 2b. Uncertainty regime
    try:
        idx = macro_indexes.load_all()
        epu, gpr = macro_indexes.snapshot(idx["EPU"]), macro_indexes.snapshot(idx["GPR"])
    except Exception as exc:  # noqa: BLE001
        epu, gpr = None, None
        warn("uncertainty indexes unavailable: %s", exc)
    regime = macro_indexes.uncertainty_regime(epu, gpr)

    def _fmt(name, snap):
        if not snap:
            return f"{name} unavailable"
        return (f"{name} {snap['latest']:.0f} (30-day mean {snap['mean_30d']:.0f}, "
                f"{snap['percentile_10y']:.0f}th percentile of the last 10 years)")
    uncertainty_text = (f"{_fmt('Economic Policy Uncertainty index', epu)}; "
                        f"{_fmt('Geopolitical Risk index', gpr)}. Regime: {regime}.")

    # 2c. Policy text (FOMC stance in the decision) and headlines (display unless asked)
    news = news_pipeline.news_snapshot(client=None, live=True, headlines=headlines)
    decision_news = news if headlines_in_decision else {"fomc": news.get("fomc")}
    news_text = news_pipeline.snapshot_text(decision_news)

    # 3. Prompt
    data_payload = (
        f"As of {as_of}: 10-Year Treasury yield {current_yield:.2f}% "
        f"(3-month average {yield_3mo_avg:.2f}%). Cash (13-week T-bill) yield {rf_pct:.2f}%. "
        f"SPY 1-month return {spy_return_1m:+.2f}%. "
        f"SPY annualized volatility {np.sqrt(sigma[0, 0]) * 100:.1f}%, "
        f"TLT {np.sqrt(sigma[1, 1]) * 100:.1f}%. "
        f"Uncertainty: {uncertainty_text}"
    )   # the single Yahoo headline is display-only and deliberately NOT in the prompt
    if headlines_in_decision:
        top = "\n".join(f"- {h['title']}" for h in news.get("headlines", [])[:8])
        data_payload += f" News features: {news_text}" + (f"\nRecent macro headlines:\n{top}" if top else "")
    else:
        data_payload += f" Policy text: {news_text}"
    prompt = build_prompt(data_payload, svar_shock_text)          # legacy single-call prompt
    prompts = committee.build_prompts(data_payload, svar_shock_text)  # economist ∥ risk → CIO

    fingerprint = hashlib.sha256(json.dumps({
        "as_of": as_of, "yield": round(current_yield, 3), "avg": round(yield_3mo_avg, 3),
        "spy_1m": round(spy_return_1m, 3), "rf": round(rf_pct, 3),
        "epu": epu and epu["mean_30d"], "gpr": gpr and gpr["mean_30d"],
        "fomc": news.get("fomc") and news["fomc"]["score"],
        "sentiment": news.get("sentiment") if headlines_in_decision else None,
        "headlines": [h["title"] for h in news.get("headlines", [])][:10] if headlines_in_decision else [],
        "model": model_name,
    }, sort_keys=True).encode()).hexdigest()[:16]

    return {
        "as_of": as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fingerprint": fingerprint,
        "yield": f"{current_yield:.2f}%",
        "yield_value": round(current_yield, 3),
        "yield_3mo_avg": round(yield_3mo_avg, 3),
        "risk_free": round(rf_pct, 2),
        "spy_return": f"{spy_return_1m:.2f}%",
        "spy_return_value": round(spy_return_1m, 3),
        "headline": headline,
        "headline_available": headline_available,
        "sigma": [[float(sigma[0, 0]), float(sigma[0, 1])], [float(sigma[1, 0]), float(sigma[1, 1])]],
        "svar_shock": svar_shock_text,
        "svar_value": round(rate_shock_bps, 2),
        "epu": epu,
        "gpr": gpr,
        "uncertainty_regime": regime,
        "uncertainty_text": uncertainty_text,
        "news": {"fomc": news.get("fomc"), "sentiment": news.get("sentiment"),
                 "headline_count": news.get("headline_count"), "headline_source": news.get("headline_source"),
                 "headlines": news.get("headlines", [])[:8], "extraction": None,
                 "text": news_text, "headlines_in_decision": headlines_in_decision},
        "horizon_months": HORIZON_MONTHS,
        "prompt": prompt,
        "prompts": prompts,
    }
