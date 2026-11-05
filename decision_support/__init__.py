"""Decision support harness: evidence plugins scored on the level playing field.

A plugin is anything that, given the masked month, returns a typed Answer (a stated view per fund,
optional numeric features, a self-reported confidence, and a readable trace). The harness turns a
plugin's answers into the raw-signal table the level field expects and scores it with the same
calibration, trust (Omega), Black-Litterman and accounting as every other plugin, against doing
nothing and a placebo. Plugins never see labels or each other's answers.
"""
from .contract import FUND_SETS, Answer, Manifest, Plugin, coverage, to_frame, validate  # noqa: F401
from .registry import discover, load  # noqa: F401
