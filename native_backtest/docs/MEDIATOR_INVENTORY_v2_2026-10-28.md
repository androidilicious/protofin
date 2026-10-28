# AP3 mediator-data inventory v2 — validation (2026-10-28)

**Status: 6 of 7 series validated; fed funds futures pending (Bloomberg).** Development packets and trigger counts built on this inventory stay **provisional** until the futures series is supplied or the team drops it. Inventory v1, its 95 packets and its 550 triggers are unchanged and still reproduce byte for byte.

Machine-readable result: `native_backtest/out/ap3/mediator_inventory_v2.json`, written by `native_backtest/scripts/ap3_mediator_inventory.py`. The script runs offline and recomputes every check from the pinned files.

## What was checked

Each series was compared with **ALFRED**, the St. Louis Fed's archive of what FRED showed on each past date. The ALFRED downloads were run in the browser on your computer, over 3,000–3,700 vintages per series, with the hash of each response recorded (`native_backtest/data/ap3_mediators/alfred_vintage_evidence_v1.json`).

| Series | Source in v2 | Equals the official latest data | First posted later than the rule | Revised values | Validated |
|---|---|---|---|---|---|
| 2-year Treasury (UST2Y) | FRED DGS2, pinned mirror | Yes, 3,709 days | 123 (mostly Dec 2011–Mar 2012, when FRED posted two days late) | 0 | Yes |
| 10-year Treasury (UST10Y) | FRED DGS10, pinned mirror | Yes, 3,709 days | 124 | 3 (largest: 2014-01-14, 2.77 → 2.88 the next day) | Yes |
| 10Y–3M slope | FRED T10Y3M, Stage 2 pin | Yes, 3,709 days | 29 | 3, including a spurious 0.00 for Good Friday 2017, shown for two days | Yes |
| 5-year breakeven (BEI5Y) | **New**: FRED T5YIE, browser capture committed with hashes | Yes, 3,709 days | 23 against the rule | 2 (≤ 2 bp) | Yes |
| IG spread **proxy** | FRED BAA10Y, Stage 2 pin | Yes, 3,704 days | **204, including a five-month gap** | **13 (up to 21 bp)** | Yes, as a labelled proxy |
| VIX | **Changed**: CBOE daily close, one public-domain source | Yes, all of 2011-12..2026-09-22 equals VIXCLS | n/a (market close) | n/a | Yes |
| Fed funds futures, 6 months ahead | Bloomberg export requested | — | — | — | **Pending** |

## Findings that changed the data

1. **Late postings and revisions are now point-in-time.**
   - Each value's `available_at` is the later of two dates: the rule (next business day, 18:00 ET), or the date ALFRED first shows the value.
   - A revised value enters as a new version on its revision date.
   - A decision therefore sees exactly what was public at the time.
2. **BAA10Y had a five-month posting gap.** Observations from 2016-10-07 to 2017-03-20 first appeared on FRED on 2017-03-22. The Federal Reserve's H.15 release had stopped carrying Moody's yields in October 2016.
   - Under v1 rules, the decisions for October 2016 to February 2017 could see data that was not public at the time.
   - In v2, the series stops at 2016-10-06 for those decisions.
   - Revisions mattered too: the May and June 2020 decisions saw values that were later revised (by 2–7 bp). v2 gives those decisions the values public at the time.
3. **VIX now has one source covering the whole span.** The v1 splice started on 2015-01-02. That left the 36-month stress reference short for 2015–2017 and blocked VIX triggers until April 2015.
   - v2 uses the CBOE daily file (`datasets/finance-vix`, public domain), which equals FRED's VIXCLS exactly over 2011-12-01..2026-09-22.
   - The old splice differed from VIXCLS on 7 days in January–February 2018, by up to 0.15 points.
   - Stage 2's own data freeze is untouched.
4. **One rule convention needs stating.** ALFRED dates its vintages to the day, not the hour. A vintage is treated as public at 18:00 ET on its date, the same convention as the base rule.
   - FRED's T5YIE page showed "Updated 4:03 PM CDT" (5:03 PM ET) for the same day's value.

## The IG-spread proxy and what it implies

Approved 2026-10-28 as an **explicitly labelled proxy**, not an equivalent of an investment-grade option-adjusted spread. In v2 the label travels with the data:
- each packet's `mediator_series` block,
- each stress trigger's `series_label`,
- each mediator test result.

So the model, the records and the dashboard all name it as Moody's Baa minus the 10-year Treasury yield.

| Difference from IG OAS | Consequence for AP3 |
|---|---|
| Covers Baa (the lowest investment-grade tier) only, not the whole IG index | More sensitive to downgrade and default risk than LQD's average-quality basket; credit moves may look larger than the IG market's |
| Long seasoned bonds against a 10-year Treasury, not a duration-matched curve | Moves with the 10s–30s Treasury curve as well as with credit; a curve move can show up as a "credit" mediator move |
| Yield spread, not option-adjusted | Callable bonds bias it when rates move sharply |
| Moody's data: posting gap Oct 2016–Mar 2017 and revisions | Fewer usable credit triggers in late 2016; handled point-in-time (see above) |
| Moody's licence | Levels stay out of git (pinned by hash; revisions stored as differences in bp) |

**Reporting rule:**
- Mediator tests on this series are reported as "IG spread proxy (Baa − 10Y)".
- A consistent move is recorded as consistent with the proxy, not as evidence about IG OAS.
- Any LQD-related finding resting mainly on this proxy is flagged.

## Trigger counts, v1 and v2 (development, 95 months; provisional)

| | v1 (unchanged) | v2 |
|---|---|---|
| Macro surprises | 238 | 238 |
| FOMC | 67 | 67 |
| Market stress | 245 | 293 (UST2Y 54, UST10Y 52, slope 50, BEI5Y 49, IG proxy 46, VIX 42) |
| **Total** | **550** | **598** |
| Stress inputs public before the decision | 245/245 | 293/293 |

Differences:
- +49 from the 5-year breakeven, which v1 lacked.
- IG proxy 48 → 46 because of the posting gap.
- VIX 41 → 42 because of the full history.

Both sets are provisional. v2 packets (`ap3_packets_v2.jsonl`, SHA-256 `0522bb07…`) sit next to the v1 file; nothing was relabelled.

## Still pending

- **Fed funds futures (FF_FUTURES_6M).** Data request: `BLOOMBERG_FED_FUNDS_FUTURES_REQUEST_2026-10-28.md`. When the export arrives:
  1. The importer validates it.
  2. The inventory is re-run.
  3. Packets are rebuilt as v3.
