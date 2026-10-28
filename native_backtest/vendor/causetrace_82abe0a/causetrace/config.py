"""Paths and fixed settings for the CauseTrace backend."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

CLAIMS_PATH = BASE_DIR / "data" / "macro_claims.parquet"
FAISS_PATH = BASE_DIR / "indexes" / "kg_bge_m3.faiss"
NODES_PATH = BASE_DIR / "indexes" / "kg_nodes.json"

# These must match how the stored vectors were produced; the index is never rebuilt.
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024
QUERY_MAX_TOKENS = 64

# Bounds for node search requests.
QUERY_MAX_CHARS = 500
SEARCH_TOP_K_DEFAULT = 10
SEARCH_TOP_K_MAX = 50

# Bounds for path retrieval, graph exploration and evidence display.
PATH_MAX_HOPS_DEFAULT = 3
PATH_MAX_HOPS_LIMIT = 4
PATH_MAX_RESULTS_DEFAULT = 50
PATH_MAX_RESULTS_LIMIT = 200
PATH_TIME_LIMIT_DEFAULT_S = 5.0
PATH_TIME_LIMIT_MAX_S = 20.0
NEIGHBORHOOD_LIMIT_DEFAULT = 25
NEIGHBORHOOD_LIMIT_MAX = 100
OVERVIEW_TOP_N_MAX = 100
EVIDENCE_LIMIT_DEFAULT = 50
EVIDENCE_LIMIT_MAX = 500

# Local LLM (Ollama). Override with environment variables if needed.
OLLAMA_URL = os.environ.get("CAUSETRACE_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("CAUSETRACE_OLLAMA_MODEL", "qwen3:4b")
OLLAMA_STATUS_TIMEOUT_S = 2.0
OLLAMA_REQUEST_TIMEOUT_S = 180.0
OLLAMA_NUM_CTX = 8192

# Limits on the evidence pack sent to the local model.
PACK_MAX_PATHS = 6
PACK_MAX_RECORDS_PER_EDGE = 4
PACK_MAX_CHARS = 9000
PACK_TEXT_FIELD_MAX_CHARS = 160
QUESTION_MAX_CHARS = 500
PARSE_CANDIDATES = 5

# Helping the user when a mapped concept is thin or a search finds nothing.
THIN_NODE_MAX_DEGREE = 10
HINT_MIN_SIMILARITY = 0.85
HINT_MIN_DEGREE_RATIO = 5
SUGGEST_CANDIDATES_PER_SIDE = 5
SUGGEST_MAX_PATHS_PER_PAIR = 20
SUGGEST_PAIR_TIME_S = 1.0
SUGGEST_TOTAL_TIME_S = 10.0

# Number of stored vectors sampled at startup to check that they are unit length.
NORM_CHECK_SAMPLE = 256
NORM_CHECK_TOLERANCE = 1e-3
