"""Tests for the signal harness. No network: plugins are tested on fixture text only.

    python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from harness import scoring, store
from harness.alerts import US10Y_JUMP
from harness.contract import Reading
from harness.plugins import fomc_tone, fred_rates, uncertainty


def R(series, date, value):
    return Reading(series=series, date=date, value=value, source="test")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_load_is_backfill_then_live(self):
        c = store.append([R("x", "2026-01-01", 1.0), R("x", "2026-01-02", 2.0)], "p", self.dir, "2026-01-02T00:00:00+00:00")
        self.assertEqual(c, {"backfill": 2, "live": 0, "revision": 0})
        c = store.append([R("x", "2026-01-01", 1.0), R("x", "2026-01-02", 2.0), R("x", "2026-01-03", 3.0)],
                         "p", self.dir, "2026-01-03T00:00:00+00:00")
        self.assertEqual(c, {"backfill": 0, "live": 1, "revision": 0})

    def test_same_data_twice_adds_nothing(self):
        rows = [R("x", "2026-01-01", 1.0)]
        store.append(rows, "p", self.dir)
        size = os.path.getsize(os.path.join(self.dir, "x.csv"))
        c = store.append(rows, "p", self.dir)
        self.assertEqual(sum(c.values()), 0)
        self.assertEqual(os.path.getsize(os.path.join(self.dir, "x.csv")), size)

    def test_revision_is_appended_and_old_view_is_kept(self):
        store.append([R("x", "2026-01-01", 1.0)], "p", self.dir, "2026-01-01T00:00:00+00:00")
        c = store.append([R("x", "2026-01-01", 1.5)], "p", self.dir, "2026-02-01T00:00:00+00:00")
        self.assertEqual(c["revision"], 1)
        self.assertEqual(len(store.read("x", self.dir)), 2)            # nothing overwritten
        self.assertEqual(store.series("x", store_dir=self.dir).iloc[-1], 1.5)
        then = store.series("x", as_of="2026-01-15T00:00:00+00:00", store_dir=self.dir)
        self.assertEqual(then.iloc[-1], 1.0)                           # what we knew in January

    def test_nan_is_skipped(self):
        c = store.append([R("x", "2026-01-01", float("nan"))], "p", self.dir)
        self.assertEqual(sum(c.values()), 0)


class PluginParseTests(unittest.TestCase):
    def test_fred_csv(self):
        text = "observation_date,DGS10\n2026-11-16,4.41\n2026-11-17,.\n2026-11-18,4.47\n"
        out = fred_rates.parse(text, "us10y", "u")
        self.assertEqual([(r.date, r.value) for r in out], [("2026-11-16", 4.41), ("2026-11-18", 4.47)])

    def test_fred_csv_rejects_garbage(self):
        with self.assertRaises(ValueError):
            fred_rates.parse("<html>blocked</html>", "us10y", "u")

    def test_uncertainty_series_to_readings(self):
        s = pd.Series([100.0, np.nan, 120.0], index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]))
        out = uncertainty.to_readings(s, "epu", "u")
        self.assertEqual([r.date for r in out], ["2026-01-01", "2026-01-03"])

    def test_fomc_tone_reads_the_repo_index(self):
        out = fomc_tone.FomcTone().fetch()
        self.assertGreater(len(out), 100)
        self.assertTrue(all(-1.0 <= r.value <= 1.0 for r in out))


def synthetic(seed=0, days=1500):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=days)
    us2y = pd.Series(2 + np.cumsum(rng.normal(0, 0.04, days)), index=idx)
    us10y = pd.Series(3 + np.cumsum(rng.normal(0, 0.04, days)), index=idx) + 0.5 * (us2y - us2y.shift(15)).fillna(0)
    data = {"us10y": us10y, "us2y": us2y,
            "epu": pd.Series(100 + rng.normal(0, 20, days), index=idx),
            "gpr": pd.Series(100 + rng.normal(0, 20, days), index=idx),
            "fomc_tone": pd.Series(rng.uniform(-0.5, 0.5, days // 30), index=idx[::30][: days // 30])}
    return lambda name: data.get(name, pd.Series(dtype=float))


class ScoringTests(unittest.TestCase):
    def test_same_input_same_score(self):
        get = synthetic()
        a, b = scoring.score_alert(US10Y_JUMP, get), scoring.score_alert(US10Y_JUMP, get)
        self.assertEqual(a, b)

    def test_score_and_range_are_bounded(self):
        for seed in range(5):
            out = scoring.score_alert(US10Y_JUMP, synthetic(seed))
            self.assertTrue(0 <= out["low"] <= out["score"] <= out["high"] <= 100)
            self.assertIn(out["level"], ("low", "moderate", "high"))

    def test_points_add_up(self):
        out = scoring.score_alert(US10Y_JUMP, synthetic())
        total = sum(d["points"] for d in out["drivers"])
        self.assertAlmostEqual(out["score"], np.clip(out["base"] + total, 0, 100), delta=1.0)

    def test_each_part_stays_in_range(self):
        out = scoring.score_alert(US10Y_JUMP, synthetic())
        for d in out["drivers"]:
            if d["status"] != "ok":
                continue
            for k in ("R", "S", "P", "H"):
                self.assertTrue(0 <= d[k] <= 1, (d["id"], k, d[k]))
            self.assertLessEqual(abs(d["points"]), US10Y_JUMP["max_points"])

    def test_missing_source_is_reported_not_fatal(self):
        get = synthetic()
        out = scoring.score_alert(US10Y_JUMP, lambda n: pd.Series(dtype=float) if n == "gpr" else get(n))
        row = [d for d in out["drivers"] if d["series"] == "gpr"][0]
        self.assertEqual(row["status"], "no data")
        self.assertEqual(out["signals_used"], 3)
        full = scoring.score_alert(US10Y_JUMP, get)
        self.assertGreater(out["high"] - out["low"], full["high"] - full["low"] - 1)   # range does not narrow

    def test_no_look_ahead(self):
        """Scoring as of a past day must not change when later data is added."""
        get = synthetic()
        cut = get("us10y").index[1200]
        early = lambda n: get(n)[get(n).index <= cut]   # noqa: E731
        self.assertEqual(scoring.score_alert(US10Y_JUMP, early), scoring.score_alert(US10Y_JUMP, get, as_of=cut))

    def test_track_record_needs_enough_events(self):
        z = pd.Series([2.0] * 5 + [0.0] * 95)
        rec = scoring.track_record(z, pd.Series([1.0] * 100))
        self.assertTrue(rec["default"])
        self.assertEqual(rec["H"], scoring.H_DEFAULT)

    def test_track_record_rewards_a_signal_that_worked(self):
        z = pd.Series([2.0] * 50 + [0.0] * 150)
        good = scoring.track_record(z, pd.Series([1.0] * 50 + [0.0] * 150))
        bad = scoring.track_record(z, pd.Series([0.0] * 50 + [1.0] * 50 + [0.0] * 100))
        self.assertGreater(good["H"], H := scoring.H_DEFAULT)
        self.assertLess(bad["H"], H)

    def test_no_target_history(self):
        out = scoring.score_alert(US10Y_JUMP, lambda n: pd.Series(dtype=float))
        self.assertIsNone(out["score"])


if __name__ == "__main__":
    unittest.main()
