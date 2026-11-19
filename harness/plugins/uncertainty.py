"""Economic Policy Uncertainty and Geopolitical Risk daily indexes.

Wraps macro_indexes.py, which already downloads and caches both files.
  EPU  Baker, Bloom & Davis, www.PolicyUncertainty.com
  GPR  Caldara & Iacoviello, www.matteoiacoviello.com/gpr.htm
Both are free to use with attribution. Both are revised by their authors, which is
why the store keeps every revision as its own row.
"""
from ..contract import ATTRIBUTION, Plugin, Reading


def to_readings(s, series, source):
    return [Reading(series=series, date=str(d.date()), value=float(v), source=source, unit="index")
            for d, v in s.dropna().items()]


class Uncertainty(Plugin):
    name = "uncertainty"
    title = "Policy and geopolitical uncertainty"
    licence = ATTRIBUTION
    series = ("epu", "gpr")

    def fetch(self, since=None):
        import macro_indexes  # imported here so the harness loads without xlrd installed
        out = []
        for series, loader, key in (("epu", macro_indexes.load_epu, "epu"), ("gpr", macro_indexes.load_gpr, "gpr")):
            out.extend(to_readings(loader(), series, macro_indexes.SOURCES[key]))
        return out
