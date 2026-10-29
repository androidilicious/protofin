#!/usr/bin/env python3
"""Headless browser check of the dashboard: every view loads without console errors, required
content is present, internal labels (AP1, AP2-A, ...) never appear, tooltips open on hover and tap,
the page never scrolls sideways at phone width, and screenshots are saved for review.

Usage: python mvp/tests/check_dashboard.py [--url http://127.0.0.1:8765/] [--shots DIR]
Requires Playwright with Chromium.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWS = {
    "overview": ["Does AI improve on our Deterministic baseline?", "Deterministic Quantitative Model", "Agentic Workflow — JEV", "Agentic Causal RAG",
                 "Research baseline", "Awaiting validation", "No clear answer yet", "not statistically clear", "Research comparisons", "Findings so far",
                 "What we know", "Not yet known", "Key metrics", "Net CER is the primary metric", "Growth of $1", "Versus baseline",
                 "vs Deterministic baseline", "Net CER vs baseline", "Cumulative return", "Passive investment comparison", "Passive 60/40 reference",
                 "Development 2019–22", "Historical test", "No results yet",
                 "Within-approach experiments", "Methodology and validation"],
    "approaches": ["How it works", "Economic surprises", "Ridge regression", "Black–Litterman", "Results", "Research baseline", "Versus the passive 60/40 reference", "Gap split", "accounting split", "Benchmark mix",
                   "Versus its own benchmark", "Secondary check",
                   "Monthly return forecasts", "Holdings over time", "Reproduction check", "Historical test 2023–26: sealed"],
    "deterministic": ["How it works", "Results", "Monthly return forecasts", "Reproduction check", "Limitations"],
    "jev": ["How it works", "JEV decision model", "JEV's answer each month", "represents the Agentic Workflow", "Versus the Deterministic baseline", "Reproduction check"],
    "committee": ["Within-approach variant of the Agentic Workflow", "Chief investment officer", "12-month views", "Versus JEV (within-approach)", "Sample reasoning"],
    "causal-rag": ["Awaiting validation", "Results unavailable", "Knowledge graph", "Hypothesis Agent", "CauseTrace", "Testing Agent",
                   "Validation progress", "Two versions", "Reduced evidence", "With historical documents", "Primary version: not yet chosen",
                   "Evidence the Testing Agent can use", "Free real-model run (Qwen3 4B", "Qwen3 4B, free", "Inputs: research the agents can draw on", "No results yet", "Demo: one month, step by step", "Safeguards"],
    "experiments": ["Within-approach experiments", "None enters the primary comparison", "Tested", "Awaiting validation", "Planned", "Blocked", "Paused",
                    "Base model: 8 economic-data surprises", "Add one financial signal at a time", "Market regimes", "JEV only", "Agent Committee only",
                    "Committee + JEV", "Its primary version is chosen before the test opens", "Causal RAG — Reduced Evidence",
                    "Causal RAG — With Historical Documents", "Do historical documents help?", "Standard RAG vs Causal RAG", "Ablations and placebo checks", "Model and calibration variants",
                    "Agent Committee only vs JEV only", "Do the signals actually add value?", "See the Signal Value-Added tab",
                    "None of the five improves the forecasts", "The combined signal set does not beat the baseline",
                    "Everything earns less after 2019", "The combination lands between its two parts, and beats neither",
                    "46 development months", "Signals that pass the robustness rule", "0 of 5", "Signal coverage", "100%",
                    "These splits are diagnostics and never select anything."],
    "signal-value": ["Signal Value-Added", "Observation", "Experiments", "Results", "Explanation", "Takeaway",
                     "Two very different forecasting approaches, remarkably similar performance curves", "0.971", "0.983",
                     "no calculation or charting error", "Keep the investment framework fixed. Change only the forecasting signal.",
                     "Experiment 1", "Experiment 2", "Deterministic signal value", "JEV signal value", "Same assets: SPY, IEF, LQD", "Same assets: SPY, TLT",
                     "Same starting weights: 45% / 35% / 20%", "Same starting weights: 60% / 40%", "Only the Ridge-generated portfolio tilts are switched off",
                     "Only the JEV-generated portfolio tilts are switched off", "not protected historical test results",
                     "3.67%", "3.77%", "−0.11 pts", "4.67%", "4.37%", "+0.31 pts", "p = 0.17", "p = 0.59",
                     "95% interval −0.31 pts to +0.03 pts", "95% interval −0.48 pts to +1.38 pts", "Interval includes zero: not statistically significant",
                     "+1.01 pts", "+0.59 pts", "+0.42 pts", "+1.39 pts", "−0.79 pts", "+0.11 pts", "Accounting attribution, not proof of causality",
                     "does not establish AI-generated alpha", "Rounded, the parts add up to +1.02", "+0.31 pts → −0.18 pts", "Feb 2020 decision",
                     "54.7%", "SPY fell 19.9%", "not proof of foresight",
                     "neither system's signals demonstrated statistically significant incremental value in this development sample",
                     "This does not prove the signals have zero value.", "46-month development sample", "The protected historical test has not been opened.",
                     "Agentic Causal RAG has not yet produced validated real-model backtest results."],
    "methodology": ["Timeline", "Training", "Development", "Historical test", "Live", "2023 overlaps", "reported separately", "Awaiting decision", "Jan 2024 – Aug 2026", "Supporting metrics",
                    "Rules and settings", "Frozen", "Needs approval", "Differs by design", "Net CER (certainty-equivalent return)", "Validation status",
                    "How net CER is calculated", "not a compound annual return",
                    "Passive Portfolio Reference — 60% SPY / 40% IEF", "Research baseline", "Own benchmarks", "Same dates", "Monthly rebalancing", "Same trading cost", "Dividends included",
                    "Same return accounting", "not the research baseline and not a fourth approach"],
    "timeline": ["Timeline", "Feb 2015"],
    "method": ["Rules and settings"],
}
# Wording the usability review flagged as jargon or as overstating the results.
JARGON = re.compile(r"\b(common benchmark|(?<!accounting )attribution|Awaiting freeze approval|best|TypeSafe|temperature|P\(stocks|spending approval|one fair test|Faithfulness)\b|\bS 0\b|% TLT|% LQD", re.I)   # "60% SPY / 40% IEF" is the approved passive-reference label
FORBIDDEN = re.compile(r"\b(AP1|AP2A|AP2B|AP2-A|AP2-B|AP3|engineering_mock|saved_native_replay|\.jsonl|\.py\b)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765/")
    ap.add_argument("--shots", default=None)
    a = ap.parse_args()
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    problems, report = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("dark", "light"):
            for vp_name, vp in (("desktop", {"width": 1280, "height": 900}), ("phone", {"width": 390, "height": 844})):
                ctx = browser.new_context(viewport=vp, color_scheme=scheme, has_touch=vp_name == "phone")
                page = ctx.new_page()
                errors = []
                failed = []
                page.on("requestfailed", lambda r: failed.append(r.url))
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
                page.on("pageerror", lambda e: errors.append(str(e)))
                for view, must in VIEWS.items():
                    page.goto(a.url + "#" + view)
                    page.wait_for_selector("main .wrap section, main .wrap .err", timeout=15000)
                    page.wait_for_timeout(400)
                    text = page.text_content("main")
                    missing = [m for m in must if m not in text]
                    if missing:
                        problems.append(f"[{scheme}/{vp_name}] #{view}: missing {missing}")
                    bad = FORBIDDEN.findall(page.text_content("body"))
                    if bad:
                        problems.append(f"[{scheme}/{vp_name}] #{view}: internal labels shown {sorted(set(bad))}")
                    jargon = [m.group(0) for m in JARGON.finditer(page.text_content("body"))]
                    if jargon:
                        problems.append(f"[{scheme}/{vp_name}] #{view}: flagged wording {sorted(set(map(str, jargon)))}")
                    # nothing may be cut off: the nav fits, and no table or timeline needs sideways scrolling on a phone
                    clipped = page.evaluate("""() => [...document.querySelectorAll('nav, main .scroll')]
                        .filter(e => e.offsetParent !== null && e.scrollWidth > e.clientWidth + 1).map(e => e.tagName.toLowerCase() + '.' + e.className)""")
                    if clipped and (vp_name == "phone" or "nav" in " ".join(clipped)):
                        problems.append(f"[{scheme}/{vp_name}] #{view}: content cut off in {clipped}")
                    # info icons must sit on the same line as the text they explain
                    lonely = page.evaluate("""() => [...document.querySelectorAll('main li .tip')].filter(t => {
                        const r = t.getBoundingClientRect(), p = t.parentElement.getBoundingClientRect();
                        const li = t.closest('li'), pad = parseFloat(getComputedStyle(li).paddingLeft) || 0, q = li.getBoundingClientRect();
                        return r.width > 0 && Math.abs(r.left - (q.left + pad)) < 4 && t.closest('li').textContent.trim().length > 0; }).length""")
                    if lonely:
                        problems.append(f"[{scheme}/{vp_name}] #{view}: {lonely} info icon(s) wrapped onto their own line")
                    if view == "overview":
                        n_cards = page.locator("main .acard").count()
                        if n_cards != 3:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: {n_cards} approach cards, expected exactly 3")
                        # main chart: the approaches with the Deterministic baseline; the passive 60/40 reference is an optional dashed line, off by default
                        for mode in ("abs", "gap"):
                            g = page.locator(f"[data-g={mode}]")
                            g.tap() if vp_name == "phone" else g.click()   # taps on phones: a mouse click would leave a stale pointer
                            ds = page.evaluate("""() => { const c = Chart.getChart('c-growth'); return c.data.datasets.map((d, i) => ({l: d.label, dash: (d.borderDash || []).length > 0, shown: c.isDatasetVisible(i)})); }""")
                            want = [("Deterministic (baseline)", False, True), ("Agentic Workflow (JEV)", False, True), ("Passive 60/40 reference", True, False)] if mode == "abs" \
                                else [("Agentic Workflow (JEV)", False, True), ("Deterministic baseline", True, True)]
                            if [(d["l"], d["dash"], d["shown"]) for d in ds] != want:
                                problems.append(f"[{scheme}/{vp_name}] #{view} ({mode}): chart lines {ds}")
                        g = page.locator("[data-g=abs]")
                        g.tap() if vp_name == "phone" else g.click()
                        # optional similarity diagnostic: closed by default; opening it draws the gap bars and the stock-weight lines
                        if page.locator("#d-alike").get_attribute("open") is not None:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: similarity diagnostic open by default")
                        sm = page.locator("#d-alike summary")
                        sm.tap() if vp_name == "phone" else sm.click()
                        page.wait_for_timeout(200)
                        ad = page.evaluate("""() => { const a = Chart.getChart('c-spread'), b = Chart.getChart('c-spy');
                            return a && b ? {bars: a.data.datasets[0].data.length, lines: b.data.datasets.map(d => d.label)} : null; }""")
                        if not ad or ad["bars"] != 46 or ad["lines"] != ["Deterministic (baseline)", "JEV"] or "0.97" not in page.text_content("#d-alike"):
                            problems.append(f"[{scheme}/{vp_name}] #{view}: similarity diagnostic {ad}")
                        if shots and scheme == "dark":
                            page.locator("#d-alike").screenshot(path=str(shots / f"{scheme}-{vp_name}-similarity.png"))
                    if view in ("deterministic", "jev", "committee"):
                        ds = page.evaluate("""() => { const c = Chart.getChart('c-one'); return c.data.datasets.map((d, i) => ({l: d.label, shown: c.isDatasetVisible(i)})); }""")
                        cmp = {"deterministic": [], "jev": ["Deterministic baseline"], "committee": ["JEV"]}[view]
                        labels = [d["l"] for d in ds]
                        if labels[1:1 + len(cmp)] != cmp or not labels[-2].startswith("Own benchmark") or labels[-1] != "Passive 60/40 reference" or ds[-1]["shown"]:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: detail chart lines {ds}")
                        if page.locator("main .attr .arow").count() != 3:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: decomposition rows missing")
                    if view == "experiments":
                        # every experiment shows its real status; results appear only where one actually ran
                        rows = page.evaluate("""() => [...document.querySelectorAll('.branch')].map(b => ({
                            name: b.querySelector('.nm').textContent.trim(), status: [...b.classList].find(c => c !== 'branch'),
                            chip: b.querySelector('.chip') ? b.querySelector('.chip').textContent.trim() : null,
                            results: b.querySelectorAll('.exres').length}))""")
                        want = {"Add one financial signal at a time": ("tested", 1), "All five financial signals together": ("tested", 1),
                                "Market regimes": ("tested", 1), "Agent Committee only": ("tested", 0), "Committee + JEV": ("tested", 1),
                                "Causal RAG — Reduced Evidence": ("awaiting_validation", 0), "Causal RAG — With Historical Documents": ("blocked", 0),
                                "Policy-path proxy variant": ("awaiting_validation", 0), "Do historical documents help?": ("planned", 0),
                                "Standard RAG vs Causal RAG": ("planned", 0), "Ablations and placebo checks": ("planned", 0),
                                "Model and calibration variants": ("planned", 0)}
                        got = {r["name"]: (r["status"], r["results"]) for r in rows}
                        if got != want:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: experiment statuses {[(k, got.get(k), v) for k, v in want.items() if got.get(k) != v]}")
                        if any(r["status"] in ("paused", "planned") and r["results"] for r in rows):
                            problems.append(f"[{scheme}/{vp_name}] #{view}: results shown for an experiment that did not run")
                        for b_ in page.locator(".branch > button").all():
                            b_.tap() if vp_name == "phone" else b_.click()
                        page.wait_for_timeout(250)
                        if page.locator(".exres").count() != 4 or page.locator("#app .exres-caution").count() != 1:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: result blocks {page.locator('.exres').count()}")
                        if shots and scheme == "dark":
                            page.screenshot(path=str(shots / f"{scheme}-{vp_name}-experiments-open.png"), full_page=True)

                    if view == "signal-value":
                        # its own top-level tab: the right strategies, periods and series in every chart
                        if page.locator("header nav a[aria-current=page]").text_content() != "Signal Value-Added" or page.locator("header nav a").count() != 5:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: not a selected top-level tab")
                        ch = page.evaluate("""() => Object.fromEntries(['c-sva-growth', 'c-sva-det', 'c-sva-jev', 'c-sva-month'].map(id => { const c = Chart.getChart(id);
                            return [id, c ? {labels: [c.data.labels[0], c.data.labels.at(-1), c.data.labels.length],
                                             sets: c.data.datasets.map(d => [d.label.split(' (')[0], (d.borderDash || []).length > 0, d.data.length])} : null]; }))""")
                        period = ["2019-03", "2022-12", 46]
                        want = {"c-sva-growth": [["Deterministic", False, 46], ["Agentic Workflow", False, 46]],
                                "c-sva-det": [["With signals", False, 46], ["Without signals", True, 46]], "c-sva-jev": [["With signals", False, 46], ["Without signals", True, 46]],
                                "c-sva-month": [["JEV signal contribution", False, 46]]}
                        for cid, w in want.items():
                            got = ch.get(cid)
                            if not got or got["labels"] != period or [[l[0].split(" (")[0], l[1], l[2]] for l in got["sets"]] != w:
                                problems.append(f"[{scheme}/{vp_name}] #{view}: chart {cid} {got}")
                        hi = page.evaluate("""() => { const c = Chart.getChart('c-sva-month'); const bg = c.data.datasets[0].backgroundColor;
                            const odd = bg.map((x, i) => x !== bg[0] ? i : -1).filter(i => i >= 0); return odd.map(i => c.data.labels[i]); }""")
                        if hi != ["2020-02"]:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: highlighted month {hi}")
                        # both 95% intervals include zero, and nothing in the tab uses the green 'success' colour
                        cis = page.evaluate("""() => [...document.querySelectorAll('#sva-results .cibar')].map(b => { const r = b.querySelector('.range').getBoundingClientRect(), z = b.querySelector('.zero').getBoundingClientRect();
                            return r.left <= z.left + 1 && z.right <= r.right + 1; })""")
                        green = page.evaluate("""() => { const pos = getComputedStyle(document.documentElement).getPropertyValue('--pos').trim(); const tmp = document.createElement('i'); tmp.style.color = pos; document.body.append(tmp);
                            const rgb = getComputedStyle(tmp).color; tmp.remove(); return [...document.querySelectorAll('main *')].filter(e => { const s = getComputedStyle(e); return s.color === rgb || s.backgroundColor === rgb; }).length; }""")
                        if cis != [True, True] or green:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: intervals-include-zero {cis}, green elements {green}")
                        tips = page.evaluate("""() => [...document.querySelectorAll('main .tip span[role=tooltip]')].map(t => t.textContent.split(':')[0])""")
                        need = ["Net CER = Certainty-Equivalent Return", "No-signal portfolio", "Correlation", "Likely range (95%)", "p-value"]
                        if [n for n in need if n not in tips]:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: missing tooltips {[n for n in need if n not in tips]}")
                        if page.locator("#sva-results .sva-exp").count() != 2 or page.locator("#sva-tests .sva-exp").count() != 2 or page.locator("#sva-explain .arow").count() != 5:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: experiment or split cards missing")
                    if view in ("approaches", "deterministic", "jev", "causal-rag"):
                        n_tabs = page.locator("main .atabs a").count()
                        if n_tabs != 3:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: {n_tabs} approach tabs, expected exactly 3")
                    # no view may declare a winner: the old 'stronger value' markers are gone
                    if page.locator("main .lead, main .leadmark").count():
                        problems.append(f"[{scheme}/{vp_name}] #{view}: winner markers shown")
                    stray = page.evaluate("""() => [...document.querySelectorAll('.tip > span')].filter(s => !s.parentElement.classList.contains('show') && getComputedStyle(s).display !== 'none').length""")
                    if stray:
                        problems.append(f"[{scheme}/{vp_name}] #{view}: {stray} tooltip(s) visible without being opened")
                    sw = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                    if sw > 1:
                        problems.append(f"[{scheme}/{vp_name}] #{view}: page scrolls sideways by {sw}px")
                    n_canvas = page.locator("canvas").count()
                    report[f"{scheme}/{vp_name}/{view}"] = {"canvases": n_canvas, "chars": len(text)}
                    if shots and (scheme == "dark" or view in ("overview", "experiments", "signal-value")):
                        page.screenshot(path=str(shots / f"{scheme}-{vp_name}-{view}.png"), full_page=True)
                # flow diagram: selecting a step shows its short explanation
                page.goto(a.url + "#causal-rag")
                page.wait_for_selector(".fnode")
                node = page.locator(".fnode").nth(4)
                node.tap() if vp_name == "phone" else node.click()
                page.wait_for_timeout(150)
                if "Testing Agent." not in (page.text_content(".fdetail") or ""):
                    problems.append(f"[{scheme}/{vp_name}] flow step did not show its explanation")
                # experiment branches expand on click or tap
                page.goto(a.url + "#experiments")
                page.wait_for_selector(".branch > button")
                br = page.locator(".branch > button").first
                br.tap() if vp_name == "phone" else br.click()
                if br.get_attribute("aria-expanded") != "true":
                    problems.append(f"[{scheme}/{vp_name}] experiment branch did not expand")
                # tooltip opens on hover (desktop) or tap (phone)
                page.goto(a.url + "#overview")
                page.wait_for_selector(".tip > button")
                btn = page.locator(".tip > button").first
                if vp_name == "phone":
                    btn.tap()
                else:
                    btn.hover()
                page.wait_for_timeout(250)
                vis = page.evaluate("getComputedStyle(document.querySelector('.tip > span')).display")
                if vis != "block":
                    problems.append(f"[{scheme}/{vp_name}] tooltip did not open ({vis})")
                nonfont = [u for u in failed if "fonts.googleapis.com" not in u and "fonts.gstatic.com" not in u]
                if nonfont:
                    problems.append(f"[{scheme}/{vp_name}] failed requests: {nonfont[:3]}")
                if errors:
                    problems.append(f"[{scheme}/{vp_name}] console errors: {errors[:3]}")
                ctx.close()
        browser.close()
    print(json.dumps({"views_checked": len(report), "problems": problems}, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
