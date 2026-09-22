"""Protofin MVP backend: live data -> LLM views -> Black-Litterman -> constrained allocation.

Run:  python server.py   then open http://127.0.0.1:5000
Each pipeline run is appended to runs/pipeline_log.jsonl with every intermediate stage,
and the last decision is persisted in state/last_allocation.json so that repeated runs on
unchanged evidence return the same decision instead of drifting.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from openai import OpenAI

from allocation import MAX_MOVE, MAX_SPY, MIN_SPY, NO_TRADE_BAND, allocate
import macro_indexes
import news_pipeline

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "state", "last_allocation.json")
LOG_PATH = os.path.join(BASE_DIR, "runs", "pipeline_log.jsonl")

# Allocation policy constants live in allocation.py (shared with research/backtest.py)
HORIZON_MONTHS = 12
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
# Headlines have no archive, so by default they are DISPLAY ONLY and never reach the view,
# the fingerprint or the allocation. The FOMC statement index (archived since 2008) always does.
#   off     -> no headline fetch at all
#   display -> fetched and shown on the dashboard, excluded from the decision (default)
#   decide  -> included in the committee prompt and the fingerprint (demo mode; not backtestable)
HEADLINES_MODE = os.getenv("HEADLINES_MODE", "display")
# Prototype mode (default on): no evidence cache, no state file, no hold band / move cap.
# The optimizer target is applied directly. Set PROTOTYPE_MODE=0 to restore the stability controls.
PROTOTYPE_MODE = os.getenv("PROTOTYPE_MODE", "1") == "1"

app = Flask(__name__, static_folder=".", static_url_path="")


@app.route("/")
def index():
    return send_file("mvp_dashboard.html")


# --------------------------------------------------------------------------- helpers
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


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


def parse_llm(text):
    """Parse the fixed-format LLM reply. Returns (fields, problems)."""
    fields = {"economist": None, "risk": None, "cio": None, "grounding": None,
              "spy_q": None, "tlt_q": None, "confidence": None}
    labels = {"Economist:": "economist", "Risk_Manager:": "risk", "CIO_Decision:": "cio",
              "Grounding_Summary:": "grounding"}
    for raw in text.splitlines():
        line = raw.strip()
        for label, key in labels.items():
            if line.startswith(label):
                fields[key] = line[len(label):].strip()
        for label, key in (("SPY_Expected_Return_Percent:", "spy_q"),
                           ("TLT_Expected_Return_Percent:", "tlt_q")):
            if line.startswith(label):
                match = NUMBER.search(line[len(label):])
                if match:
                    fields[key] = float(match.group())
        if line.startswith("CIO_Confidence:"):
            value = line.split(":", 1)[1].strip().strip(".").lower()
            if value in ("high", "medium", "low"):
                fields["confidence"] = value.capitalize()

    problems = []
    for key in ("spy_q", "tlt_q"):
        value = fields[key]
        if value is None:
            problems.append(f"{key} missing")
        elif not -50.0 <= value <= 50.0:
            problems.append(f"{key}={value} outside plausible annual range")
            fields[key] = None
    if fields["confidence"] is None:
        problems.append("confidence missing or not High/Medium/Low")
    return fields, problems


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


DIAGRAM_BUILDER = os.path.join(BASE_DIR, "docs", "build_flow_diagram.py")


def rebuild_diagram_async():
    """Regenerate the archify diagram with this run's results, off the request thread."""
    import subprocess
    import sys
    import threading

    def _run():
        try:
            subprocess.run([sys.executable, DIAGRAM_BUILDER], capture_output=True, timeout=180, cwd=BASE_DIR)
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("diagram rebuild failed: %s", exc)
    threading.Thread(target=_run, daemon=True).start()


# --------------------------------------------------------------------------- pipeline
@app.route("/api/run_pipeline")
def run_pipeline():
    force = request.args.get("force") == "1"
    try:
        # 1. Data ingestion
        tnx_hist = yf.Ticker("^TNX").history(period="3mo")["Close"].dropna()
        spy_tk = yf.Ticker("SPY")
        spy_hist = spy_tk.history(period="1y")["Close"].dropna()
        tlt_hist = yf.Ticker("TLT").history(period="1y")["Close"].dropna()
        if len(tnx_hist) < 5 or len(spy_hist) < 30 or len(tlt_hist) < 30:
            raise RuntimeError("Insufficient price history returned by Yahoo Finance")

        current_yield = float(tnx_hist.iloc[-1])
        yield_3mo_avg = float(tnx_hist.mean())
        # Risk-free rate: 13-week T-bill (^IRX), falling back to the 10Y yield if unavailable
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
        returns = df.pct_change().dropna()
        sigma = returns.cov().values * 252

        # 2. Rate shock: 10Y yield vs its 3-month mean, in basis points
        rate_shock_bps = (current_yield - yield_3mo_avg) * 100.0
        direction = "Hawkish (Tightening)" if rate_shock_bps > 0 else "Dovish (Easing)"
        svar_shock_text = (f"{direction} rate shock: 10Y yield is {rate_shock_bps:+.0f} bps "
                           f"from its 3-month average ({yield_3mo_avg:.2f}%).")

        # 2b. Uncertainty indexes: EPU (policy) and GPR (geopolitical), 30-day means ranked
        # against 10 years of history. Elevated uncertainty lowers trust in views, never raises it.
        try:
            idx = macro_indexes.load_all()
            epu, gpr = macro_indexes.snapshot(idx["EPU"]), macro_indexes.snapshot(idx["GPR"])
        except Exception as exc:
            epu, gpr = None, None
            app.logger.warning("uncertainty indexes unavailable: %s", exc)
        regime = macro_indexes.uncertainty_regime(epu, gpr)
        def _fmt(name, snap):
            if not snap:
                return f"{name} unavailable"
            return (f"{name} {snap['latest']:.0f} (30-day mean {snap['mean_30d']:.0f}, "
                    f"{snap['percentile_10y']:.0f}th percentile of the last 10 years)")
        uncertainty_text = (f"{_fmt('Economic Policy Uncertainty index', epu)}; "
                            f"{_fmt('Geopolitical Risk index', gpr)}. Regime: {regime}.")

        # 2c. News and policy text: latest FOMC statement hawkishness (FOMC-RoBERTa), live macro
        # headlines (Google News RSS) scored by FinBERT, then LLM structured extraction with quotes.
        # The single Yahoo headline is kept only for comparison on the dashboard.
        news = news_pipeline.news_snapshot(client=None, live=True, headlines=HEADLINES_MODE != "off")
        decision_news = news if HEADLINES_MODE == "decide" else {"fomc": news.get("fomc")}
        news_text = news_pipeline.snapshot_text(decision_news)

        # Evidence fingerprint: identical inputs -> identical decision (no drift on refresh)
        fingerprint = hashlib.sha256(json.dumps({
            "as_of": as_of, "yield": round(current_yield, 3), "avg": round(yield_3mo_avg, 3),
            "spy_1m": round(spy_return_1m, 3), "rf": round(rf_pct, 3), "headline": headline,
            "epu": epu and epu["mean_30d"], "gpr": gpr and gpr["mean_30d"],
            "fomc": news.get("fomc") and news["fomc"]["score"],
            "sentiment": news.get("sentiment") if HEADLINES_MODE == "decide" else None,
            "headlines": [h["title"] for h in news.get("headlines", [])][:10] if HEADLINES_MODE == "decide" else [],
            "model": LLM_MODEL,
        }, sort_keys=True).encode()).hexdigest()[:16]

        # Prototype mode: every click is a fresh run. No cache, no stored holding, no trade policy.
        previous = None if PROTOTYPE_MODE else load_state()
        if previous and previous.get("fingerprint") == fingerprint and not force:
            cached = dict(previous["response"])
            cached["cached"] = True
            cached["trade_status"] = "unchanged evidence: returning stored decision"
            return jsonify(cached)
        previous_spy = previous["response"]["spy_weight"] / 100.0 if previous else None

        # 3. LLM reasoning
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        data_payload = (
            f"As of {as_of}: 10-Year Treasury yield {current_yield:.2f}% "
            f"(3-month average {yield_3mo_avg:.2f}%). Cash (13-week T-bill) yield {rf_pct:.2f}%. "
            f"SPY 1-month return {spy_return_1m:+.2f}%. "
            f"SPY annualized volatility {np.sqrt(sigma[0, 0]) * 100:.1f}%, "
            f"TLT {np.sqrt(sigma[1, 1]) * 100:.1f}%. Latest headline: '{headline}'. "
            f"Uncertainty: {uncertainty_text}"
        )
        client = OpenAI(api_key=api_key)
        if news.get("headlines"):
            try:
                news["extraction"] = news_pipeline.extract_shocks(news["headlines"], client, model=LLM_MODEL)
            except Exception as exc:  # noqa: BLE001
                news["extraction"], news["extraction_error"] = None, str(exc)[:120]
        if HEADLINES_MODE == "decide":
            news_text = news_pipeline.snapshot_text(news)
            top = chr(10).join(f"- {h['title']}" for h in news.get("headlines", [])[:8])
            data_payload = data_payload + f" News features: {news_text}" + (chr(10) + "Recent macro headlines:" + chr(10) + top if top else "")
        else:
            data_payload = data_payload + f" Policy text: {news_text}"
        prompt = build_prompt(data_payload, svar_shock_text)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            seed=42,
            max_tokens=400,
        )
        llm_output = response.choices[0].message.content or ""
        fields, problems = parse_llm(llm_output)
        llm_parse_ok = not problems

        # 4-5. Black-Litterman posterior (views as EXCESS returns over cash), constrained
        # optimum and trade policy: shared code path in allocation.py
        confidence_reported = fields["confidence"] or "Low"
        confidence = macro_indexes.downgrade_confidence(confidence_reported, regime)
        if llm_parse_ok:
            views = [fields["spy_q"], fields["tlt_q"]]
            view_note = f"views applied as excess return over cash ({rf_pct:.2f}%)"
        else:
            views = None   # invalid views are rejected, not replaced with defaults
            view_note = "LLM views rejected (" + "; ".join(problems) + "); using equilibrium prior only"
        decision = allocate(sigma, views, confidence, rf_pct, previous_spy)
        pi, er_bl, w_unconstrained = decision["pi"], decision["er"], decision["unconstrained"]
        target_spy, final_spy, trade_status = decision["target_spy"], decision["final_spy"], decision["status"]
        if PROTOTYPE_MODE:
            final_spy, trade_status = target_spy, "prototype mode: optimizer target applied directly"

        result = {
            "prototype_mode": PROTOTYPE_MODE,
            "as_of": as_of,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fingerprint": fingerprint,
            "cached": False,
            "yield": f"{current_yield:.2f}%",
            "spy_return": f"{spy_return_1m:.2f}%",
            "headline": headline,
            "headline_available": headline_available,
            "news": {"fomc": news.get("fomc"), "sentiment": news.get("sentiment"),
                     "headline_count": news.get("headline_count"), "headline_source": news.get("headline_source"),
                     "headlines": news.get("headlines", [])[:8], "extraction": news.get("extraction"),
                     "text": news_text, "headlines_mode": HEADLINES_MODE,
                     "headlines_in_decision": HEADLINES_MODE == "decide"},
            "svar_shock": svar_shock_text,
            "svar_value": round(rate_shock_bps, 2),
            "economist": fields["economist"] or "(no economist output parsed)",
            "risk": fields["risk"] or "(no risk-manager output parsed)",
            "cio": fields["cio"] or "(no CIO output parsed)",
            "grounding": fields["grounding"] or "(no grounding summary parsed)",
            "spy_q": fields["spy_q"],
            "tlt_q": fields["tlt_q"],
            "confidence": confidence,
            "confidence_reported": confidence_reported,
            "uncertainty_regime": regime,
            "epu": epu,
            "gpr": gpr,
            "uncertainty_text": uncertainty_text,
            "llm_parse_ok": llm_parse_ok,
            "llm_problems": problems,
            "view_note": view_note,
            "horizon_months": HORIZON_MONTHS,
            "risk_free": round(rf_pct, 2),
            "spy_q_excess": None if not llm_parse_ok else round(fields["spy_q"] - rf_pct, 2),
            "tlt_q_excess": None if not llm_parse_ok else round(fields["tlt_q"] - rf_pct, 2),
            "prior_spy": round(float(pi[0]) * 100, 2),
            "prior_tlt": round(float(pi[1]) * 100, 2),
            "posterior_spy": round(float(er_bl[0]) * 100, 2),
            "posterior_tlt": round(float(er_bl[1]) * 100, 2),
            "unconstrained_spy": round(float(w_unconstrained[0]) * 100, 1),
            "unconstrained_tlt": round(float(w_unconstrained[1]) * 100, 1),
            "target_spy": round(target_spy * 100, 1),
            "target_tlt": round((1 - target_spy) * 100, 1),
            "previous_spy": None if previous_spy is None else round(previous_spy * 100, 1),
            "spy_weight": round(final_spy * 100, 1),
            "tlt_weight": round((1 - final_spy) * 100, 1),
            "trade_status": trade_status,
            "policy": {"tilt_band_spy": [MIN_SPY * 100, MAX_SPY * 100],
                       "no_trade_band_pp": NO_TRADE_BAND * 100, "max_move_pp": MAX_MOVE * 100},
        }

        append_log({**result, "sigma": sigma.tolist(), "llm_raw": llm_output, "prompt": prompt})
        save_state({"fingerprint": fingerprint, "response": result})
        rebuild_diagram_async()
        return jsonify(result)

    except Exception as exc:  # surfaced to the dashboard as an alert
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=False, port=5000)
