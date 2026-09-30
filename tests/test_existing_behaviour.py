"""Regression checks on the deterministic path that the stochastic mode must not change."""
import committee
import macro_indexes


def test_cio_parser_reads_reported_confidence():
    fields, problems = committee.parse_cio("SPY_Expected_Return_Percent: 6.1\nTLT_Expected_Return_Percent: 2.4\nCIO_Confidence: high")
    assert (fields["spy_q"], fields["tlt_q"], fields["confidence"], problems) == (6.1, 2.4, "High", [])


def test_cio_parser_rejects_missing_confidence_and_implausible_views():
    fields, problems = committee.parse_cio("SPY_Expected_Return_Percent: 90\nTLT_Expected_Return_Percent: 2.4")
    assert fields["spy_q"] is None
    assert any("outside plausible" in p for p in problems) and any("confidence" in p for p in problems)


def test_regime_gate_only_lowers_confidence():
    assert [macro_indexes.downgrade_confidence(c, "elevated") for c in ("High", "Medium", "Low")] == ["Medium", "Low", "Low"]
    assert macro_indexes.downgrade_confidence("High", "normal") == "High"
