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
                 "Development 2019–22", "Historical test", "Not run yet",
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
                    "Agent Committee only vs JEV only"],
    "methodology": ["Timeline", "Training", "Development", "Historical test", "Live", "2023 overlaps", "reported separately", "Awaiting decision", "Jan 2024 – Aug 2026", "Supporting metrics",
                    "Rules and settings", "Frozen", "Needs approval", "Differs by design", "Net CER (certainty-equivalent return)", "Validation status",
                    "How net CER is calculated", "not a compound annual return",
                    "Passive Portfolio Reference — 60% SPY / 40% IEF", "Research baseline", "Own benchmarks", "Same dates", "Monthly rebalancing", "Same trading cost", "Dividends included",
                    "Same return accounting", "not the research baseline and not a fourth approach"],
    "timeline": ["Timeline", "Feb 2015"],
    "method": ["Rules and settings"],
}
# Wording the usability review flagged as jargon or as overstating the results.
JARGON = re.compile(r"\b(common benchmark|attribution|Awaiting freeze approval|best|TypeSafe|temperature|P\(stocks|spending approval|one fair test|Faithfulness)\b|\bS 0\b|% TLT|% LQD", re.I)   # "60% SPY / 40% IEF" is the approved passive-reference label
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
                    if view in ("deterministic", "jev", "committee"):
                        ds = page.evaluate("""() => { const c = Chart.getChart('c-one'); return c.data.datasets.map((d, i) => ({l: d.label, shown: c.isDatasetVisible(i)})); }""")
                        cmp = {"deterministic": [], "jev": ["Deterministic baseline"], "committee": ["JEV"]}[view]
                        labels = [d["l"] for d in ds]
                        if labels[1:1 + len(cmp)] != cmp or not labels[-2].startswith("Own benchmark") or labels[-1] != "Passive 60/40 reference" or ds[-1]["shown"]:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: detail chart lines {ds}")
                        if page.locator("main .attr .arow").count() != 3:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: decomposition rows missing")
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
                    if shots and (scheme == "dark" or view in ("overview", "experiments")):
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
