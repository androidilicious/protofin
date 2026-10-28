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
    "overview": ["So far", "Growth of $1", "Versus own benchmark", "How they compare", "Primary comparisons", "How allocations changed",
                 "Deterministic Quantitative Model", "Agentic Workflow — JEV", "Agentic Causal RAG", "Awaiting validation · results unavailable",
                 "Development diagnostics", "Protected historical results", "Experiments"],
    "approaches": ["The three approaches", "At a glance", "Within-approach variant"],
    "experiments": ["Within the Agentic Workflow", "Committee only", "JEV only", "Committee + JEV", "Proposed · not run", "Implemented",
                    "Committee only vs JEV only", "Secondary experiments", "Signal ablations", "Market-regime experiments", "Standard RAG vs Causal RAG"],
    "deterministic": ["How it works", "Development diagnostics", "Monthly return forecasts", "Portfolio weights", "Reproduction check"],
    "jev": ["How it works", "JEV's answer each month", "Can't be re-run", "represents the Agentic Workflow"],
    "committee": ["Within-approach variant of the Agentic Workflow", "12-month views", "Reproduction check", "Sample reasoning"],
    "causal-rag": ["Awaiting validation · results unavailable", "Research inventory", "not a result", "Demo only", "Safeguards"],
    "timeline": ["Walk-forward validation", "Training", "Feb 2015", "Protected historical test", "Development diagnostics", "Two stages of checking"],
    "method": ["Net CER (Certainty-Equivalent Return)", "not a compound annual return", "Primary comparison", "Same for every approach",
               "Why this is not a controlled comparison"],
}
# Wording the usability review flagged as jargon or as overstating the results.
JARGON = re.compile(r"\b(best|TypeSafe|temperature|P\(stocks|spending approval|one fair test|Faithfulness)\b|\bS 0\b|% SPY|% TLT|% IEF|% LQD", re.I)
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
                    jargon = JARGON.findall(page.text_content("body"))
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
                    if view in ("overview", "approaches"):
                        n_cards = page.locator("main .cards .card").count()
                        if n_cards != 3:
                            problems.append(f"[{scheme}/{vp_name}] #{view}: {n_cards} approach cards, expected exactly 3")
                    sw = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                    if sw > 1:
                        problems.append(f"[{scheme}/{vp_name}] #{view}: page scrolls sideways by {sw}px")
                    n_canvas = page.locator("canvas").count()
                    report[f"{scheme}/{vp_name}/{view}"] = {"canvases": n_canvas, "chars": len(text)}
                    if shots and (scheme == "dark" or view in ("overview", "experiments")):
                        page.screenshot(path=str(shots / f"{scheme}-{vp_name}-{view}.png"), full_page=True)
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
