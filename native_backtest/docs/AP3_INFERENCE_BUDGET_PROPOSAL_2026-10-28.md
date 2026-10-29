# Agentic Causal RAG: hosted Llama 3.1 70B inference budget — proposal for approval (2026-10-28)

> **Update (later on 2026-10-28):** Bedrock moved this model to Legacy on 2026-09-30 (end of life 2027-03-30; no access for new customers), and DeepInfra forwards retired models to replacements. Provider choice, endpoints, version guarantees and the $5 stage-A configuration are now in `AP3_INFERENCE_PROVIDER_SPEC_2026-10-28.md`, which supersedes the provider recommendation below. The token estimates are unchanged.

**Request.** Two staged approvals, so no large spend happens before the pipeline is proven on real calls:

| Approval | Stages | Estimate (typical – upper) | Requested cap |
|---|---|---|---|
| **A: smoke test** | Connectivity and canary; 3-month smoke test | Bedrock $0.26 – $1.02 (DeepInfra $0.15 – $0.57) | **$5** |
| **B: development programme** | G3a 12-month smoke run, G3b fixtures, 95-month development replay, one full contingency re-run | Bedrock $18.76 – $72.26 (DeepInfra $10.41 – $40.14) | **$100 on Bedrock** (or $60 on DeepInfra) |

**Recommended provider:** Amazon Bedrock (`meta.llama3-1-70b-instruct-v1:0`). It has a versioned model ID, published model-lifecycle notices and IAM-scoped credentials. At these volumes the difference from DeepInfra is under $35.

Approval B is requested only after A's smoke test. Its estimate will be recalculated with the provider's actual token counts, and you will see the revised figure before any B spend.

**Nothing has been spent.** The model client refuses to call a paid provider unless `AP3_ALLOW_PAID_INFERENCE=1` is set and credentials exist.

## How the estimate was made

- **Measured.** The development-readiness dry run built the real prompts for all 95 months and measured them:
  - Hypothesis Agent: system prompt 1,971 characters; packet plus pathway library median 7,590, p90 11,014, max 15,905 characters.
  - Testing Agent plan: about 2,700 characters.
  - Assessor with 12 evidence chunks: 16,500 characters at the native chunker's typical 170 words a chunk, or 23,300 at its 260-word maximum.
- **Assumed (cannot be measured without the model)**, as two scenarios:

| | Typical | Upper |
|---|---|---|
| Characters per token (Llama 3 tokenizer, English and JSON) | 3.5 | 3.0 |
| Hypothesis Agent turns a month | 6 | 16 (locked maximum) |
| Prompt growth per graph-tool call | 2,000 characters | 6,200 (tool result cap) |
| Hypotheses a month | 4 | 6 (locked maximum) |
| Testing Agent runs per hypothesis | 3 (locked) | 3 |
| Output tokens: plan / assessment / final hypotheses | 600 / 1,000 / 1,500 | 2,000 / 2,000 / 2,000 (caps) |
| Per-call input cap | 16,000 tokens (locked) | 16,000 |

- **Per decision month:** typical 96k input + 21k output tokens in 30 calls; upper 390k + 76k in 52 calls.
- 93 of the 95 months have at least one trigger.

## Stages and costs

Prices are USD per 1M tokens, input and output: Bedrock $0.72 / $0.72; DeepInfra $0.40 / $0.40. These are third-party compilations checked on 2026-10-28; I could not open AWS's own pricing page from here, so confirm on the provider's page before purchase.

| Stage | What | Tokens in / out (typical) | Bedrock typical – upper | DeepInfra typical – upper |
|---|---|---|---|---|
| 1 Connectivity and canary | 5 fixed prompts, temperature 0; checks credentials, model ID, JSON output | 0.01M / 0.003M | $0.01 | $0.01 |
| 2 Smoke test, 3 months | 2015-03 (quiet), 2019-06 (typical), 2020-03 (stressed) | 0.29M / 0.06M | $0.25 – $1.01 | $0.14 – $0.56 |
| 3 G3a 12-month smoke run | Confirms the locked limits before the replay | 1.16M / 0.25M | $1.02 – $4.03 | $0.56 – $2.24 |
| 4 G3b Testing Agent fixtures | 30 labelled fixtures × 3 runs | 0.54M / 0.14M | $0.49 – $0.88 | $0.27 – $0.49 |
| 5 Development replay | 95 months, 2015-02..2022-12 | 8.97M / 1.96M | $7.87 – $31.22 | $4.37 – $17.34 |
| 6 Contingency | One allowed version change: stages 3–5 once more | 10.67M / 2.36M | $9.38 – $36.13 | $5.21 – $20.07 |
| **Total** | | **21.6M / 4.8M** | **$19.02 – $73.28** | **$10.57 – $40.71** |

- **Later, not in this request:**
  - the protected-window run, after GO: about 44 months, ≈ $4–15 on Bedrock;
  - prospective use: ≈ $0.09–0.34 a month on Bedrock.
- **Secondary experiments** (Standard RAG control, ablations) are not included. Each costs about one development replay.

## Controls

- A budget alarm is set at 50% and 80% of each cap, and the client has a hard call budget per stage.
- Every call is logged with provider, model ID, region, request ID, timestamp, and request and response hashes. Responses are cached, so re-runs are free.
- A fixed canary prompt at temperature 0 runs before each batch, to detect a silent backend change.
- **Availability risk.** Llama 3.1 70B has been superseded by Llama 3.3 70B on several providers. Run the replay soon after approval, and confirm the model is still listed before starting.
- **Licence.** Llama 3.1 Community License: research use is permitted. On Bedrock, enabling model access accepts it for the AWS account.

## What is needed from you

1. **Approval A** (cap $5) and the provider choice.
2. **A credential added as an environment secret.** Do not paste it into chat. Bedrock: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-east-1`, scoped to `bedrock:InvokeModel` on that model. DeepInfra: `DEEPINFRA_API_KEY`.
3. **The provider host allowed for this environment:** `bedrock-runtime.us-east-1.amazonaws.com` or `api.deepinfra.com`.

The smoke test's Testing Agent stage is meaningful only once the evidence corpus exists (`AP3_DEV_READINESS_2026-10-28.md`), so the corpus acquisition should be unblocked first or in parallel.
