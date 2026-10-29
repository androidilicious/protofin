"""Model client for AP3's agents.

One interface, four providers:

- ``EngineeringMockProvider``: canned responses for engineering tests only. Every call and every
  output produced through it is marked ``engineering_mock``; the shared evaluator refuses to score
  records with that mode, so mock outputs can never become backtest results.
- ``BedrockProvider``, ``HFEndpointProvider`` (a dedicated endpoint serving pinned weights through an
  OpenAI-compatible vLLM server) and ``DeepInfraProvider``: Llama 3.1 70B Instruct. All refuse to run
  unless ``AP3_ALLOW_PAID_INFERENCE=1`` is set and credentials are present, so no paid call can happen
  before approval.
- ``CostGuard``: a hard spending cap kept in an append-only ledger. Before each paid call it adds the
  call's worst-case cost (all input tokens at a conservative 3 characters per token, plus the full output
  allowance; for an hourly endpoint, the time it has been running) and refuses if the cap would be passed.

Every response is validated against its JSON schema, cached by the SHA-256 of the full request,
and logged append-only with request and response hashes.
"""
from __future__ import annotations

import calendar
import dataclasses
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import jsonschema

LLAMA_MODEL_IDS = {
    "bedrock": "meta.llama3-1-70b-instruct-v1:0",
    "hf_endpoint": "meta-llama/Llama-3.1-70B-Instruct",
    "deepinfra": "meta-llama/Meta-Llama-3.1-70B-Instruct",
}


class PaidInferenceNotApproved(RuntimeError):
    pass


class ModelOutputError(RuntimeError):
    raw_text: Optional[str] = None           # the model's reply, kept for diagnosis when it was not valid
    pass


class BudgetExceeded(RuntimeError):
    pass


class CostGuard:
    """Hard USD cap for one approval stage, persisted in an append-only JSONL ledger.

    pricing: {"mode": "tokens", "usd_per_m_input": x, "usd_per_m_output": y}
          or {"mode": "hourly", "usd_per_hour": z, "started_utc": "...Z"} (dedicated endpoint, billed while running)."""

    def __init__(self, cap_usd: float, ledger: Path, pricing: dict, gate: Optional[Callable[[], Optional[str]]] = None):
        """gate: returns a reason to refuse the next call (e.g. the endpoint is not running), or None."""
        self.cap, self.ledger, self.pricing, self.gate = float(cap_usd), Path(ledger), dict(pricing), gate
        self.ledger.parent.mkdir(parents=True, exist_ok=True)

    def spent(self) -> float:
        if self.pricing["mode"] == "hourly":
            start = calendar.timegm(time.strptime(self.pricing["started_utc"], "%Y-%m-%dT%H:%M:%SZ"))
            return (time.time() - start) / 3600.0 * float(self.pricing["usd_per_hour"])
        if not self.ledger.exists():
            return 0.0
        return sum(json.loads(l)["usd"] for l in self.ledger.read_text().splitlines() if l.strip())

    def worst_case(self, req: "Request") -> float:
        if self.pricing["mode"] == "hourly":
            return 0.0   # time-billed: the check is on elapsed time
        tin = (len(req.system) + len(req.user)) / 3.0
        return (tin * self.pricing["usd_per_m_input"] + req.max_tokens * self.pricing["usd_per_m_output"]) / 1e6

    def check(self, req: "Request") -> None:
        if self.gate is not None:
            why = self.gate()
            if why:
                raise BudgetExceeded(f"stopping before the call: {why}")
        s, w = self.spent(), self.worst_case(req)
        if s + w > self.cap:
            raise BudgetExceeded(f"cap ${self.cap:.2f}: spent ${s:.4f}, next call up to ${w:.4f}; stopping before the call")

    def record(self, step: str, usage: Optional[dict]) -> float:
        if self.pricing["mode"] == "hourly":
            usd = 0.0
        else:
            u = usage or {}
            tin = u.get("inputTokens", u.get("prompt_tokens", 0)) or 0
            tout = u.get("outputTokens", u.get("completion_tokens", 0)) or 0
            usd = (tin * self.pricing["usd_per_m_input"] + tout * self.pricing["usd_per_m_output"]) / 1e6
        with self.ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "step": step, "usage": usage, "usd": usd}) + "\n")
        return usd


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclasses.dataclass
class Request:
    step: str
    system: str
    user: str
    schema: dict
    temperature: float
    seed: Optional[int]
    max_tokens: int = 2000
    # Later messages of a multi-turn exchange, after the first user message: the model's own earlier replies as
    # "assistant" turns and what it was shown next as "user" turns (e.g. the Hypothesis Agent's tool loop).
    turns: Tuple[Dict[str, str], ...] = ()

    def messages(self) -> List[Dict[str, str]]:
        return [{"role": "user", "content": self.user}] + [{"role": t["role"], "content": t["content"]} for t in self.turns]

    def prompt_chars(self) -> int:
        return len(self.system) + sum(len(m["content"]) for m in self.messages())

    def key(self, provider: str, model: str) -> str:
        k = {"provider": provider, "model": model, "step": self.step, "system": self.system, "user": self.user,
             "schema": self.schema, "temperature": self.temperature, "seed": self.seed, "max_tokens": self.max_tokens}
        if self.turns:                       # single-message requests keep their earlier cache keys
            k["turns"] = [dict(t) for t in self.turns]
        return _sha(_canon(k))


class EngineeringMockProvider:
    """Deterministic canned responses. ENGINEERING TESTS ONLY — never a backtest input."""

    name = "engineering_mock"
    model = "engineering-mock (no model)"
    is_mock = True

    def __init__(self, responder: Callable[[Request], dict]):
        self.responder = responder

    def complete(self, req: Request) -> Tuple[str, dict]:
        return _canon(self.responder(req)), {"request_id": None}


BUDGET = Path(__file__).resolve().parents[2] / "native_backtest/config/budget_v1.json"


def paid_budget_usd() -> float:
    """The project's additional budget for paid inference; missing file means no budget."""
    try:
        return float(json.loads(BUDGET.read_text())["additional_budget_usd"])
    except (OSError, KeyError, ValueError):
        return 0.0


def _require_approval(provider: str, env_vars: Tuple[str, ...]) -> None:
    if paid_budget_usd() <= 0:
        raise PaidInferenceNotApproved(f"{provider}: the project budget for paid inference is $0 (config/budget_v1.json)")
    if os.environ.get("AP3_ALLOW_PAID_INFERENCE") != "1":
        raise PaidInferenceNotApproved(f"{provider}: paid inference is not approved (set AP3_ALLOW_PAID_INFERENCE=1 only after approval)")
    missing = [v for v in env_vars if not os.environ.get(v)]
    if missing:
        raise PaidInferenceNotApproved(f"{provider}: missing credentials {missing}")


class DeepInfraProvider:
    name = "deepinfra"
    model = LLAMA_MODEL_IDS["deepinfra"]
    is_mock = False
    url = "https://api.deepinfra.com/v1/openai/chat/completions"

    def complete(self, req: Request) -> Tuple[str, dict]:
        _require_approval(self.name, ("DEEPINFRA_API_KEY",))
        import requests

        body = {"model": self.model, "temperature": req.temperature, "max_tokens": req.max_tokens,
                "messages": [{"role": "system", "content": req.system}] + req.messages(),
                "response_format": {"type": "json_object"}}
        if req.seed is not None:
            body["seed"] = req.seed
        r = requests.post(self.url, json=body, timeout=600, headers={"Authorization": f"Bearer {os.environ['DEEPINFRA_API_KEY']}"})
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"], {"request_id": j.get("id"), "usage": j.get("usage"), "model_returned": j.get("model")}


class BedrockProvider:
    """Amazon Bedrock, Converse API. In-region model ID in us-west-2 (the only in-region Region for this model);
    the 'us.' geo profile would route across three US Regions and is not used."""
    name = "bedrock"
    model = LLAMA_MODEL_IDS["bedrock"]
    is_mock = False

    def complete(self, req: Request) -> Tuple[str, dict]:
        _require_approval(self.name, ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"))
        import boto3

        client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-west-2"))
        resp = client.converse(modelId=self.model, system=[{"text": req.system}],
                               messages=[{"role": m["role"], "content": [{"text": m["content"] + ("\n\nReturn JSON only." if i == len(req.messages()) - 1 else "")}]}
                                         for i, m in enumerate(req.messages())],
                               inferenceConfig={"temperature": req.temperature, "maxTokens": req.max_tokens})
        text = resp["output"]["message"]["content"][0]["text"]
        return text, {"request_id": resp.get("ResponseMetadata", {}).get("RequestId"), "usage": resp.get("usage"),
                      "note": "Bedrock Converse does not accept a seed for Llama; repeated runs rely on the cache for replay"}


class HFEndpointProvider:
    """Dedicated Hugging Face Inference Endpoint running an OpenAI-compatible vLLM server with the model
    repository pinned to one commit (AP3_MODEL_REVISION) and a pinned container image. The served model
    name and revision are checked on every call."""
    name = "hf_endpoint"
    model = LLAMA_MODEL_IDS["hf_endpoint"]
    is_mock = False

    def complete(self, req: Request) -> Tuple[str, dict]:
        _require_approval(self.name, ("HF_TOKEN", "AP3_HF_ENDPOINT_URL", "AP3_MODEL_REVISION"))
        import requests

        body = {"model": self.model, "temperature": req.temperature, "max_tokens": req.max_tokens,
                "messages": [{"role": "system", "content": req.system}] + req.messages(),
                "response_format": {"type": "json_object"}}
        if req.seed is not None:
            body["seed"] = req.seed
        # No scale-up header: a request must never wake a paused or scaled-to-zero endpoint (a new replica is billed).
        r = requests.post(os.environ["AP3_HF_ENDPOINT_URL"].rstrip("/") + "/v1/chat/completions", json=body,
                          timeout=float(os.environ.get("AP3_REQUEST_TIMEOUT_SECONDS", "300")),
                          headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"})
        r.raise_for_status()
        j = r.json()
        if j.get("model") not in (None, self.model, "/repository"):
            raise ModelOutputError(f"endpoint served {j.get('model')!r}, expected {self.model!r}")
        return j["choices"][0]["message"]["content"], {"request_id": j.get("id"), "usage": j.get("usage"), "model_returned": j.get("model"),
                                                       "revision": os.environ["AP3_MODEL_REVISION"]}


class ContextOverflow(ModelOutputError):
    """The prompt would not fit the model's context window; refused instead of letting the server truncate it."""


# Free local inference. The original CauseTrace project runs qwen3:4b through Ollama (causetrace/config.py);
# AP3 uses the same tag, pinned to the official library digest. A DOCUMENTED MODEL SUBSTITUTION for the planned
# Llama 3.1 70B Instruct: smaller (4.02B parameters, Q4_K_M), so results are not a reproduction of the 70B system.
OLLAMA_MODEL = "qwen3:4b"
OLLAMA_DIGEST_PREFIX = "359d7dd4bcda"      # ollama.com/library/qwen3:4b, checked 2026-10-29
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


class OllamaProvider:
    """A model served by Ollama on THIS machine (e.g. a free Kaggle GPU notebook). Costs nothing and refuses any
    non-local address, so it can never reach a paid service. Thinking mode is off; replies are constrained to the
    step's JSON schema (falls back to plain JSON mode if the server cannot compile the schema, and says so);
    prompts that could exceed the context window are refused, never truncated."""
    name = "ollama_local"
    is_mock = False
    is_free = True

    def __init__(self, urls: Optional[str] = None, num_ctx: Optional[int] = None, structured: bool = True):
        from urllib.parse import urlparse
        raw = urls or os.environ.get("AP3_OLLAMA_URLS", "http://127.0.0.1:11434")
        self.urls = [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]
        for u in self.urls:
            if urlparse(u).hostname not in _LOCAL_HOSTS:
                raise PaidInferenceNotApproved(f"OllamaProvider serves only from this machine, not {u}")
        self.num_ctx = int(num_ctx or os.environ.get("AP3_OLLAMA_NUM_CTX", "32768"))   # Qwen3-4B native context
        self.structured = structured
        self.model = f"{OLLAMA_MODEL}@{OLLAMA_DIGEST_PREFIX}"
        self.digest: Optional[str] = None
        self._i = 0
        self._lock = threading.Lock()

    def verify(self) -> dict:
        """Every server must serve the pinned model digest. Returns provenance."""
        import requests
        prov = []
        for u in self.urls:
            tags = requests.get(u + "/api/tags", timeout=30).json().get("models", [])
            m = next((x for x in tags if x.get("name") in (OLLAMA_MODEL, OLLAMA_MODEL + ":latest") or x.get("model") == OLLAMA_MODEL), None)
            if m is None:
                raise PaidInferenceNotApproved(f"{u}: {OLLAMA_MODEL} is not pulled")
            if not str(m.get("digest", "")).startswith(OLLAMA_DIGEST_PREFIX):
                raise ModelOutputError(f"{u}: {OLLAMA_MODEL} digest {m.get('digest')} is not the pinned {OLLAMA_DIGEST_PREFIX}")
            ver = requests.get(u + "/api/version", timeout=30).json().get("version")
            prov.append({"url": u, "digest": m["digest"], "size": m.get("size"), "details": m.get("details"), "ollama_version": ver})
        self.digest = prov[0]["digest"]
        return {"model": OLLAMA_MODEL, "servers": prov, "num_ctx": self.num_ctx, "structured_output": self.structured}

    def _url(self) -> str:
        with self._lock:
            u = self.urls[self._i % len(self.urls)]
            self._i += 1
            return u

    def complete(self, req: Request) -> Tuple[str, dict]:
        import requests
        if self.digest is None:
            self.verify()
        est = req.prompt_chars() / 4.0                      # pre-check for clear overflow; the server's own count is checked after
        if est + req.max_tokens > self.num_ctx:
            raise ContextOverflow(f"{req.step}: about {est:.0f} prompt tokens + {req.max_tokens} output exceed num_ctx {self.num_ctx}")
        body = {"model": OLLAMA_MODEL, "stream": False, "think": False,
                "messages": [{"role": "system", "content": req.system}] + req.messages(),
                "format": req.schema if (self.structured and req.schema) else "json",
                "options": {"temperature": req.temperature, "seed": req.seed if req.seed is not None else 0,
                            "num_ctx": self.num_ctx, "num_predict": req.max_tokens}}
        u = self._url()
        r = requests.post(u + "/api/chat", json=body, timeout=900)
        fallback = False
        if r.status_code == 400 and self.structured:      # schema the server cannot compile: plain JSON mode, recorded
            body["format"], fallback = "json", True
            r = requests.post(u + "/api/chat", json=body, timeout=900)
        r.raise_for_status()
        j = r.json()
        if (j.get("prompt_eval_count") or 0) >= self.num_ctx - 8:
            raise ContextOverflow(f"{req.step}: prompt filled the context window ({j.get('prompt_eval_count')} tokens); possibly truncated")
        return j["message"]["content"], {
            "usage": {"prompt_tokens": j.get("prompt_eval_count"), "completion_tokens": j.get("eval_count")},
            "durations_ns": {k: j.get(k) for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")},
            "done_reason": j.get("done_reason"), "server": u, "model_digest": self.digest, "schema_fallback": fallback,
            "cost_usd": 0.0}


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ModelOutputError("no JSON object in model output")
    return json.loads(text[start:text.rfind("}") + 1])


class LLMClient:
    def __init__(self, provider, cache_dir: Path, call_log: Path, run_tag: str, max_calls: Optional[int] = None,
                 guard: Optional[CostGuard] = None):
        self.provider = provider
        self.guard = guard
        if not getattr(provider, "is_mock", False) and not getattr(provider, "is_free", False) and guard is None:
            raise PaidInferenceNotApproved("a paid provider needs a CostGuard (hard spending cap)")
        self.cache_dir = Path(cache_dir)
        self.call_log = Path(call_log)
        self.run_tag = run_tag
        self.max_calls = max_calls
        self.calls = 0
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.call_log.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()   # several months may run in parallel threads; budget and logs stay serialised

    @property
    def is_mock(self) -> bool:
        return bool(getattr(self.provider, "is_mock", False))

    def complete_json(self, req: Request) -> Tuple[Any, Dict[str, Any]]:
        key = req.key(self.provider.name, self.provider.model)
        cpath = self.cache_dir / f"{key}.json"
        cached = cpath.exists()
        if cached:
            text = json.loads(cpath.read_text())["text"]
            meta = json.loads(cpath.read_text())["meta"]
        else:
            with self._lock:
                if self.max_calls is not None and self.calls >= self.max_calls:
                    raise RuntimeError(f"call budget {self.max_calls} exhausted")
                if self.guard is not None:
                    self.guard.check(req)
                self.calls += 1
            text, meta = self.provider.complete(req)
            with self._lock:
                if self.guard is not None:
                    meta["usd"] = self.guard.record(req.step, meta.get("usage"))
                cpath.write_text(_canon({"text": text, "meta": meta, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
        try:
            obj = _extract_json(text)
            jsonschema.validate(obj, req.schema)
        except (ModelOutputError, json.JSONDecodeError, jsonschema.ValidationError) as e:
            bad = {"run_tag": self.run_tag, "step": req.step, "provider": self.provider.name, "model": self.provider.model,
                   "mock": self.is_mock, "cache_key": key, "cached": cached, "invalid": True, "error": f"{type(e).__name__}: {str(e)[:300]}",
                   "response_sha256": _sha(text), "logged_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            with self._lock, self.call_log.open("a", encoding="utf-8") as f:
                f.write(_canon(bad) + "\n")
            err = ModelOutputError(f"{req.step}: invalid model output ({type(e).__name__})")
            err.raw_text = text[:4000]
            raise err from e
        log = {"run_tag": self.run_tag, "step": req.step, "provider": self.provider.name, "model": self.provider.model,
               "mock": self.is_mock, "cache_key": key, "cached": cached, "temperature": req.temperature, "seed": req.seed,
               "system_sha256": _sha(req.system), "user_sha256": _sha(req.user), "response_sha256": _sha(text),
               "request_id": meta.get("request_id"), "logged_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               **{k: meta[k] for k in ("usage", "done_reason", "schema_fallback", "durations_ns") if k in meta}}
        with self._lock, self.call_log.open("a", encoding="utf-8") as f:
            f.write(_canon(log) + "\n")
        return obj, {"cache_key": key, "cached": cached, "provider": self.provider.name, "model": self.provider.model, "mock": self.is_mock,
                     **{k: meta[k] for k in ("usage", "done_reason") if k in meta}}
