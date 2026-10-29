#!/usr/bin/env python3
"""Dedicated Hugging Face endpoint for AP3 (Llama 3.1 70B Instruct) under a hard spending authorization.

Default is --plan: prints the endpoint configuration, the safeguard deadlines and the worst-case cost of every
failure mode, and contacts nothing. --create/--delete call the Hugging Face API and need the stage-A approval
record and HF_TOKEN as an environment secret. The smoke test (ap3_smoke_test --execute) uses EndpointController
directly, so creation, waiting, inference and deletion run under one controller in one process.

Billing facts (Hugging Face pricing page, checked 2026-10-29): nvidia-h200 x2 on AWS costs $10/hour, charged per
minute while initialising and running. A request sent to a scaled-to-zero endpoint starts a new (billed) replica.
Hugging Face offers no account-side hard cap for dedicated endpoints, so the cap is enforced here.

Safeguards (all measured from the moment just BEFORE the create call, so the clock never starts late):
  1. Configuration check: right after creation the echoed configuration must show the pinned revision, image,
     instance and container arguments; otherwise the endpoint is deleted at once.
  2. Initialisation deadline: not running after `init_deadline_minutes` -> delete.
  3. Failure: status failed / updateFailed -> delete.
  4. No wake-ups: a request is sent only while the controller's last status poll says "running"; the client sends
     no scale-up header, so a paused or scaled-to-zero endpoint is never woken.
  5. Stop new calls at `stop_new_calls_minute`; request timeout `request_timeout_seconds`.
  6. Watchdog deletes at `delete_minute`, even with a request in flight.
  7. The run deletes the endpoint when it finishes, fails or is interrupted (finally block), and verifies deletion.
  8. If this process dies, the endpoint (min replicas 0) scales to zero after 15 minutes without requests.
worst_cases() computes the bound for each failure mode; spec_check() refuses a configuration whose bounds exceed
the authorization.

Usage (repository root):
  python -m native_backtest.scripts.ap3_hf_endpoint            # plan only
  python -m native_backtest.scripts.ap3_hf_endpoint --delete   # delete the recorded endpoint (always allowed with HF_TOKEN)
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "native_backtest/config/ap3_smoke_test_v1.json"
OUT = ROOT / "native_backtest/out/ap3/smoke/hf_endpoint"
STATE = OUT / "endpoint.json"
LOG = OUT / "endpoint_log.jsonl"
RUNNING, FAILED_STATES = "running", ("failed", "updateFailed")


def _cfg() -> dict:
    return json.loads(CONFIG.read_text())


def spec() -> dict:
    return _cfg()["providers"]["hf_endpoint"]["endpoint_spec"]


def safeguards() -> dict:
    return _cfg()["providers"]["hf_endpoint"]["safeguards"]


def approved() -> bool:
    cfg = _cfg()
    p = ROOT / cfg["approval_record"]
    return p.exists() and json.loads(p.read_text()).get("provider") == "hf_endpoint" and bool(os.environ.get("HF_TOKEN"))


def usd(minutes: float, s: Optional[dict] = None) -> float:
    s = s or safeguards()
    return math.ceil(max(0.0, minutes)) * s["usd_per_hour"] / 60.0


def worst_cases(s: Optional[dict] = None) -> Dict[str, dict]:
    """Billable minutes and cost bound for each failure mode (+1 minute for deletion to take effect)."""
    s = s or safeguards()
    req = s["request_timeout_seconds"] / 60.0
    cases = {
        "normal_finish": ("deleted when the run ends", s["stop_new_calls_minute"] + req + 1),
        "controller_alive_cap_reached": ("watchdog deletes at the deadline", s["delete_minute"] + 1),
        "never_starts": ("deleted at the initialisation deadline", s["init_deadline_minutes"] + 1),
        "controller_dies_while_running": ("no new requests; endpoint scales to zero after the idle timeout",
                                          s["stop_new_calls_minute"] + req + s["scale_to_zero_minutes"]),
    }
    out = {k: {"how": h, "max_billable_minutes": math.ceil(m), "max_usd": round(usd(m, s), 2)} for k, (h, m) in cases.items()}
    out["controller_dies_during_initialisation"] = {
        "how": "the endpoint scales to zero 15 minutes after it becomes ready; if Hugging Face kept it initialising "
               "indefinitely this bound would not hold. Backstop: a scheduled check deletes it; the console can delete it",
        "max_billable_minutes": None, "max_usd": None}
    return out


def spec_check(s: Optional[dict] = None) -> None:
    s = s or safeguards()
    bounded = [v["max_usd"] for v in worst_cases(s).values() if v["max_usd"] is not None]
    if max(bounded) > s["authorized_usd"]:
        raise SystemExit(f"safeguards allow up to ${max(bounded):.2f}, above the ${s['authorized_usd']:.2f} authorization")
    if not s["init_deadline_minutes"] < s["stop_new_calls_minute"] < s["delete_minute"]:
        raise SystemExit("deadlines must satisfy init < stop-new-calls < delete")


# ------------------------------------------------------------------ Hugging Face API wrapper (fake in tests)
class HFApiWrapper:
    def __init__(self, token: str):
        from huggingface_hub import HfApi
        self.api = HfApi(token=token)

    def create(self, e: dict) -> dict:
        ep = self.api.create_inference_endpoint(
            e["name"], repository=e["repository"], revision=e["revision"], framework="pytorch", task="text-generation",
            vendor=e["vendor"], region=e["region"], accelerator="gpu", instance_type=e["instance_type"], instance_size=e["instance_size"],
            min_replica=e["min_replica"], max_replica=e["max_replica"], scale_to_zero_timeout=e["scale_to_zero_timeout_minutes"],
            custom_image={"url": e["image"], "health_route": "/health", "port": 8000, "env": e["env"], "args": e["container_args"]},
            env=e["env"], type="protected")
        return {"status": ep.status, "url": ep.url, "raw": ep.raw}

    def get(self, name: str) -> Optional[dict]:
        from huggingface_hub.utils import HfHubHTTPError
        try:
            ep = self.api.get_inference_endpoint(name)
        except HfHubHTTPError as e:
            if getattr(e.response, "status_code", None) == 404:
                return None
            raise
        return {"status": ep.status, "url": ep.url, "raw": ep.raw}

    def delete(self, name: str) -> None:
        self.api.delete_inference_endpoint(name)


def _contains(obj, needle) -> bool:
    if obj == needle:
        return True
    if isinstance(obj, dict):
        return any(_contains(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains(v, needle) for v in obj)
    return False


def config_mismatches(raw: dict, e: dict) -> list:
    """What the echoed endpoint configuration does not show of the pinned spec."""
    miss = []
    for label, needle in (("revision", e["revision"]), ("image", e["image"]), ("instance type", e["instance_type"]),
                          ("instance size", e["instance_size"]), ("container arguments", e["container_args"])):
        if not _contains(raw, needle):
            miss.append(label)
    return miss


class EndpointController:
    def __init__(self, api, name: str, s: Optional[dict] = None, log: Path = LOG, clock: Callable[[], float] = time.time):
        self.api, self.name, self.s, self.log, self.clock = api, name, s or safeguards(), Path(log), clock
        self.t0: Optional[float] = None
        self.status: Optional[str] = None
        self.url: Optional[str] = None
        self.deleted: Optional[dict] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.log.parent.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------- bookkeeping
    def _log(self, event: str, **kw) -> None:
        rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())), "event": event,
               "elapsed_min": round(self.elapsed_min(), 2), **kw}
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def elapsed_min(self) -> float:
        return 0.0 if self.t0 is None else (self.clock() - self.t0) / 60.0

    def cost_usd(self) -> float:
        end = self.deleted["at"] if self.deleted else self.clock()
        return 0.0 if self.t0 is None else usd((end - self.t0) / 60.0, self.s)

    def stop_reason(self) -> Optional[str]:
        """Why no new request may be sent (None = a request may be sent). Used as the CostGuard gate."""
        if self.deleted:
            return f"endpoint deleted ({self.deleted['reason']})"
        if self.elapsed_min() >= self.s["stop_new_calls_minute"]:
            return f"time limit: {self.s['stop_new_calls_minute']} minutes since creation"
        if self.status != RUNNING:
            return f"endpoint status is {self.status!r}, not running (no wake-up requests are sent)"
        return None

    # -------------------------------------------------- lifecycle
    def create(self) -> dict:
        spec_check(self.s)
        e = spec()
        self.t0 = self.clock()                      # before the call: the clock never starts late
        self._log("create_requested", spec={k: e[k] for k in ("name", "repository", "revision", "instance_type", "instance_size", "image")})
        r = self.api.create(e)
        self.status, self.url = r["status"], r["url"]
        state = {"name": self.name, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.t0)), "spec": e}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=1) + "\n")
        miss = config_mismatches(r["raw"], e)
        self._log("created", status=self.status, config_mismatches=miss)
        if miss:
            self.delete(f"configuration not applied as pinned: {', '.join(miss)}")
            raise SystemExit(f"endpoint deleted: the echoed configuration lacks {miss}")
        return state

    def poll_once(self) -> None:
        r = self.api.get(self.name)
        new = None if r is None else r["status"]
        if r is not None and r.get("url"):
            self.url = r["url"]
        if new != self.status:
            self._log("status", status=new)
        self.status = new
        m = self.elapsed_min()
        if r is None and not self.deleted:
            self.deleted = {"at": self.clock(), "reason": "endpoint no longer exists"}
        elif new in FAILED_STATES:
            self.delete(f"endpoint status {new}")
        elif new != RUNNING and m >= self.s["init_deadline_minutes"]:
            self.delete(f"not running after {self.s['init_deadline_minutes']} minutes")
        elif m >= self.s["delete_minute"]:
            self.delete(f"spending deadline: {self.s['delete_minute']} minutes")

    def watch(self) -> None:
        def loop():
            while not self._stop.is_set() and not self.deleted:
                try:
                    self.poll_once()
                except Exception as e:  # keep watching; repeated API errors near a deadline still lead to deletion
                    self._log("poll_error", error=str(e)[:200])
                    if self.elapsed_min() >= self.s["delete_minute"]:
                        self.delete("spending deadline reached during API errors")
                self._stop.wait(self.s["poll_seconds"])
        threading.Thread(target=loop, daemon=True).start()

    def wait_running(self, sleep: Callable[[float], None] = time.sleep) -> str:
        while True:
            if self.deleted:
                raise SystemExit(f"endpoint deleted before it was ready: {self.deleted['reason']}")
            if self.status == RUNNING and self.url:
                self._log("ready", url_host=self.url.split("/")[2] if "://" in self.url else self.url)
                return self.url
            sleep(min(10, self.s["poll_seconds"]))
            self.poll_once()

    def delete(self, reason: str) -> None:
        with self._lock:
            if self.deleted and self.deleted.get("confirmed"):
                return
            at = self.clock()
            try:
                self.api.delete(self.name)
                gone = self.api.get(self.name) is None
            except Exception as e:  # never hide a failed delete: billing would continue
                self._log("delete_failed", reason=reason, error=str(e)[:200])
                print(f"WARNING: could not delete endpoint {self.name} ({e}); delete it in the Hugging Face console now")
                return
            self.deleted = {"at": at, "reason": reason, "confirmed": gone}
            self._stop.set()
            self._log("deleted", reason=reason, confirmed=gone, billed_minutes=math.ceil((at - self.t0) / 60.0) if self.t0 else 0,
                      cost_usd=round(self.cost_usd(), 2))

    def runtime_record(self) -> dict:
        end = self.deleted["at"] if self.deleted else self.clock()
        minutes = 0.0 if self.t0 is None else (end - self.t0) / 60.0
        return {"name": self.name, "created_utc": None if self.t0 is None else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.t0)),
                "deleted": self.deleted, "billable_minutes_upper": math.ceil(minutes), "cost_usd_upper": round(usd(minutes, self.s), 2),
                "rate_usd_per_hour": self.s["usd_per_hour"], "basis": "per-minute billing from just before creation to deletion (an upper bound on the invoice)"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true")
    a = ap.parse_args(argv)
    if not a.delete:
        spec_check()
        print(json.dumps({"endpoint_spec": spec(), "safeguards": safeguards(), "worst_cases": worst_cases(),
                          "will_contact_hugging_face": False}, indent=1))
        return 0
    if not os.environ.get("HF_TOKEN"):
        raise SystemExit("HF_TOKEN is not set")
    name = json.loads(STATE.read_text())["name"] if STATE.exists() else spec()["name"]
    c = EndpointController(HFApiWrapper(os.environ["HF_TOKEN"]), name)
    if STATE.exists():
        c.t0 = calendar.timegm(time.strptime(json.loads(STATE.read_text())["created_utc"], "%Y-%m-%dT%H:%M:%SZ"))
    c.delete("manual delete")
    print(json.dumps(c.runtime_record(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
