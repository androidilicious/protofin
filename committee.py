"""Three-persona investment committee: two independent views in parallel, then a CIO synthesis.

    economist  (macro economist at an asset manager)   \\  run concurrently, neither sees the other
    risk       (head of risk at a bank's investment arm) /
    cio        receives both views verbatim, decides the numbers

Shared by server.py (live), scripts/build_signals.py (saved runs) and, in spirit, site/js/pipeline.js.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

HORIZON_MONTHS = 12


def build_prompts(data_payload, svar_shock_text):
    """Returns {'economist', 'risk', 'cio'}; the CIO prompt has {ECONOMIST_VIEW} and {RISK_VIEW} slots."""
    data = (f"Point-in-time data (use only this; do not assume facts not given):\n{data_payload}\n"
            f"Rate-shock signal: {svar_shock_text}\n")
    rules = (f"Expected returns are TOTAL returns over the next {HORIZON_MONTHS} months, in percent "
             "(e.g. 7.5 or -2.0), judged against the cash yield above: below cash is a bearish view.\n")
    economist = (
        "You are the chief macro economist at a large asset manager, advising an allocation between SPY "
        "(US equities) and TLT (long Treasuries). Give your own independent view; no one else's opinion is available to you.\n"
        + data + rules +
        "Format EXACTLY like this (no markdown):\n"
        "Economist_View: [2 concise sentences arguing a specific macro view]\n"
        "Economist_SPY_Return_Percent: [number]\n"
        "Economist_TLT_Return_Percent: [number]\n")
    risk = (
        "You are the head of risk at a bank's investment arm, reviewing an allocation between SPY (US equities) "
        "and TLT (long Treasuries). Focus on downside, tail risk, and what could go wrong. Give your own independent view; "
        "no one else's opinion is available to you.\n"
        + data + rules +
        "Format EXACTLY like this (no markdown):\n"
        "Risk_View: [2 concise sentences on the key risks and what they imply]\n"
        "Risk_SPY_Return_Percent: [number]\n"
        "Risk_TLT_Return_Percent: [number]\n")
    cio = (
        "You are the chief investment officer. Two colleagues have given independent views on the same data. "
        "Weigh them, resolve disagreements, and decide the inputs for a Black-Litterman allocation between SPY and TLT.\n"
        + data + rules +
        "Confidence describes how much the evidence justifies deviating from a neutral 60/40 stance, not how strongly anyone argued.\n\n"
        "Economist (independent): {ECONOMIST_VIEW}\n"
        "Risk manager (independent): {RISK_VIEW}\n\n"
        "Format EXACTLY like this (no markdown):\n"
        "CIO_Decision: [2 sentence synthesis naming where you sided with whom and why]\n"
        "Grounding_Summary: [1 sentence naming the specific data points that drove this decision]\n"
        "SPY_Expected_Return_Percent: [number]\n"
        "TLT_Expected_Return_Percent: [number]\n"
        "CIO_Confidence: [High, Medium, or Low]\n")
    return {"economist": economist, "risk": risk, "cio": cio}


# ------------------------------------------------------------------ parsing (tolerant of small models)
def _clean(text):
    return re.sub(r"\*\*|__|`", "", text or "")


def _number_for(text, label_stem, asset):
    """First matching number for e.g. Economist_SPY_Return_Percent / 'SPY ... return ... 6%'."""
    num = r"([-+]?\d+(?:\.\d+)?)"
    for pat, flags in ((label_stem + asset + r"[_ ]?(?:Expected[_ ]?)?Return[_ ]?Percent\s*[:=]?\s*" + num, re.I),
                       (r"^[^\n]*" + asset + r"[^\n]*?(?:return|expect)[^\n]*?" + num + r"\s*%", re.I | re.M),
                       (r"^[^\n]*" + asset + r"[^\n]*?(?:return|expect)[^\n]*?[:=]\s*" + num, re.I | re.M),
                       (r"^[^\n]*" + asset + r"\s*[:=]\s*" + num + r"\s*%", re.I | re.M)):
        m = re.search(pat, text, flags)
        if m:
            return float(m.group(1))
    return None


def parse_view(raw, role):
    """role in ('economist', 'risk'). Returns {'text', 'spy', 'tlt'}; text falls back to the whole reply."""
    text = _clean(raw)
    label = "Economist_View" if role == "economist" else "Risk_View"
    m = re.search(label.replace("_", "[_ ]?") + r"\s*:\s*(.*)", text, re.I)
    view = m.group(1).strip() if m else " ".join(l for l in text.splitlines() if l and not re.search(r"Return[_ ]?Percent", l, re.I)).strip()
    stem = "Economist[_ ]?" if role == "economist" else "Risk[_ ]?"
    return {"text": view or "(no view text parsed)", "spy": _number_for(text, stem, "SPY"), "tlt": _number_for(text, stem, "TLT")}


def parse_cio(raw):
    """Returns (fields, problems). Numbers must be present and plausible; nothing is substituted."""
    text = _clean(raw)
    fields = {"cio": None, "grounding": None, "spy_q": None, "tlt_q": None, "confidence": None}
    for label, key in (("CIO[_ ]?Decision", "cio"), ("Grounding[_ ]?Summary", "grounding")):
        m = re.search(label + r"\s*:\s*(.*)", text, re.I)
        if m:
            fields[key] = m.group(1).strip()
    fields["spy_q"] = _number_for(text, r"(?:CIO[_ ]?)?", "SPY")
    fields["tlt_q"] = _number_for(text, r"(?:CIO[_ ]?)?", "TLT")
    m = (re.search(r"CIO[_ ]?Confidence\s*[:=]?\s*(High|Medium|Low)", text, re.I)
         or re.search(r"confidence[^\n]{0,40}?\b(High|Medium|Low)\b", text, re.I))
    if m:
        fields["confidence"] = m.group(1).capitalize()
    problems = []
    for key in ("spy_q", "tlt_q"):
        v = fields[key]
        if v is None:
            problems.append(f"{key} missing")
        elif not -50.0 <= v <= 50.0:
            problems.append(f"{key}={v} outside plausible annual range")
            fields[key] = None
    if fields["confidence"] is None:
        problems.append("confidence missing or not High/Medium/Low")
    return fields, problems


# ------------------------------------------------------------------ orchestration
def run_committee(prompts, call, parallel=True):
    """call(prompt) -> reply text. Economist and risk run concurrently, then the CIO. Returns everything."""
    t0 = time.time()
    timings = {}

    def timed(role):
        s = time.time()
        out = call(prompts[role])
        timings[role + "_ms"] = int((time.time() - s) * 1000)
        return out

    if parallel:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_e, f_r = ex.submit(timed, "economist"), ex.submit(timed, "risk")
            econ_raw, risk_raw = f_e.result(), f_r.result()
    else:
        econ_raw, risk_raw = timed("economist"), timed("risk")
    stage1_ms = int((time.time() - t0) * 1000)
    econ, risk = parse_view(econ_raw, "economist"), parse_view(risk_raw, "risk")
    cio_prompt = prompts["cio"].replace("{ECONOMIST_VIEW}", econ_raw.strip()).replace("{RISK_VIEW}", risk_raw.strip())
    s = time.time()
    cio_raw = call(cio_prompt)
    timings["cio_ms"] = int((time.time() - s) * 1000)
    fields, problems = parse_cio(cio_raw)
    return {
        "economist_raw": econ_raw, "risk_raw": risk_raw, "cio_raw": cio_raw, "cio_prompt": cio_prompt,
        "economist": econ, "risk": risk, "cio": fields, "problems": problems,
        "timings": {**timings, "stage1_wall_ms": stage1_ms, "total_ms": int((time.time() - t0) * 1000),
                    "parallel": parallel},
    }
