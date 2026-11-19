"""Hawkish minus dovish tone of each FOMC statement.

Reads data/news/fomc_index.csv, which news_pipeline.py builds by scoring every
statement sentence with FOMC-RoBERTa. The scores are our own derived data. This
plugin only reads the file, so it needs no model weights.
"""
import os

import pandas as pd

from ..contract import PUBLIC, Plugin, Reading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(BASE_DIR, "data", "news", "fomc_index.csv")
SOURCE = "federalreserve.gov FOMC statements, scored with FOMC-RoBERTa (news_pipeline.py)"


class FomcTone(Plugin):
    name = "fomc_tone"
    title = "Fed statements"
    licence = PUBLIC
    series = ("fomc_tone",)

    def __init__(self, path=INDEX):
        self.path = path

    def fetch(self, since=None):
        df = pd.read_csv(self.path)
        return [Reading(series="fomc_tone", date=str(d), value=float(v), source=SOURCE, unit="score -1..1")
                for d, v in zip(df["date"], df["score"]) if pd.notna(v)]
