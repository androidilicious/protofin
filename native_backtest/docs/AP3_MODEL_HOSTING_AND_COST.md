# AP3 model hosting and cost estimate (for approval) — 2026-10-28

Approved direction: AP3's new agents use **Llama 3.1 70B Instruct** through a hosted provider, subject to cost and access approval. AP2's Agent Committee keeps its native gpt-4o implementation and saved runs; nothing here changes it.

**No paid inference has been run.** Engineering tests use clearly labelled mock responses only.

## Provider options

| Provider | Model ID | Price per 1M tokens (input / output) | Pinning | Network host to allow | Credentials |
|---|---|---|---|---|---|
| **Amazon Bedrock (recommended)** | `meta.llama3-1-70b-instruct-v1:0` | $0.72 / $0.72 (standard tier) | Versioned model ID; AWS publishes model-lifecycle notices before retirement | `bedrock-runtime.us-east-1.amazonaws.com` | IAM access key limited to `bedrock:InvokeModel` on that model; model access enabled in the console (accepts Meta's licence) |
| DeepInfra (cheaper alternative) | `meta-llama/Meta-Llama-3.1-70B-Instruct` (standard, not the FP8 "Turbo" variant) | $0.40 / $0.40 | Model ID only; precision of the standard endpoint not documented | `api.deepinfra.com` | API key |
| Self-hosted (exact weights hash) | Meta's released weights | GPU rental instead of tokens: roughly $250–400 for the whole programme | Exact SHA-256 of the weights | The GPU host, plus `huggingface.co` to download the weights | Hugging Face token with the licence accepted |

Prices are third-party compilations checked on 2026-10-28 ([Artificial Analysis](https://artificialanalysis.ai/models/llama-3-1-instruct-70b/providers), [pricepertoken, updated 2026-07-03](https://pricepertoken.com/pricing-page/model/meta-llama-llama-3.1-70b-instruct), [TypingMind Bedrock calculator](https://custom.typingmind.com/tools/estimate-llm-usage-costs/amazon-bedrock/meta-llama3-1-70b-instruct-v1-0), [DeepInfra](https://deepinfra.com/blog/llama-3-1-70b-instruct-api-from-deepinfra-snappy-starts-fair-pricing-production-fit)). Confirm on the provider's own pricing page before purchase.

**Availability risk.** Artificial Analysis marks Llama 3.1 70B as deprecated, superseded by Llama 3.3 70B. It is still served by Bedrock and DeepInfra, but a provider could retire it. The full historical replay should therefore run soon after approval. Every call logs provider, model ID, region, request ID and timestamp. A fixed canary prompt at temperature 0 is run before each batch to detect a silent backend change.

**What "pinned" means for a hosted model.** A hosted API does not expose the weights hash. The pin is provider + versioned model ID + region + logged responses, plus the canary check. Exact weight pinning requires self-hosting.

## Token budget per decision month (upper bound from the locked AP3 limits)

| Agent | Calls | Input tokens | Output tokens |
|---|---|---|---|
| Hypothesis Agent (1 run, up to 15 graph-tool calls, growing context) | ≤ 16 | ≈ 216,000 | ≈ 6,400 |
| Testing Agent (≤ 6 hypotheses × 3 runs; implications and rival, assessment over 12 chunks and 8 research records, rubric pass) | ≤ 54 | ≈ 360,000 | ≈ 54,000 |
| **Total per month** | ≤ 70 | **≈ 0.58M** | **≈ 0.06M** |

## Cost estimates (upper bounds, before contingency)

| Run | Months | Tokens | Bedrock ($0.72) | DeepInfra ($0.40) |
|---|---|---|---|---|
| Small validation run: 12-month smoke run twice, plus 30 fixtures × 3 runs | 24 + fixtures | ≈ 17M | ≈ $12 | ≈ $7 |
| Full historical programme: development replay 2015-02..2022-12 up to 3 times (3 allowed versions), one run over 2023-01 to the freeze, probes on 24 months | ≈ 285 + 48 + 24 | ≈ 235M | ≈ $170 | ≈ $95 |
| Prospective, per month | 1 | ≈ 0.64M | ≈ $0.46 | ≈ $0.26 |

Recommended spending cap: **$300 on Bedrock** (or $170 on DeepInfra). That covers the full programme with about 75% headroom for retries and longer-than-expected contexts. A budget alarm should be set at 50% and 80%.

## Licensing

- **Llama 3.1 Community License** (Meta): research and commercial use is permitted. Use must follow Meta's Acceptable Use Policy. "Built with Llama" attribution is required if the model or derivatives are distributed. The 700M monthly-active-user clause does not apply.
- On Bedrock, enabling model access in the console accepts the licence for the AWS account.
- Model outputs stored in this repository are research records; no weights are redistributed.

## What is needed from you to start paid inference

1. Choose the provider (Bedrock recommended) and approve the spending cap.
2. Create the credential, and add it to this environment as a secret environment variable rather than pasting it into chat: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-east-1`, or `DEEPINFRA_API_KEY`.
3. Allow the provider host for this environment. On a Team or Enterprise plan an admin does this under Organization settings → Capabilities; on an individual plan, Settings → Capabilities.
