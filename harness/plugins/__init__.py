"""Registry of source plugins. Add a plugin here to switch it on."""
from .fomc_tone import FomcTone
from .treasury_yields import TreasuryYields
from .uncertainty import Uncertainty


def all_plugins():
    return [TreasuryYields(), Uncertainty(), FomcTone()]
