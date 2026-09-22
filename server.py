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
import signals
import committee

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "state", "last_allocation.json")
LOG_PATH = os.path.join(BASE_DIR, "runs", "pipeline_log.jsonl")

# Allocation policy constants live in allocation.py (shared with research/backtest.py)
HORIZON_MONTHS = signals.HORIZON_MONTHS
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
    text = re.sub(r"\*\*|__|`", "", text or "")   # tolerate markdown from smaller models
    for raw in text.splitlines():
        line = raw.strip()
        for label, key in labels.items():
            if line.lower().startswith(label.lower()):
                fields[key] = line[len(label):].strip()
    for asset, key in (("SPY", "spy_q"), ("TLT", "tlt_q")):
        m = (re.search(asset + r"[_ ]?Expected[_ ]?Return[_ ]?Percent\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)", text, re.I)
             or re.search(r"^[^\n]*" + asset + r"[^\n]*?(?:return|expect)[^\n]*?([-+]?\d+(?:\.\d+)?)\s*%", text, re.I | re.M)   # number followed by %
             or re.search(r"^[^\n]*" + asset + r"[^\n]*?(?:return|expect)[^\n]*?[:=]\s*([-+]?\d+(?:\.\d+)?)", text, re.I | re.M)  # number after a colon
             or re.search(r"^[^\n]*" + asset + r"\s*[:=]\s*([-+]?\d+(?:\.\d+)?)\s*%", text, re.I | re.M))
        if m:
            fields[key] = float(m.group(1))
    m = (re.search(r"CIO[_ ]?Confidence\s*[:=]?\s*(High|Medium|Low)", text, re.I)
         or re.search(r"confidence[^\n]{0,40}?\b(High|Medium|Low)\b", text, re.I))
    if m:
        fields["confidence"] = m.group(1).capitalize()

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
        # 1-3. Market data, signals, policy text and the prompt: shared with the static site
        sig = signals.collect(headlines=HEADLINES_MODE != "off", headlines_in_decision=HEADLINES_MODE == "decide",
                              model_name=LLM_MODEL, log=app.logger.warning)
        as_of, headline, headline_available = sig["as_of"], sig["headline"], sig["headline_available"]
        current_yield, spy_return_1m, rf_pct = sig["yield_value"], sig["spy_return_value"], sig["risk_free"]
        sigma = np.array(sig["sigma"])
        rate_shock_bps, svar_shock_text = sig["svar_value"], sig["svar_shock"]
        epu, gpr, regime, uncertainty_text = sig["epu"], sig["gpr"], sig["uncertainty_regime"], sig["uncertainty_text"]
        news, news_text, fingerprint, prompt = dict(sig["news"]), sig["news"]["text"], sig["fingerprint"], sig["prompt"]

        # Prototype mode: every click is a fresh run. No cache, no stored holding, no trade policy.
        previous = None if PROTOTYPE_MODE else load_state()
        if previous and previous.get("fingerprint") == fingerprint and not force:
            cached = dict(previous["response"])
            cached["cached"] = True
            cached["trade_status"] = "unchanged evidence: returning stored decision"
            return jsonify(cached)
        previous_spy = previous["response"]["spy_weight"] / 100.0 if previous else None

        # LLM reasoning (headline extraction is display-only)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        client = OpenAI(api_key=api_key)
        if news.get("headlines"):
            try:
                news["extraction"] = news_pipeline.extract_shocks(news["headlines"], client, model=LLM_MODEL)
            except Exception as exc:  # noqa: BLE001
                news["extraction"], news["extraction_error"] = None, str(exc)[:120]
        def _call(prompt_text):
            r = client.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": prompt_text}],
                                               temperature=0.0, seed=42, max_tokens=400)
            return r.choices[0].message.content or ""
        com = committee.run_committee(sig["prompts"], _call, parallel=True)
        llm_output = com["cio_raw"]
        fields = {"economist": com["economist"]["text"], "risk": com["risk"]["text"],
                  "cio": com["cio"]["cio"], "grounding": com["cio"]["grounding"],
                  "spy_q": com["cio"]["spy_q"], "tlt_q": com["cio"]["tlt_q"], "confidence": com["cio"]["confidence"]}
        problems = com["problems"]
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
            "news": {**news, "headlines_mode": HEADLINES_MODE},
            "svar_shock": svar_shock_text,
            "svar_value": rate_shock_bps,
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
            "prompt": prompt,
            "prompts": sig["prompts"],
            "llm_raw": llm_output,
            "economist_raw": com["economist_raw"], "risk_raw": com["risk_raw"], "cio_raw": com["cio_raw"],
            "cio_prompt": com["cio_prompt"],
            "economist_q": [com["economist"]["spy"], com["economist"]["tlt"]],
            "risk_q": [com["risk"]["spy"], com["risk"]["tlt"]],
            "committee_timing": com["timings"],
            "model_used": LLM_MODEL,
            "model_source": "OpenAI API via local server, temperature 0, seed 42",
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
