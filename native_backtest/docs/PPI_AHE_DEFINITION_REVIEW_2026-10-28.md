# PPI and AHE definition-consistency review (2026-10-28)

**Question.** Do the PPI and average hourly earnings (AHE) definition changes require the Deterministic model's research timeline to start in 2016 instead of February 2015?

**Answer: no.** From 2015-02 onward, every PPI and AHE surprise is computed only from releases under the current definitions, so the frozen start is kept. One item is left for the team (see the end).

## Evidence in the repository

**1. The panel builder starts each series at its new definition's first release.** `stage2/notebooks/build_model_ready_panels.ipynb` (`sheet_cfg`) sets:

| Series | First release used | What happened on that date |
|---|---|---|
| PPI | 2014-02-19 | First release of the PPI Final Demand index as the headline: January 2014 data ([BLS release, 2014-02-19](https://www.bls.gov/news.release/archives/ppi_02192014.htm); [BLS TED, 2014-02-27](https://www.bls.gov/opub/ted/2014/ted_20140227.htm)) |
| AHE | 2010-02-05 | First official all-employee average hourly earnings: the Employment Situation for January 2010 ([BLS Monthly Labor Review, March 2010](https://www.bls.gov/opub/mlr/2010/03/art4full.pdf)) |

**2. Each surprise is standardised on the prior 12 releases of the same series only.** Surprise = actual − Bloomberg median consensus. So the first z-score is the 13th release:
- PPI: 2015-02.
- AHE: 2011-03.

No z-score mixes an old-definition release into its standardisation window.

**3. The committed panels confirm these first months.**
- `model_scoring_panel_E4_meanrule.csv`, `model_unbalanced_panel.csv` and `stage1_macro_panel_snapshot.csv`: the first PPI z-score is 2015-02.
- The first AHE z-score is 2011-03.
- The eight-surprise era E4 begins 2015-02.

**4. No other break.** No later change to either headline definition (Final Demand PPI month-on-month; all-employee AHE month-on-month) is recorded in the builder, the panels or the BLS sources above.

**Conclusion.**
- The training sample (2015-02..2019-02), development and test windows contain only same-definition PPI and AHE surprises.
- A 2016 start would only drop the first twelve standardised PPI observations; it would not remove any definition mix.
- The frozen 2015-02 start stays.

## Remaining item for the team (one line, no data needed)

The source workbook is licensed Bloomberg data and is not in the repository, so the exact tickers behind `ppi_release_raw` and `ahe_release_raw` cannot be read here. The first dates match the two definitions' launch releases exactly, which is strong evidence.

To close the item formally, the workbook owner confirms which two tickers were used. I expect the Final Demand PPI month-on-month and the all-employee AHE month-on-month tickers, but have not seen them.

**Status:** resolved on the repository evidence, pending that one-line confirmation before the final methodological freeze.
