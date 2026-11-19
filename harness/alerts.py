"""Alert definitions. Every number here is a setting, not a fitted result.

sign   +1 if a high reading is expected to raise the risk, -1 if it is expected to lower it.
       This is a hypothesis. H (track record) is what checks it against history.
trust  R, source trust, set by hand: 1.0 official release, about 0.6 news-based index.
steps  links between the signal and the target on the causal map. P = 0.7 ** (steps - 1).
window days of history that define "normal" for S, counted in trading days.
"""

US10Y_JUMP = {
    "id": "us10y_jump",
    "title": "10-year yield jump",
    "target": "us10y",          # series the alert is about
    "horizon": 20,              # trading days ahead
    "threshold": 0.25,          # a "jump" is a rise of at least this many percentage points
    "base": 30,                 # resting score when no signal is unusual
    "max_points": 40,           # most points one signal can add or remove
    "signals": [
        {"id": "us2y_chg20", "label": "2-year Treasury yield, 20-day change", "series": "us2y",
         "transform": "chg20", "window": 252, "sign": +1, "trust": 1.0, "steps": 1},
        {"id": "fomc_tone", "label": "Fed statement tone (hawkish minus dovish)", "series": "fomc_tone",
         "transform": "level", "window": 504, "sign": +1, "trust": 0.9, "steps": 1},
        {"id": "epu_mean30", "label": "Economic policy uncertainty, 30-day mean", "series": "epu",
         "transform": "mean30", "window": 252, "sign": -1, "trust": 0.6, "steps": 2},
        {"id": "gpr_mean30", "label": "Geopolitical risk, 30-day mean", "series": "gpr",
         "transform": "mean30", "window": 252, "sign": -1, "trust": 0.6, "steps": 2},
    ],
}

ALERTS = [US10Y_JUMP]
