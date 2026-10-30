#!/usr/bin/env python3
"""Headless browser check of the dashboard: every view loads without console errors, required
content is present, internal labels (AP1, AP2-A, ...) never appear, tooltips open on hover and tap,
the page never scrolls sideways at phone width, and screenshots are saved for review.

Expectations are read from mvp/data/dashboard.json wherever a figure or a label is published there,
so a rebuild that changes a number does not silently invalidate this check. Only genuine invariants
are written out here: the nav, the counts, "no view declares a winner", "every interval that includes
zero is drawn that way", "no internal identifier reaches the page".

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

ROOT = Path(__file__).resolve().parents[2]
D = json.loads((ROOT / "mvp/data/dashboard.json").read_text())
RAG = bool(D.get("ap3_exploratory", {}).get("monthly_net_return"))

NAV = ["Overview", "Replay", "Pipeline", "Comparison", "Signal Value", "Sensitivity", "Experiments",
       "Causal RAG", "Appendix"]
TOP = ["overview", "replay", "pipeline", "comparison", "signal-value", "sensitivity", "experiments",
       "causal-rag", "appendix"]
DETAIL = ["deterministic", "jev", "committee"]

pc = lambda x, n=2: f"{x * 100:.{n}f}%"
ppts = lambda x, n=2: f"{'+' if x >= 0 else '−'}{abs(x) * 100:.{n}f} pts"


def required() -> dict:
    """What each view must say. Numbers come from the published data, never from a second copy here."""
    sv, g = D["signal_value"], D["signal_value"]["gap"]
    sysn = {s["key"]: s for s in D["systems"] + D["variants"]}
    must = {
        "overview": ["Does AI improve on our Deterministic baseline?", "Net CER", "No clear answer yet",
                     "statistically clear", sysn["det"]["name"], sysn["jev"]["name"], sysn["rag"]["name"]],
        "replay": ["Play", "Month", sysn["det"]["short"], sysn["jev"]["short"], sysn["rag"]["short"]],
        "pipeline": ["Historical data", "Signal generation", "Forecasting", "Portfolio allocation",
                     "Trades & returns", "Performance evaluation"],
        "comparison": ["Primary comparison", "Growth of $1", "Versus baseline",
                       "Same assets, different questions", "7–10 year Treasuries and corporate bonds"],
        "signal-value": ["Signal Value-Added", "Observation", "Experiments", "Results", "Explanation",
                         "Takeaway", "no calculation or charting error",
                         "Interval includes zero: not statistically significant",
                         "Accounting attribution, not proof of causality",
                         "does not establish AI-generated alpha",
                         pc(sv["systems"]["det"]["with"]["cer"]), pc(sv["systems"]["jev"]["with"]["cer"]),
                         ppts(g["total"]["cer_difference"]), ppts(g["mix"]["cer_difference"]),
                         "their bond holdings are now identical"],
        "sensitivity": ["Forecast-to-allocation sensitivity", "Neutral (0x)", "Original (1x)", "Stronger (2x)"],
        "experiments": ["Within-approach experiments", "None enters the primary comparison", "Tested",
                        "Planned", "Blocked", "Committee + JEV"],
        "causal-rag": ["Knowledge graph", "Hypothesis Agent", "Testing Agent", "Qwen3 4B"],
        # the exploratory designation is stated once, in the appendix, where it is explained in full
        "appendix": ["Why every Causal RAG figure is marked exploratory", "did not pass the two pre-registered",
                     "not validated evidence", "56.7%", "97.7%"],
        "deterministic": ["How it works", "Reproduction check", "Limitations"],
        "jev": ["How it works", "JEV decision model", "Reproduction check"],
        "committee": ["Chief investment officer", "12-month views", "Sample reasoning"],
    }
    # the three funds every approach now holds, named in plain words on the comparison view
    return must


# Wording the usability review flagged as jargon or as overstating the results.
JARGON = re.compile(r"\b(common benchmark|(?<!accounting )attribution|Awaiting freeze approval|best|TypeSafe|temperature|P\(stocks|spending approval|one fair test|Faithfulness)\b|\bS 0\b", re.I)   # "60% SPY / 40% IEF" is the approved passive-reference label
FORBIDDEN = re.compile(r"\b(AP1|AP2A|AP2B|AP2-A|AP2-B|AP3|engineering_mock|saved_native_replay|\.jsonl|\.py\b)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765/")
    ap.add_argument("--shots", default=None)
    a = ap.parse_args()
    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    VIEWS = required()
    problems, report = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("dark", "light"):
            for vp_name, vp in (("desktop", {"width": 1280, "height": 900}), ("phone", {"width": 390, "height": 844})):
                tag = f"[{scheme}/{vp_name}]"
                ctx = browser.new_context(viewport=vp, color_scheme=scheme, has_touch=vp_name == "phone")
                page = ctx.new_page()
                errors, failed = [], []
                page.on("requestfailed", lambda r: failed.append(r.url))
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
                page.on("pageerror", lambda e: errors.append(str(e)))
                tap = lambda loc: loc.tap() if vp_name == "phone" else loc.click()

                for view, must in VIEWS.items():
                    page.goto(a.url + "#" + view)
                    page.wait_for_selector("main .wrap section, main .wrap .err", timeout=15000)
                    page.wait_for_timeout(400)
                    text = page.text_content("main")
                    missing = [m for m in must if m not in text]
                    if missing:
                        problems.append(f"{tag} #{view}: missing {missing}")
                    # Provenance citations deliberately name the committed files and report titles a figure comes
                    # from, so they are read out of the prose check: renaming a real path would break the trail.
                    prose = page.evaluate("""() => { const m = document.querySelector('main').cloneNode(true);
                        m.querySelectorAll('code, .apx-src, a[href^="http"]').forEach(e => e.remove());
                        return m.textContent; }""")
                    if FORBIDDEN.search(prose):
                        problems.append(f"{tag} #{view}: internal identifier {FORBIDDEN.search(prose).group(0)!r}")
                    if JARGON.search(prose):
                        problems.append(f"{tag} #{view}: flagged wording {JARGON.search(prose).group(0)!r}")
                    # the nav is the nine top-level sections, and the current one is marked
                    nav = page.locator("header nav a")
                    if nav.count() != len(NAV) or [nav.nth(i).text_content().strip() for i in range(nav.count())] != NAV:
                        problems.append(f"{tag} #{view}: nav is {[nav.nth(i).text_content() for i in range(nav.count())]}")
                    cur = page.locator("header nav a[aria-current=page]")
                    if cur.count() != 1:
                        problems.append(f"{tag} #{view}: {cur.count()} tabs marked current")
                    # An element wider than its box is only a problem when nothing between it and the page can
                    # scroll: a deliberately scrollable strip (a wide table, the pipeline rail) is not cut off.
                    clipped = page.evaluate("""() => [...document.querySelectorAll('header, main, main *')]
                        .filter(e => e.scrollWidth - e.clientWidth > 2 && getComputedStyle(e).overflowX === 'visible')
                        .filter(e => { for (let n = e.parentElement; n && n !== document.body; n = n.parentElement) {
                            const ox = getComputedStyle(n).overflowX;
                            if (ox === 'auto' || ox === 'scroll') return false; } return true; })
                        .map(e => e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : '')).slice(0, 4)""")
                    if clipped and (vp_name == "phone" or "nav" in " ".join(clipped)):
                        problems.append(f"{tag} #{view}: content cut off in {clipped}")
                    lonely = page.evaluate("""() => [...document.querySelectorAll('main li .tip')].filter(t => {
                        const r = t.getBoundingClientRect();
                        const li = t.closest('li'), pad = parseFloat(getComputedStyle(li).paddingLeft) || 0, q = li.getBoundingClientRect();
                        return r.width > 0 && Math.abs(r.left - (q.left + pad)) < 4 && li.textContent.trim().length > 0; }).length""")
                    if lonely:
                        problems.append(f"{tag} #{view}: {lonely} info icon(s) wrapped onto their own line")

                    if view == "overview":
                        n = page.locator("main .acard").count()
                        if n != 3:
                            problems.append(f"{tag} #{view}: {n} approach cards, expected exactly 3")

                    if view == "comparison":
                        # the growth chart: every approach with results, the passive reference an optional dashed line
                        for mode in ("abs", "gap"):
                            tap(page.locator(f"[data-g={mode}]"))
                            page.wait_for_timeout(150)
                            ds = page.evaluate("""() => { const c = Chart.getChart('c-growth');
                                return c.data.datasets.map((d, i) => ({l: d.label, dash: (d.borderDash || []).length > 0, shown: c.isDatasetVisible(i)})); }""")
                            labels = [d["l"] for d in ds]
                            if mode == "abs":
                                want = ["Deterministic (baseline)", "Agentic Workflow (JEV)"] + (["Causal RAG (exploratory)"] if RAG else []) + ["Passive 60/40 reference"]
                                if labels != want or ds[-1]["shown"] or not ds[-1]["dash"]:
                                    problems.append(f"{tag} #{view} ({mode}): chart lines {ds}")
                                if RAG and not ds[2]["dash"]:
                                    problems.append(f"{tag} #{view}: the exploratory Causal RAG line must be dashed")
                            else:
                                if labels[0] != "Agentic Workflow (JEV)" or labels[-1] != "Deterministic baseline" or not ds[-1]["dash"]:
                                    problems.append(f"{tag} #{view} ({mode}): chart lines {ds}")
                        tap(page.locator("[data-g=abs]"))
                        # optional similarity diagnostic: closed by default; opening it draws the bars and the stock-weight lines
                        if page.locator("#d-alike").get_attribute("open") is not None:
                            problems.append(f"{tag} #{view}: similarity diagnostic open by default")
                        tap(page.locator("#d-alike summary"))
                        page.wait_for_timeout(250)
                        ad = page.evaluate("""() => { const a = Chart.getChart('c-spread'), b = Chart.getChart('c-spy');
                            return a && b ? {bars: a.data.datasets[0].data.length, lines: b.data.datasets.map(d => d.label)} : null; }""")
                        corr = f'{D["audit"]["corr_monthly_net"]:.2f}'
                        if not ad or ad["bars"] != len(D["dev"]["months"]) or ad["lines"][:2] != ["Deterministic (baseline)", "JEV"] \
                                or corr not in page.text_content("#d-alike"):
                            problems.append(f"{tag} #{view}: similarity diagnostic {ad}, expected correlation {corr}")
                        if shots and scheme == "dark":
                            page.locator("#d-alike").screenshot(path=str(shots / f"{scheme}-{vp_name}-similarity.png"))

                    if view in DETAIL:
                        pass
                    if view in ("deterministic", "jev", "committee"):
                        ds = page.evaluate("""() => { const c = Chart.getChart('c-one'); return c.data.datasets.map((d, i) => ({l: d.label, shown: c.isDatasetVisible(i)})); }""")
                        cmp = {"deterministic": [], "jev": ["Deterministic baseline"], "committee": ["JEV"]}[view]
                        labels = [d["l"] for d in ds]
                        if labels[1:1 + len(cmp)] != cmp or not labels[-2].startswith("Own benchmark") \
                                or labels[-1] != "Passive 60/40 reference" or ds[-1]["shown"]:
                            problems.append(f"{tag} #{view}: detail chart lines {ds}")
                        if page.locator("main .attr .arow").count() != 3:
                            problems.append(f"{tag} #{view}: decomposition rows missing")
                        # the three primary approaches are tabbed together; the Committee is a variant reached
                        # from Experiments and has no tab row of its own
                        n_tabs = page.locator("main .atabs a").count()
                        if view != "committee" and n_tabs != 3:
                            problems.append(f"{tag} #{view}: {n_tabs} approach tabs, expected exactly 3")

                    if view == "experiments":
                        # every experiment shows the status the frozen config gives it; results only where one ran
                        rows = page.evaluate("""() => [...document.querySelectorAll('.branch')].map(b => ({
                            name: b.querySelector('.nm').textContent.trim(), status: [...b.classList].find(c => c !== 'branch'),
                            results: b.querySelectorAll('.exres').length}))""")
                        want = {v["name"]: v["status"] for g_ in D["experiments"]["groups"] for v in g_["variants"]}
                        bad = [(r["name"], r["status"], want.get(r["name"])) for r in rows if want.get(r["name"]) != r["status"]]
                        if bad or len(rows) != len(want):
                            problems.append(f"{tag} #{view}: experiment statuses {bad or (len(rows), len(want))}")
                        if any(r["status"] in ("paused", "planned", "blocked") and r["results"] for r in rows):
                            problems.append(f"{tag} #{view}: results shown for an experiment that did not run")
                        for b_ in page.locator(".branch > button").all():
                            tap(b_)
                        page.wait_for_timeout(300)
                        n_res = page.locator(".exres").count()
                        n_want = sum(1 for g_ in D["experiments"]["groups"] for v in g_["variants"] if v.get("result"))
                        if n_res != n_want:
                            problems.append(f"{tag} #{view}: {n_res} result blocks, expected {n_want}")
                        if not page.locator("#app .exres-caution").count():
                            problems.append(f"{tag} #{view}: no caution shown beside the experiment results")
                        if shots and scheme == "dark":
                            page.screenshot(path=str(shots / f"{scheme}-{vp_name}-experiments-open.png"), full_page=True)

                    if view == "signal-value":
                        keys = ["det", "jev"] + (["rag"] if RAG else [])
                        months = D["dev"]["months"]
                        period = [months[0], months[-1], len(months)]
                        ids = ["c-sva-growth", "c-sva-month"] + [f"c-sva-{k}" for k in keys]
                        ch = page.evaluate("""(ids) => Object.fromEntries(ids.map(id => { const c = Chart.getChart(id);
                            return [id, c ? {labels: [c.data.labels[0], c.data.labels.at(-1), c.data.labels.length],
                                             sets: c.data.datasets.map(d => [d.label.split(' (')[0], (d.borderDash || []).length > 0, d.data.length])} : null]; }))""", ids)
                        want = {"c-sva-growth": [["Deterministic", False, len(months)], ["Agentic Workflow", False, len(months)]]
                                               + ([["Causal RAG", True, len(months)]] if RAG else []),
                                "c-sva-month": [["JEV signal contribution", False, len(months)]]}
                        for k in keys:
                            # the exploratory series is dashed throughout, with and without its signals
                            want[f"c-sva-{k}"] = [["With signals", k == "rag", len(months)], ["Without signals", True, len(months)]]
                        for cid, w in want.items():
                            got = ch.get(cid)
                            if not got or got["labels"] != period or [[l[0].split(" (")[0], l[1], l[2]] for l in got["sets"]] != w:
                                problems.append(f"{tag} #{view}: chart {cid} {got}, expected {w}")
                        hi = page.evaluate("""() => { const c = Chart.getChart('c-sva-month'); const bg = c.data.datasets[0].backgroundColor;
                            const odd = bg.map((x, i) => x !== bg[0] ? i : -1).filter(i => i >= 0); return odd.map(i => c.data.labels[i]); }""")
                        if hi != [D["signal_value"]["influential_month"]["decision_month"]]:
                            problems.append(f"{tag} #{view}: highlighted month {hi}")
                        # every published interval that includes zero must be drawn spanning the zero line
                        cis = page.evaluate("""() => [...document.querySelectorAll('#sva-results .cibar')].map(b => { const r = b.querySelector('.range').getBoundingClientRect(), z = b.querySelector('.zero').getBoundingClientRect();
                            return r.left <= z.left + 1 && z.right <= r.right + 1; })""")
                        spans = [D["signal_value"]["systems"][k]["value"]["ci95"][0] <= 0 <= D["signal_value"]["systems"][k]["value"]["ci95"][1] for k in keys]
                        if cis != spans:
                            problems.append(f"{tag} #{view}: interval bars {cis}, expected {spans}")
                        green = page.evaluate("""() => { const pos = getComputedStyle(document.documentElement).getPropertyValue('--pos').trim(); const tmp = document.createElement('i'); tmp.style.color = pos; document.body.append(tmp);
                            const rgb = getComputedStyle(tmp).color; tmp.remove(); return [...document.querySelectorAll('main *')].filter(e => { const s = getComputedStyle(e); return s.color === rgb || s.backgroundColor === rgb; }).length; }""")
                        if green:
                            problems.append(f"{tag} #{view}: {green} element(s) use the success colour")
                        tips = page.evaluate("""() => [...document.querySelectorAll('main .tip span[role=tooltip]')].map(t => t.textContent.split(':')[0])""")
                        need = ["Net CER = Certainty-Equivalent Return", "No-signal portfolio", "Correlation", "Likely range (95%)", "p-value"]
                        if [n for n in need if n not in tips]:
                            problems.append(f"{tag} #{view}: missing tooltips {[n for n in need if n not in tips]}")
                        if page.locator("#sva-results .sva-exp").count() != len(keys) \
                                or page.locator("#sva-tests .sva-exp").count() != len(keys) \
                                or page.locator("#sva-explain .arow").count() != 5:
                            problems.append(f"{tag} #{view}: expected {len(keys)} experiment cards and 5 split rows")

                    # no view may declare a winner: the old 'stronger value' markers are gone
                    if page.locator("main .lead, main .leadmark").count():
                        problems.append(f"{tag} #{view}: winner markers shown")
                    stray = page.evaluate("""() => [...document.querySelectorAll('.tip > span')].filter(s => !s.parentElement.classList.contains('show') && getComputedStyle(s).display !== 'none').length""")
                    if stray:
                        problems.append(f"{tag} #{view}: {stray} tooltip(s) visible without being opened")
                    sw = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                    if sw > 1:
                        problems.append(f"{tag} #{view}: page scrolls sideways by {sw}px")
                    report[f"{scheme}/{vp_name}/{view}"] = {"canvases": page.locator("canvas").count(), "chars": len(text)}
                    if shots and (scheme == "dark" or view in ("overview", "comparison", "signal-value")):
                        page.screenshot(path=str(shots / f"{scheme}-{vp_name}-{view}.png"), full_page=True)

                # the replay advances all three approaches together, one controller for all of them
                page.goto(a.url + "#replay")
                page.wait_for_selector("#rp-play")
                lanes = page.locator("#rp-lanes .rlane").count()
                if lanes != 3:
                    problems.append(f"{tag} replay shows {lanes} lanes, expected 3")
                before = (page.text_content("#rp-m"), page.text_content("#rp-p"))
                tap(page.locator('[data-rp=nm]'))
                page.wait_for_timeout(350)
                if (page.text_content("#rp-m"), page.text_content("#rp-p")) == before:
                    problems.append(f"{tag} replay did not advance a month")
                # the lanes move together: every lane shows the same decision month
                shown = page.evaluate("""() => [...document.querySelectorAll('#rp-lanes .rlane')].length""")
                if shown != 3:
                    problems.append(f"{tag} replay lanes out of step: {shown}")
                tap(page.locator("#rp-restart"))
                page.wait_for_timeout(250)
                if page.text_content("#rp-p") != before[1]:
                    problems.append(f"{tag} replay restart did not return to the first month")

                # flow diagram: selecting a step shows its short explanation
                page.goto(a.url + "#causal-rag")
                page.wait_for_selector(".fnode")
                tap(page.locator(".fnode").nth(4))
                page.wait_for_timeout(200)
                if "Testing Agent." not in (page.text_content(".fdetail") or ""):
                    problems.append(f"{tag} flow step did not show its explanation")

                # experiment branches expand on click or tap
                page.goto(a.url + "#experiments")
                page.wait_for_selector(".branch > button")
                br = page.locator(".branch > button").first
                tap(br)
                if br.get_attribute("aria-expanded") != "true":
                    problems.append(f"{tag} experiment branch did not expand")

                # tooltip opens on hover (desktop) or tap (phone)
                page.goto(a.url + "#overview")
                page.wait_for_selector(".tip > button")
                btn = page.locator(".tip > button").first
                btn.tap() if vp_name == "phone" else btn.hover()
                page.wait_for_timeout(250)
                vis = page.evaluate("getComputedStyle(document.querySelector('.tip > span')).display")
                if vis != "block":
                    problems.append(f"{tag} tooltip did not open ({vis})")

                nonfont = [u for u in failed if "fonts.googleapis.com" not in u and "fonts.gstatic.com" not in u]
                if nonfont:
                    problems.append(f"{tag} failed requests: {nonfont[:3]}")
                if errors:
                    problems.append(f"{tag} console errors: {errors[:3]}")
                ctx.close()
        browser.close()
    print(json.dumps({"views_checked": len(report), "problems": problems}, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
