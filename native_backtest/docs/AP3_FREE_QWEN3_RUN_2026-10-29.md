# Agentic Causal RAG on a free GPU: qwen3:4b (documented model substitution) — 2026-10-29

The project's additional budget is **$0** (`config/budget_v1.json`). The paid Hugging Face plan is withdrawn: its approval record is marked withdrawn, and every paid provider refuses before any request. No endpoint was ever created and nothing was billed.

## Model substitution

| | Planned | Used |
|---|---|---|
| Model | Llama 3.1 70B Instruct (BF16) | **qwen3:4b**: Qwen3 4B, 4.02B parameters, Q4_K_M quantization, Apache-2.0 licence |
| Why | Originally specified | Free and runs on one free GPU. It is the model the original CauseTrace project uses through Ollama (`causetrace/config.py`) |
| Pinning | Hugging Face commit | Ollama library digest `359d7dd4bcda` (ollama.com/library/qwen3:4b, checked 2026-10-29). The run refuses any other digest and records the full digest and the Ollama version |
| Serving | vLLM on a paid endpoint | Ollama on the notebook's own GPU(s). The client accepts only `localhost`, so it can never reach a paid service |

**What stays identical:**
- the Causal RAG architecture (knowledge graph → Hypothesis Agent → CauseTrace → Testing Agent → status features → calibration → Black–Litterman);
- the year-filtered graph vintages;
- the point-in-time evidence pool (Reduced Evidence);
- every prompt, schema and limit (`limits_v1.json`);
- seeds and temperatures;
- verbatim-quote validation and the rubric;
- the pre-registered reliability gates (thresholds not relaxed);
- the walk-forward calibration and the shared evaluation.

**What differs, and how it is handled:**
- **Model size.** A 4B model is far smaller than 70B. Weaker hypotheses and more Insufficient or failed tests are expected. The gates decide whether the outputs are usable; if a gate fails, the replay does not start.
- **JSON output.** Replies are constrained to each step's JSON schema by the server's grammar-based structured output. If the server cannot compile a schema, it falls back to plain JSON mode, and every such call is flagged `schema_fallback`. Qwen3's thinking mode is switched off, so replies are the JSON object only.
- **Context.** 32,768 tokens, Qwen3-4B's native window. A prompt that would not fit is refused as a failure, never silently truncated. The server's own token count is checked after every call.
- **Determinism.** Seeds and temperatures are fixed. Concurrent requests on one server can still change replies slightly, which is recorded as a known limitation. Every reply is cached and hashed, so the recorded run replays exactly.

The results are those of the 4B substitute. They are labelled as such everywhere and are not a reproduction of the planned 70B system.

## Workflow (free, checkpointed, no personal computer needed)

The notebook is `native_backtest/notebooks/ap3_qwen3_free_run.ipynb`. It is meant for Kaggle; Colab Free also works but needs its tab kept open.

1. **Environment.** Clones `backtest`, installs the agent dependencies, starts one Ollama server per GPU (2 concurrent requests each, 8-bit KV cache), pulls `qwen3:4b` and verifies the digest. It then fetches the pinned inputs and builds the year-filtered graph libraries.
2. **Run.** `python -m native_backtest.scripts.ap3_free_run --stage all --hours 11 --push`:
   - `check`: GPU, servers, digest, inputs;
   - `g3b`: the 30 labelled Testing Agent fixtures;
   - `sample`: the 12 pre-registered G3a months, 2015-02..2016-01;
   - `replay`: **only if G3b and G3a pass**, 2016-02..2022-12, oldest first, in batches of 12, until the time budget.
3. **Checkpoints.** Each month's record is written as soon as it exists, and every model reply is cached. After each batch a **redacted bundle** is committed to the results-only branch `ap3-qwen3-runs`. The bundle holds per-month evidence summaries without claims-data text, status features, record hashes, gates, token counts and provenance. Running the notebook again continues from that branch and skips finished months.
4. **Import, evaluation and dashboard (pinned environment):**
   - `python -m native_backtest.scripts.ap3_free_import` validates the bundle. It accepts genuine outputs of the pinned model only, and development months only; the protected window is refused.
   - Once all 95 months exist and the gates passed, it runs calibration, the G4c checks, allocation, decision records and the shared evaluation against the Deterministic baseline and JEV on 2019-03..2022-12.
   - `python mvp/build_dashboard_data.py` then refreshes the dashboard.

## Expected resources (estimates; the first run measures them)

Kaggle offers T4 or P100 GPUs, 12-hour sessions and about 30 GPU-hours a week (no published quota). The inference budget measured about 96k input and 21k output tokens per month (typical) and 390k input and 76k output (upper). Assuming roughly 40 output tokens per second per stream and 4 streams on 2× T4:
- the sample plus G3b take about 1–2 hours;
- the full replay takes about 4 hours typical and 15 hours upper, so one or two sessions.

Cost: $0.

## Status

**Run 1 (2026-10-29, Kaggle 2× T4, results branch `ap3-qwen3-runs` @ `790a049`): both gates failed, so the replay did not start.**
- G3b: 53% fixture accuracy, against 80% needed.
- G3a: 12 of 12 sample months had no final answer.

The diagnosis is in `AP3_QWEN3_RUN1_DIAGNOSIS_2026-10-29.md`:
- **Pipeline defects:** the agent never got its final-answer turn; its own tool calls were pasted into the user message, which a small model copies; node search matched substrings; rival IDs were not checked; the runner exited 0; a rerun would have reused the failed attempt; the token was stored in a git URL in the saved output.
- **Fixed in protocol 1.1.** Thresholds, limits, prompts' wording, the assessor and the fixtures are unchanged.
- **G3b's pipeline is verified** by an oracle (30/30, the same 177 calls), so its errors are the model's.
- **Next step:** re-run the notebook with a new token. It starts again from G3b, because results from protocol 1.0 are never reused.

Implemented and tested:
- the provider, the runner, the notebook and the import;
- 6 tests for this path, using a fake local server for wiring only;
- the 53 AP3 tests also pass on Python 3.11 with current libraries (the Kaggle setting).

This development environment cannot reach Kaggle, Hugging Face or the Ollama registry, and has no GPU, so the genuine run is done by a team member with the steps below.

**Exit code** (shown by the run cell, and enforced by the last cell):
- **0:** every requested stage ran and every gate passed.
- **3:** a pre-registered gate failed. Results and diagnostics are still pushed.
- **Other:** an error.

## What a team member does (about 10 minutes, free)

1. **Kaggle account.** Create one and verify a phone number, which is needed for GPUs and internet.
2. **GitHub token.** Create a fine-grained token for `androidilicious/protofin` with *Contents: read and write*. Add it in Kaggle under **Add-ons → Secrets** as `GITHUB_TOKEN`.
3. **Notebook.** Download `native_backtest/notebooks/ap3_qwen3_free_run.ipynb` from GitHub (the repository is private, so Kaggle cannot import it by link) and upload it in Kaggle with **File → Import Notebook**. Attach the secret, and set Accelerator to **GPU T4 x2** and Internet to **on**.
4. **Run.** Choose **Save Version → Save & Run All**. It runs in the background. If the replay is not finished after 12 hours, do the same again.
5. **Hand back.** Tell Claude the run finished. Claude imports from branch `ap3-qwen3-runs` and updates the dashboard; nothing needs to be downloaded or attached.
