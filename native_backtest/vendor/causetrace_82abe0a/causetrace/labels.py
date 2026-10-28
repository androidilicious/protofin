"""Label normalization shared by the graph, the index and query handling."""

from typing import Optional

import pandas as pd


def normalize_label(text: Optional[str]) -> str:
    """Strip and lowercase a label, matching how graph node names were exported."""
    if text is None:
        return ""
    return str(text).strip().lower()


def normalize_series(values: pd.Series) -> pd.Series:
    """Vectorized normalize_label; missing values become pandas NA."""
    return values.astype("string").str.strip().str.lower()
