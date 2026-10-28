"""Model client for AP3's agents.

One interface, three providers:

- ``EngineeringMockProvider``: canned responses for engineering tests only. Every call and every
  output produced through it is marked ``engineering_mock``; the shared evaluator refuses to score
  records with that mode, so mock outputs can never become backtest results.
- ``DeepInfraProvider`` and ``BedrockProvider``: Llama 3.1 70B Instruct. Both refuse to run unless
  ``AP3_ALLOW_PAID_INFERENCE=1`` is set and credentials are present, so no paid call can happen
  before approval.

Every response is validated against its JSON schema, cached by the SHA-256 of the full request,
and logged append-only with request and response hashes.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import jsonschema

LLAMA_MODEL_IDS = {
    "bedrock": "meta.llama3-1-70b-instruct-v1:0",
    "deepinfra": "meta-llama/Meta-Llama-3.1-70B-Instruct",
}


class PaidInferenceNotApproved(RuntimeError):
    pass


class ModelOutputError(RuntimeError):
    pass


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
    name = "bedrock"
    model = LLAMA_MODEL_IDS["bedrock"]
    is_mock = False

    def complete(self, req: Request) -> Tuple[str, dict]:
        _require_approval(self.name, ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"))
        import boto3

        client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        resp = client.converse(modelId=self.model, system=[{"text": req.system}],
                               messages=[{"role": "user", "content": [{"text": req.user + "\n\nReturn JSON only."}]}],
                               inferenceConfig={"temperature": req.temperature, "maxTokens": req.max_tokens})
        text = resp["output"]["message"]["content"][0]["text"]
        return text, {"request_id": resp.get("ResponseMetadata", {}).get("RequestId"), "usage": resp.get("usage"),
                      "note": "Bedrock Converse does not accept a seed for Llama; repeated runs rely on the cache for replay"}


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
    def __init__(self, provider, cache_dir: Path, call_log: Path, run_tag: str, max_calls: Optional[int] = None):
        self.provider = provider
        self.cache_dir = Path(cache_dir)
        self.call_log = Path(call_log)
        self.run_tag = run_tag
        self.max_calls = max_calls
        self.calls = 0
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.call_log.parent.mkdir(parents=True, exist_ok=True)

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
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise RuntimeError(f"call budget {self.max_calls} exhausted")
            self.calls += 1
            text, meta = self.provider.complete(req)
            cpath.write_text(_canon({"text": text, "meta": meta, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
        obj = _extract_json(text)
        jsonschema.validate(obj, req.schema)
        log = {"run_tag": self.run_tag, "step": req.step, "provider": self.provider.name, "model": self.provider.model,
               "mock": self.is_mock, "cache_key": key, "cached": cached, "temperature": req.temperature, "seed": req.seed,
               "system_sha256": _sha(req.system), "user_sha256": _sha(req.user), "response_sha256": _sha(text),
               "request_id": meta.get("request_id"), "logged_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with self.call_log.open("a", encoding="utf-8") as f:
            f.write(_canon(log) + "\n")
        return obj, {"cache_key": key, "cached": cached, "provider": self.provider.name, "model": self.provider.model, "mock": self.is_mock}
