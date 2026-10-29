# Bloomberg export: fed funds futures for FF_FUTURES_6M (v1.2, 2026-10-28)

**Purpose.** FF_FUTURES_6M is the last missing Causal RAG mediator. It is required and is not dropped or proxied without the project lead's recorded approval.

**Definition.** On day d, the series is 100 − PX_SETTLE of the CME 30-Day Fed Funds contract for month(d)+6. Day-to-day changes are taken on the same contract.

**Machine-readable copy:** `native_backtest/config/bloomberg_ff_futures_request_v1.json`, with all tickers listed.

## Exact request

| Item | Value |
|---|---|
| Securities | **176 contracts, July 2012 to February 2027**. Expired contracts (to September 2026): `FF<code><yy> Comdty`, from `FFN12` to `FFU26`. Live contracts (October 2026 to February 2027): `FF<code><y> Comdty`, `FFV6` to `FFG7`. Month codes: F G H J K M N Q U V X Z |
| History field | `PX_SETTLE` only |
| Date range | **2012-01-03 to 2026-08-31** |
| Frequency | Daily, trading days only, no fill. Excel: `=BDH("FFN12 Comdty","PX_SETTLE","2012-01-03","2026-08-31","Days","T","Fill","B")` |
| Static fields, one value per contract | `FUT_DLV_DT_FIRST`, `FUT_DLV_DT_LAST`, `LAST_TRADEABLE_DT`. Excel: `=BDP("FFN12 Comdty","FUT_DLV_DT_FIRST")` |
| Validation series (recommended) | `FEDL01 Index`, `PX_LAST`, same dates and frequency |
| Adjustments | None |

**Why exactly these 176 contracts.**
- **Decision span.** Causal RAG decisions run from 2015-02 to 2026-08.
- **Look-back.** Each mediator test compares its move with the same-length moves over the 36 months before the window. The first window starts on 2015-02-01, so data are needed from January 2012.
- **Contract rule.** Each day uses the contract six months ahead. Dates from January 2012 to August 2026 therefore need the July 2012 to February 2027 contracts, and no others.
- **What the earlier list over-asked for.** It had 186 contracts (January 2012 to June 2027) and the fields `PX_LAST`, `VOLUME` and `OPEN_INT`. None of the extra contracts or fields is used.

## Export

1. **`ff_futures_history.csv`.** Columns `date,ticker,field,value`, one row per date and contract.
   - A wide BDH sheet saved as CSV is also accepted: a `Date` column, then one `<ticker>|PX_SETTLE` column per contract.
   - Include the `FEDL01 Index` rows if available.
2. **`ff_futures_static.csv`.** Columns `ticker,field,value`.
3. **Format.** UTF-8, header row, ISO dates (YYYY-MM-DD), full precision, missing values omitted.
4. **Note.** One line with the export date and the Bloomberg function or add-in version used.

**Hand-over.** Attach the files in the chat, or put them in a folder connected to this session. They are stored only in the git-ignored `native_backtest/data/_licensed/bloomberg/`. Nothing licensed is committed.

## On import

Run `python -m native_backtest.scripts.import_ff_futures`. It checks:

| Check | Requirement |
|---|---|
| Contract month | Taken from the delivery dates |
| Prices | Between 90 and 100.5 |
| Duplicates | None |
| Coverage | The six-month-ahead contract has a value on ≥ 99.5% of business days, with no gap over 3 days |
| Expired contracts | Each settles within 1 bp of 100 − that month's average effective rate, when `FEDL01` is supplied |
| Large moves | One-day moves over 50 bp are listed for review |

The report holds hashes and check results only. Then:
- FF_FUTURES_6M joins the mediator inventory as v3.
- Packets are rebuilt as v3, with v1 and v2 unchanged.
- Trigger counts are final.
