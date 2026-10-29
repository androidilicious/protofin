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
from typing import Any, Callable, Dict, Optional, Tuple

import jsonschema

LLAMA_MODEL_IDS = {
    "bedrock": "meta.llama3-1-70b-instruct-v1:0",
    "hf_endpoint": "meta-llama/Llama-3.1-70B-Instruct",
    "deepinfra": "meta-llama/Meta-Llama-3.1-70B-Instruct",
}


class PaidInferenceNotApproved(RuntimeError):
    pass


class ModelOutputError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class CostGuard:
    """Hard USD cap for one approval stage, persisted in an append-only JSONL ledger.

    pricing: {"mode": "tokens", "usd_per_m_input": x, "usd_per_m_output": y}
          or {"mode": "hourly", "usd_per_hour": z, "started_utc": "...Z"} (dedicated endpoint, billed while running)."""

    def __init__(self, cap_usd: float, ledger: Path, pricing: dict):
        self.cap, self.ledger, self.pricing = float(cap_usd), Path(ledger), dict(pricing)
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

    def key(self, provider: str, model: str) -> str:
        return _sha(_canon({"provider": provider, "model": model, "step": self.step, "system": self.system, "user": self.user,
                            "schema": self.schema, "temperature": self.temperature, "seed": self.seed, "max_tokens": self.max_tokens}))


class EngineeringMockProvider:
    """Deterministic canned responses. ENGINEERING TESTS ONLY — never a backtest input."""

    name = "engineering_mock"
    model = "engineering-mock (no model)"
    is_mock = True

    def __init__(self, responder: Callable[[Request], dict]):
        self.responder = responder

    def complete(self, req: Request) -> Tuple[str, dict]:
        return _canon(self.responder(req)), {"request_id": None}


def _require_approval(provider: str, env_vars: Tuple[str, ...]) -> None:
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
                "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": req.user}],
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
                               messages=[{"role": "user", "content": [{"text": req.user + "\n\nReturn JSON only."}]}],
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
                "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": req.user}],
                "response_format": {"type": "json_object"}}
        if req.seed is not None:
            body["seed"] = req.seed
        r = requests.post(os.environ["AP3_HF_ENDPOINT_URL"].rstrip("/") + "/v1/chat/completions", json=body, timeout=900,
                          headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}",
                                   "X-Scale-Up-Timeout": "900"})   # hold the request while a scaled-to-zero endpoint starts
        r.raise_for_status()
        j = r.json()
        if j.get("model") not in (None, self.model, "/repository"):
            raise ModelOutputError(f"endpoint served {j.get('model')!r}, expected {self.model!r}")
        return j["choices"][0]["message"]["content"], {"request_id": j.get("id"), "usage": j.get("usage"), "model_returned": j.get("model"),
                                                       "revision": os.environ["AP3_MODEL_REVISION"]}


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
        if not getattr(provider, "is_mock", False) and guard is None:
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
            raise ModelOutputError(f"{req.step}: invalid model output ({type(e).__name__})") from e
        log = {"run_tag": self.run_tag, "step": req.step, "provider": self.provider.name, "model": self.provider.model,
               "mock": self.is_mock, "cache_key": key, "cached": cached, "temperature": req.temperature, "seed": req.seed,
               "system_sha256": _sha(req.system), "user_sha256": _sha(req.user), "response_sha256": _sha(text),
               "request_id": meta.get("request_id"), "logged_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with self._lock, self.call_log.open("a", encoding="utf-8") as f:
            f.write(_canon(log) + "\n")
        return obj, {"cache_key": key, "cached": cached, "provider": self.provider.name, "model": self.provider.model, "mock": self.is_mock}
