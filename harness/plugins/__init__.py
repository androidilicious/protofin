"""Registry of source plugins. Add a plugin here to switch it on."""
from .fomc_tone import FomcTone
from .fred_rates import FredRates
from .uncertainty import Uncertainty


def all_plugins():
    return [FredRates(), Uncertainty(), FomcTone()]
