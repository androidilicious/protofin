# Bloomberg data request: fed funds futures for AP3's FF_FUTURES_6M mediator (2026-10-28)

This is the last series missing from the AP3 mediator inventory (`MEDIATOR_INVENTORY_v2_2026-10-28.md`). The specification below can be run as is on a Bloomberg terminal or with the Excel add-in. A machine-readable copy (v1.1), with all 186 contract tickers listed and checked against the CME month codes, is in `native_backtest/config/bloomberg_ff_futures_request_v1.json`.

## What the mediator measures

On each trading day d, FF_FUTURES_6M is the average effective fed funds rate the market implies for the calendar month six months after d:

> 100 − the daily settlement price of the CME 30-Day Federal Funds futures contract for that month.

- One-day changes use the same contract, so the switch to the next contract at each month-end creates no jump.
- **Availability rule:** the same day at 17:00 ET, after CME's daily settlement.

## Exact request

| Item | Specification |
|---|---|
| Securities | Individual monthly contracts, January 2012 to June 2027 (186 contracts). Expired contracts use the two-digit-year form, e.g. `FFZ16 Comdty`; live contracts the one-digit form, e.g. `FFH7 Comdty`. If a form does not resolve, look up the exact contract from the `FF1 Comdty` chain (CT \<GO\>). The full list is in the JSON file |
| History fields (BDH) | `PX_SETTLE` (required), `PX_LAST`, `VOLUME`, `OPEN_INT` |
| Static fields (BDP), one row per contract | `FUT_DLV_DT_FIRST`, `FUT_DLV_DT_LAST`, `LAST_TRADEABLE_DT` (required); `SECURITY_DES`, `NAME`, `FUT_FIRST_TRADE_DT` |
| Reference series | `FEDL01 Index`, field `PX_LAST`, same dates. Used to check every expired contract's final settlement |
| Date range | 2011-12-01 to 2026-09-30 |
| Frequency | Daily, trading days only: non-trading days omitted, no fill (Excel: `"Days","T","Fill","B"`) |
| Adjustments | None. No currency conversion |

**Excel example**, one cell per contract:
- History: `=BDH("FFZ16 Comdty","PX_SETTLE,PX_LAST,VOLUME,OPEN_INT","2011-12-01","2026-09-30","Days","T","Fill","B")`
- Static: `=BDP("FFZ16 Comdty","FUT_DLV_DT_FIRST")`, and the same for each static field.

**Fallback, only if individual contracts are unavailable:** generic `FF1`–`FF9 Comdty`, `PX_SETTLE`, plus `LAST_TRADEABLE_DT` for each underlying contract. Generic tickers roll at expiry, so the roll dates are needed to avoid false jumps.

## Export format

Two UTF-8 CSV files with header rows and ISO dates (YYYY-MM-DD). Values at full precision; missing values omitted. Templates: `native_backtest/data/ap3_mediators/templates/`.

1. `ff_futures_history.csv`: columns `date,ticker,field,value`, one row per date, ticker and field. A wide Excel sheet saved as CSV is also accepted: first column `Date`, then one column per `<ticker>|<field>`.
2. `ff_futures_static.csv`: columns `ticker,field,value`.

**Where to put them:** `native_backtest/data/_licensed/bloomberg/`. This folder is git-ignored, so neither the export nor anything derived from it is committed.

## What happens on import

Run `python -m native_backtest.scripts.import_ff_futures`. It writes the series to the licensed folder, and a report of hashes and checks, with no prices, to `native_backtest/out/ap3/ff_futures_import_report.json`.

| Check | Required |
|---|---|
| Each contract identified from its delivery dates (not from the ticker text); no month claimed twice | Yes |
| Settlement prices between 90 and 100.5 | Yes |
| No duplicate date/ticker/field rows | Yes |
| The six-month-ahead contract has a value on ≥ 99.5% of business days, with no gap longer than 3 business days | Yes |
| Each expired contract's last settlement within 1 bp of 100 − that month's average effective fed funds rate | Yes, when `FEDL01 Index` is supplied |
| One-day moves over 50 bp | Listed for review against FOMC days |

When the import passes:
1. The mediator inventory is re-run, with FF_FUTURES_6M added as inventory v3.
2. Development packets are rebuilt as v3, leaving v1 and v2 unchanged.
3. Trigger counts stop being provisional.

## Delivery

- Two files: `ff_futures_history.csv` and `ff_futures_static.csv`. Dates are Bloomberg trade dates, which are the CME settlement dates.
- Add a one-line note with the date of the export and the Bloomberg function or add-in used.
- Attach the files in the chat, or place them in a folder connected to this session. They are stored only in the git-ignored licensed folder.

## No substitution without approval

FF_FUTURES_6M is a required input. It is not dropped, and no proxy is used in its place, without the project lead's explicit approval recorded before any model run. Until the export arrives, the mediator stays "pending" in the inventory and the readiness reports.
