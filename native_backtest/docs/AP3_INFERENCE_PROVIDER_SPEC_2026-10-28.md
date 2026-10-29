# Agentic Causal RAG: Llama 3.1 70B Instruct provider recommendation (verified 2026-10-28)

**Model: Llama 3.1 70B Instruct.** Unchanged; it is the preferred model.
- **Nothing has been spent.** No paid call is possible until you approve a provider and a cap.
- **The AWS credentials in this environment have not been used**, not even for an availability check.
- **Sources:** official provider documentation, read on 2026-10-28.

## Where the model can still run

| Option | Status | Endpoint / model | Price | Pinning and reproducibility |
|---|---|---|---|---|
| **Hugging Face dedicated endpoint** (recommended) | Available: weights published, gated (manual licence acceptance), BF16, 70.55 B parameters ([model API](https://huggingface.co/api/models/meta-llama/Llama-3.1-70B-Instruct)) | `https://<name>.endpoints.huggingface.cloud/v1/chat/completions`, OpenAI-compatible vLLM, repository `meta-llama/Llama-3.1-70B-Instruct` | AWS 2× H200 (282 GB) **$10 an hour**. 2× A100 (160 GB) $5 an hour (tight for 141 GB of weights). 4× L40S $8.3 an hour. Billed per minute, including start-up ([pricing](https://huggingface.co/docs/inference-endpoints/pricing)) | See below |
| **Amazon Bedrock** | **Legacy since 2026-09-30, end of life 2027-03-30**. New customers can't enable it. Existing customers may lose access after 15 days of inactivity. Extended-access pricing is "to be announced" ([lifecycle](https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle-legacy.html), [model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-1-70b-instruct.html)) | `meta.llama3-1-70b-instruct-v1:0`, in-Region only in us-west-2, Converse API | $0.72 per million input and output tokens (third-party listings; AWS's pricing page showed no figure). The guard counts at $0.99 | Versioned model ID. **No seed** ([Converse parameters](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InferenceConfiguration.html)). Serving precision not published |
| Excluded | Together (removed 2026-02-25), Groq (shut down 2025-01-24) and Oracle (retired 2025) no longer serve it. Google Vertex and Azure no longer list it. DeepInfra's Turbo version is deprecated on 2026-11-03, and DeepInfra forwards retired models to a replacement, a silent model swap. OpenRouter can't fix the upstream provider or precision. Featherless serves FP8 | — | — | Not acceptable for a pinned backtest |

**The dedicated endpoint's pinning:**
- **Weights:** commit `1605565b47bb9346c5515c34102e054115b4f98b`, last modified 2024-12-15. Set through the endpoint's Commit Revision setting ([configuration](https://huggingface.co/docs/inference-endpoints/guides/configuration)).
- **Engine:** a tagged vLLM OpenAI image, never `latest`.
- **Precision:** bfloat16, no quantisation.
- **Determinism:** fixed seed and batch invariance on.
- **Hardware:** fixed.

vLLM is reproducible only on the same hardware and vLLM version ([vLLM reproducibility](https://docs.vllm.ai/en/stable/usage/reproducibility/)), so all four are recorded and kept for every run. Every response is also cached by request hash, so any replay is exact.

## Recommendation

**Use the dedicated Hugging Face endpoint as the single serving stack** for the smoke test, the 95-month development replay, the historical test and the live phase. It is the only option that:
- stays pinned beyond March 2027;
- accepts a seed;
- cannot be swapped silently.

**Bedrock is acceptable only for the smoke test.** It is the cheapest test (about $0.26–1.02), but only if your account already has active access in us-west-2; you can check under Bedrock → Model access. Its end of life and inactivity rule rule it out for the full programme. Moving from Bedrock to the endpoint would count as a serving change: the canaries and a sample of months would be re-run and compared.

**Remaining limitations:**
- The endpoint's start-up time is billed.
- A future vLLM or hardware change would need a documented re-validation.
- Llama 3.1's training data runs to December 2023, which is recorded in the contamination register. This is why 2023 is a secondary period.

## Smoke test on the dedicated endpoint: the details for approval

Nothing below has been run, and no endpoint exists.

**Endpoint** (`ap3_smoke_test_v1.json` → `endpoint_spec`; created only by `ap3_hf_endpoint --create` after approval):

| Item | Value |
|---|---|
| Model | `meta-llama/Llama-3.1-70B-Instruct`, revision `1605565b47bb9346c5515c34102e054115b4f98b`, BF16 |
| Hardware | AWS us-east-1, `nvidia-h200` ×2 (282 GB), **$10 an hour, billed per minute including start-up** |
| Engine | `vllm/vllm-openai:v0.30.0`, pinned by digest `sha256:8a69ffad…4a90`. Arguments: `--model /repository --served-model-name meta-llama/Llama-3.1-70B-Instruct --dtype bfloat16 --tensor-parallel-size 2 --max-model-len 32768 --seed 0`. Environment: `VLLM_BATCH_INVARIANT=1` |
| Replicas | Minimum 0, maximum 1; scales to zero after 15 minutes idle |
| To confirm in the console at creation | That the container arguments apply to the custom image, that the digest matches, and the instance and region |

**Expected time and cost.**
- Hugging Face publishes no start-up time. I estimate 15–30 minutes to load 141 GB of weights.
- Generation speed is an assumption: 15–25 tokens per second per stream with batch invariance on.
- The three months run concurrently.

| | Tokens (in / out) | Minutes | Cost |
|---|---|---|---|
| Smoke test, typical | 299k / 66k | 35–60 | **$6–10** |
| Smoke test, upper | 1.18M / 231k | 80–130 | $13–22, so the $15 cap stops it early but the measured speed is kept |
| Development programme, separate approval B (12-month G3a run, G3b fixtures, 95-month replay, 8 months concurrently) | 10.7M / 2.36M typical; 41.8M / 8.37M upper | — | **$40–75 typical, up to about $190 upper**. Re-estimated from the smoke test's measured speed before I ask |

**Safeguards (all automatic):**
1. **Billing starts at creation.** The cost guard counts every minute from the moment the endpoint is created, start-up included.
2. **Before each call**, the guard checks that elapsed time × $10 an hour stays within the cap, and stops otherwise.
3. **When the run ends** (finished, failed or capped), the runner pauses the endpoint. A watchdog thread also pauses it at the cap, even if a request hangs. Any failure to pause is printed as a warning, so it can be stopped by hand.
4. **Idle backstop.** The endpoint scales to zero after 15 minutes without requests.
5. **Outputs are real model results only.** They are never scored and never mixed with demo responses.

**To approve:**
1. Approve the $15 smoke-test cap.
2. Accept the Llama 3.1 licence on the Hugging Face account.
3. Add an inference-scoped `HF_TOKEN` as an environment secret.
4. Allow `*.endpoints.huggingface.cloud` and `api.endpoints.huggingface.cloud` for this environment.

I then write the approval record, create the endpoint, run the smoke test and pause the endpoint.

**Bedrock alternative:** $5 cap, per token, about $0.26–1.02. Only possible if your account still has access, and the present AWS credentials remain unused until you say so.
