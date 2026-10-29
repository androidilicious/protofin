# First real-model run of Causal RAG (qwen3:4b, Kaggle): diagnosis and fixes — 2026-10-29

**Run.** Kaggle, 2× T4, Ollama 0.40.13, `qwen3:4b` at digest `359d7dd4bcda…`, repository commit `5b22930`, results pushed to `ap3-qwen3-runs` @ `790a049`. Cost $0. Development months only; the protected window was never touched.

**Outcome.** Both pre-registered gates failed, and the replay correctly did not start:
- G3b, Testing Agent fixtures: 53.3% accuracy (needs 80%), with 2 opposite-direction errors (at most 1 allowed).
- G3a, 12 sample months: 12 failed months (at most 1 allowed). There were no point-in-time violations and no accepted fabricated quotes.

The bundle is imported in `native_backtest/out/ap3/qwen3_runs/` as the record of this attempt (protocol 1.0).

## Summary

| Finding | Kind | Effect | Fixed |
|---|---|---|---|
| The Hypothesis Agent never got its final-answer turn: the "give your final answer now" message was added after the last turn | **Pipeline bug** | Every sample month ended "no final answer within the turn limit", whatever the model would have done | Yes |
| The agent's own earlier tool calls were pasted into the user message ("YOUR TOOL CALL: …") instead of being sent back as assistant turns | **Prompt/model integration defect** | At temperature 0 the 4B model copied its previous call: 162 of 180 tool calls were exact repeats | Yes |
| `search_nodes` matched substrings, contrary to its documented whole-word matching | **Pipeline bug** | "PPI" returned "happiness" and "increased shopping effort"; "AHE" returned "…ahead forecast"; `INDUSTRIAL_PRODUCTION` returned nothing | Yes |
| Repeated identical tool calls were re-run silently | Harness gap | Nothing told the model it was repeating itself | Yes (flagged, still counted) |
| `rival_path_id` was never checked against the candidate rivals | **Pipeline bug** | Any string, including "none", created rival edges for the assessor. In G3b there are no candidates, so any named rival was spurious | Yes |
| Testing Agent labels in G3b: 16 of 30 correct | **Model reasoning** (pipeline verified, see below) | Directional fixtures mostly came back Insufficient: supported 3/9, contradicted 1/9 | Not a code fix |
| Runner returned exit code 0 with both gates failed | **Pipeline bug** | The notebook printed "exit code 0" | Yes: 3 on a failed gate |
| A rerun would have reused the failed attempt | **Pipeline bug** | The results-branch bundle and its failed G3a verdict would have been restored and the 12 months skipped | Yes: protocol fingerprint |
| G3b details, raw replies and G3b token use were not saved to the branch | Diagnostics gap | Run 1's per-fixture errors can't be read from the branch | Yes, for future runs |
| GitHub token embedded in a git remote URL under `/kaggle/working` | **Security defect** | `/kaggle/working/ap3_results_branch/.git/config` in that notebook version's saved output contains the token | Yes. **Rotate the token** |

No gate threshold, limit, temperature, seed, fixture, assessor prompt, assessor schema or rubric was changed.

## 1. G3a: why all 12 months failed

**Evidence (saved month records).**
- Each month has 16 turns and 15 tool calls, then "no final answer within the turn limit".
- Only 18 of the 180 calls are distinct. Ten months issued one call 15 times, for example `search_nodes("FOMC")` in 2015-04, 06, 07 and 09, and `search_nodes("PPI")` in 2015-05.
- The 192 model calls in the sample (12 × 16) averaged 5.3k input and 41 output tokens: each reply was a short tool call.
- There were no invalid replies and no schema fallbacks: the model always answered in the required shape.

**Root cause 1: pipeline bug.**
- The loop allows 16 turns with a budget of 15 tool calls. That is meant to be 15 calls plus one final answer, and the system prompt and the budget message say so.
- The model's 16th turn was spent on a 16th tool call, which the budget refused. The refusal message, "tool budget used; give your final answer now", was appended to the transcript, and then the loop ended.
- The model was therefore never asked for its final answer. A stand-in model that answers as soon as it is told the budget is used reproduces the Kaggle record exactly (16 turns, 15 calls, the same failure) under the old code.
- The fix: once the budget is used, or on the last turn, the model gets that turn, and its reply is restricted by schema to the final-answer shape. Whether a final answer was prompted this way is recorded per month (`final_answer_forced`) and in the reliability report (`months_final_answer_forced`). It is reported, not hidden.

**Root cause 2: integration defect.**
- Protocol 1.0 rebuilt one user message each turn, containing the packet, the library and then "YOUR TOOL CALL: {…} TOOL RESULT: […]" for every previous turn.
- A chat model is trained to see its own earlier replies as assistant turns. Shown its own call as user text, at temperature 0, the 4B model reproduced the last JSON object it saw.
- Protocol 1.1 sends each of the model's replies back as an assistant turn, and each tool result as the next user turn. The words of the system prompt, packet, library and tool results are unchanged.
- An identical repeated call now returns "identical to your tool call #n; its result is above…" instead of being re-run. It still counts against the 15-call budget.

**Root cause 3: pipeline bug in node search.**
- `search_nodes` is documented as exact-token matching, but it tested `word in name`, a substring check.
- Measured on the same graph vintages: "PPI" matched 183 concepts, of which 20 contain the word "ppi". The most connected match is "happiness".
- "AHE" (average hourly earnings) matched 52 concepts, none containing the word. "INDUSTRIAL_PRODUCTION" matched nothing, because underscores were not split.
- Search now matches whole words, letters and digits only. Errors for non-concept names explain that trigger codes and tickers are not concepts.

**The model's part.** The 4B model also did not use the results it received. For example, in 2015-04 the FOMC results were relevant, and it still repeated the call. Whether it now produces useful hypotheses is for the rerun to show. G3a counts months that fail; months answered only on the prompted final turn are reported separately.

## 2. G3b: why the Testing Agent scored 16/30

**Evidence.**
- By category: conflict 3/3, injection 3/3, one-node 2/2, theory-only 3/3, unrelated 1/1, supported 3/9, contradicted 1/9.
- So every Insufficient fixture was right, and directional fixtures mostly came back Insufficient. There were 2 opposite-direction errors.
- The real run made 177 calls.

**The pipeline is not the limit.** A deterministic "oracle" model was run through the unchanged G3b pipeline: plan prompt, BM25 retrieval, native assessor validation, rubric, three seeds and majority. The oracle assesses correctly and copies its quotes verbatim.
- It scores **30/30** with **177 calls**, exactly the real run's count. The three calls fewer than 180 come from fixture I04, whose excerpts share no words with any query, so no assessor call is made, by design.
- This shows that retrieval, quote validation, the rubric and the majority rule return every expected status when the model answers correctly.
- The matching call count also indicates that the real run had no invalid replies: an invalid reply ends a fixture early and changes the count.
- The oracle is now a regression test (`test_ap3_run1_fixes.py`).

**What remains is the model's labels and quotes.** The run-1 bundle holds only category totals, so the exact per-fixture failure can't be read from the branch. The possible causes are:
- labelling insufficient_evidence;
- quotes that are not verbatim, which validation downgrades;
- quoting only one excerpt, while Supported needs two valid items under the pre-registered rubric;
- evidence filed on the wrong side.

A small model that must emit the label before its quotes, with thinking off, plausibly does all of these. One pipeline bug could also have contributed: an unchecked rival, now fixed. The fixtures supply no rival candidates, so any rival the model named added spurious "R:" edges to the assessor's task.

**From the next run, every fixture's details are pushed** to `qwen3_runs/diagnostics/g3b_fixtures.json`. The fixtures are synthetic, so nothing is redacted. Each row has:
- the plan;
- the retrieved excerpts;
- each assessor label, quote and citation check;
- the rubric step;
- tokens and stop reason.

For run 1, the same rows exist only in that Kaggle version's output, at `/kaggle/working/protofin/native_backtest/out/ap3/g3b/ollama/summary.json`, with raw replies in `…/g3b/ollama/cache/`.

**Not changed.** The assessor prompt, schema and validation, which are the native causal-rag-mvp component, the rubric, the fixtures and the 80% threshold are all unchanged. The prompts were not tuned on the gate fixtures, because that would make G3b meaningless.

## 3. Exit code 0

`ap3_free_run.main()` returned 0 on the "gate failed" path. `ap3_g3b_fixtures.main()` always returned 0. The notebook printed the code without acting on it.

Now:
- **0** means every requested stage ran and every gate passed.
- **3** means a pre-registered gate failed. Results are still bundled and pushed.
- Anything else is an error.

The notebook's last cell fails visibly unless the code is 0.

## 4. Stale results and protocol versions

`native_backtest/ap3/protocol.py` defines protocol **1.1** and a fingerprint: a hash of the agents' code, prompts and schemas, tools, limits, concepts, variants, fixtures, gates, the vendored assessor and retrieval, and the G3b scorer.
- Every month record, G3b summary and bundle now carries the fingerprint.
- A run never reuses records, a G3b summary or a results-branch bundle with a different fingerprint. A stale local bundle is set aside, and a stale branch bundle is not restored.
- Run 1 has no fingerprint (protocol 1.0). The next run starts again from G3b, and its bundle replaces run 1's on the branch. Run 1 stays in the branch history at `790a049`.

## 5. Credentials

The old runner cloned the results branch with `https://x-access-token:<token>@github.com/…`, which git stores in `.git/config`. That clone sat under `/kaggle/working`, which Kaggle saves as the notebook version's output.
- The runner and the notebook now pass the token through an askpass helper, kept outside the output folder, that holds no secret itself. The remote URL never contains it.
- **Action for the team:** revoke the fine-grained token used in run 1 and create a new one. If that notebook version or its output was shared, delete the version's output.

## 6. What to rerun

Re-run the same Kaggle notebook (**Save Version → Save & Run All**). Its first cell clones the current `backtest`, so it picks up these fixes; no edits are needed.
1. Before running, replace the `GITHUB_TOKEN` secret with a new token.
2. Optionally replace the last two cells with those of `native_backtest/notebooks/ap3_qwen3_free_run.ipynb`, so a failed gate fails the run visibly.

The runner will:
- see that the results branch holds protocol 1.0 results and not reuse them;
- rerun G3b (about 180 calls) and the 12 G3a months;
- start the 95-month replay only if both gates pass.

Every per-fixture and per-turn diagnostic is pushed either way.

**What to expect.**
- **G3a** can now pass if the model gives schema-valid final answers and its hypotheses' tests run.
- **G3b** depends on the model. The pipeline is verified, so if qwen3:4b scores below 80% again, that is a finding about the 4B substitute, and the run-2 diagnostics will show exactly which step fails.

If G3b fails again, the choices belong to the project lead, made before any further run. None changes a threshold. Each is a documented substitution or configuration change, applied to all gates alike:
1. a larger free model on the same T4s, such as `qwen3:8b` or `qwen3:14b`;
2. Qwen3's thinking mode, which means more tokens and slower runs;
3. accepting that Causal RAG stays "awaiting validation".
