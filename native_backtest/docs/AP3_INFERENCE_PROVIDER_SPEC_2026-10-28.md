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

## Stage A (smoke test): prepared, not approved

| Item | Setting |
|---|---|
| Cap | **$15 on the endpoint** (about 90 minutes of 2× H200, including start-up), or **$5 on Bedrock**. Enforced by `CostGuard` before every call; the ledger is append-only |
| Steps | 5 fixed canary prompts (temperature 0), then 3 months: 2015-03, 2019-06 and 2020-03, from the hash-pinned inventory-v2 packets |
| Evidence | The official-document corpus is being captured. Until it is imported, the Testing Agent's evidence step returns Insufficient |
| Outputs | `native_backtest/out/ap3/smoke/<provider>/`. Real model outputs only; never scored |
| Pass criteria | All canaries valid. At least 95% of agent replies valid against the schemas. Every cited pathway exists. Spend within the cap. The measured tokens or minutes set the budget for the development replay, which needs its own approval |

**Runner:** `python -m native_backtest.scripts.ap3_smoke_test --provider hf_endpoint`. It plans only. Adding `--execute` requires your approval record (`native_backtest/config/approvals/ap3_inference_approval_A.json`) and `AP3_ALLOW_PAID_INFERENCE=1`.

**What I need from you for the endpoint:**
1. Accept the Llama 3.1 licence on the Hugging Face account.
2. Approve the $15 cap.
3. Either create the endpoint yourself (2× H200, the commit above, a tagged vLLM image), or authorise me to create it with an inference-scoped `HF_TOKEN` added as an environment secret.
4. Allow the endpoint host for this environment.

**For a Bedrock smoke test instead:**
1. Confirm active access.
2. Approve the $5 cap.
3. Confirm that the present AWS credentials may be used, scoped to the IAM policy in `ap3_smoke_test_v1.json`.
