"""The plugin contract: what every information source must hand to the harness.

A plugin turns one outside source into a list of Reading records. It does not score,
weight or interpret anything. To add a source, write a class with `name`, `series`,
`licence` and a `fetch()` method, and add it to harness/plugins/__init__.py.
"""
from dataclasses import dataclass

# Licence labels decide what may be committed to a public repository.
PUBLIC = "public"            # public domain or our own derived data: store freely
ATTRIBUTION = "attribution"  # free to redistribute with credit: store, and credit in the README
RESTRICTED = "restricted"    # terms limit republishing: never written to the store


@dataclass(frozen=True)
class Reading:
    """One observation of one series on one date."""
    series: str        # stable id, e.g. "us10y"
    date: str          # the day the value describes, YYYY-MM-DD
    value: float
    source: str        # URL or citation the value came from
    unit: str = ""


class Plugin:
    """Base class for a source plugin."""
    name = ""          # short id, e.g. "fred_rates"
    title = ""         # label for people, e.g. "Treasury yields"
    licence = PUBLIC
    series = ()        # ids of the series this plugin produces

    def fetch(self):
        """Return every Reading the source currently publishes (history included).

        The store keeps only what is new or changed, so returning the full history on
        every run is expected and safe.
        """
        raise NotImplementedError
