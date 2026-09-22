"""Build site/data/signals.json for the static site (run by the GitHub Action, or locally).

    python scripts/build_signals.py            # signals only
    python scripts/build_signals.py --reference # also run the committee once with OPENAI_API_KEY
                                                # so visitors without a key can replay a real run

The reference run uses the same prompt the browser will send, so keyless visitors see a genuine
decision rather than a mock.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

import signals  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "site", "data", "signals.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", action="store_true", help="also store one real committee reply")
    ap.add_argument("--model", default=os.getenv("LLM_MODEL", "gpt-4o"))
    args = ap.parse_args()
    load_dotenv(os.path.join(BASE, ".env"))

    sig = signals.collect(headlines=True, headlines_in_decision=False, model_name=args.model,
                          log=lambda *a: print("warning:", a[0] % a[1:]))
    sig["reference_run"] = None
    key = os.getenv("OPENAI_API_KEY")
    if args.reference and key and key != "YOUR_API_KEY_HERE":
        from openai import OpenAI
        import committee
        client = OpenAI(api_key=key)

        def _call(prompt_text):
            r = client.chat.completions.create(model=args.model, messages=[{"role": "user", "content": prompt_text}],
                                               temperature=0.0, seed=42, max_tokens=400)
            return r.choices[0].message.content or ""
        com = committee.run_committee(sig["prompts"], _call, parallel=True)
        sig["reference_run"] = {"model": args.model, "generated_at": sig["generated_at"], "parallel": True,
                                "economist_raw": com["economist_raw"], "risk_raw": com["risk_raw"],
                                "cio_raw": com["cio_raw"], "cio_prompt": com["cio_prompt"], "timings": com["timings"],
                                "raw": com["cio_raw"]}   # 'raw' kept for older page code
        print(f"reference run stored (economist {com['timings']['economist_ms']} ms || risk {com['timings']['risk_ms']} ms "
              f"-> CIO {com['timings']['cio_ms']} ms; parse problems: {com['problems'] or 'none'})")
    elif args.reference:
        # keep the last stored reference so keyless visitors still get a real committee reply
        try:
            with open(OUT, encoding="utf-8") as fh:
                sig["reference_run"] = json.load(fh).get("reference_run")
            print("no OPENAI_API_KEY: previous reference run kept")
        except (OSError, ValueError):
            print("no OPENAI_API_KEY and no previous reference run")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(sig, fh, indent=1)
    print(f"signals -> {OUT} (as of {sig['as_of']}, regime {sig['uncertainty_regime']}, "
          f"FOMC {(sig['news']['fomc'] or {}).get('score')})")

    # Saved-runs archive: one file per build that carries a real committee reply, plus an index.
    if sig["reference_run"]:
        runs_dir = os.path.join(BASE, "site", "data", "runs")
        os.makedirs(runs_dir, exist_ok=True)
        run_id = sig["generated_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
        with open(os.path.join(runs_dir, f"{run_id}.json"), "w", encoding="utf-8") as fh:
            json.dump(sig, fh, indent=1)
        index_path = os.path.join(runs_dir, "index.json")
        try:
            index = json.load(open(index_path, encoding="utf-8"))
        except (OSError, ValueError):
            index = []
        index = [r for r in index if r["id"] != run_id]
        index.append({"id": run_id, "as_of": sig["as_of"], "generated_at": sig["generated_at"],
                      "model": sig["reference_run"]["model"], "regime": sig["uncertainty_regime"],
                      "fomc": (sig["news"]["fomc"] or {}).get("score")})
        index.sort(key=lambda r: r["generated_at"], reverse=True)
        with open(index_path, "w", encoding="utf-8") as fh:
            json.dump(index[:60], fh, indent=1)
        print(f"saved run {run_id} ({len(index)} in archive)")


if __name__ == "__main__":
    main()
