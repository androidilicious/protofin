# Native four-system backtest

Shared evaluation of the four executable systems as they exist in their repositories:
AP1 (Stage 2 System A), AP2-A Agent Committee, AP2-B JEV, and AP3 Agentic Causal RAG (being built).
The 2023-01..2026-08 window is sealed: the evaluator refuses to score it without a signed GO record.

## Layout

| Path | Contents |
|---|---|
| `docs/NATIVE_BEHAVIOUR_AUDIT.md` | Step 1 audit: what each system's code actually does, conflicts with the earlier proposal |
| `docs/AP3_MODEL_HOSTING_AND_COST.md` | Hosting options and cost estimate for AP3's Llama 3.1 70B agents (awaiting approval) |
| `framework/` | Shared evaluator: decision-record schema, market data and calendar, protected-window lock, accounting, metrics |
| `adapters/ap1_stage2.py` | AP1 decisions from the unchanged Stage 2 scorer |
| `adapters/ap2_native.py`, `adapters/node/ap2_native_replay.mjs` | AP2 native replay: the unchanged site engine run in Node, plus fidelity checks |
| `adapters/execution_attribution.py` | External adapter: native → common execution, one adjustment at a time |
| `vendor/` | Byte-identical copies of native AP2 code and saved outputs, with `PROVENANCE.json` |
| `config/` | Shared evaluation settings; TLT data manifest |
| `out/` | Decision records, reproduction and development reports (development months only) |

## Reproduce (from the repository root)

```
pip install -r stage2/scoring/requirements-lock.txt
python stage2/scoring/fetch_pinned_inputs.py --manifest stage2/reproducibility/stage2_data_snapshot_manifest_v3_2026-10-27.json
python stage2/scoring/fetch_pinned_inputs.py --manifest native_backtest/config/native_data_manifest_v1.json
python stage2/scoring/stage2_backtest.py --spec stage2/scoring/stage2_run_spec_dev_v4.json --mode development --output-dir native_backtest/out/ap1/stage2_dev_rerun
python -m native_backtest.scripts.build_ap1_decisions
python -m native_backtest.scripts.ap2_native_reproduction
python -m native_backtest.scripts.development_evaluation
python -m pytest -q native_backtest/tests
```

Node 22 is required for the AP2 native engine. No step calls a model or the network except the GitHub fetch of pinned inputs.
