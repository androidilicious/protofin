"""Signal harness: source plugins -> dated store -> deterministic risk score.

    python -m harness.run             # fetch, store, score, write site/data/harness.json
    python -m harness.run --dry-run   # fetch and score, write nothing
    python -m harness.run --no-fetch  # score from what is already in the store

No language model is called anywhere in this package.
"""
