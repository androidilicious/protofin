# Agentic Causal RAG: inference provider, endpoint, version guarantees and the $5 smoke test (2026-10-28)

**Model: Llama 3.1 70B Instruct (unchanged; it is the preferred model).**
- **Nothing has been spent**, and no paid call is possible until you approve a provider and a cap.
- Machine-readable configuration: `native_backtest/config/ap3_smoke_test_v1.json`.
- Runner: `native_backtest/scripts/ap3_smoke_test.py`. It plans by default; `--execute` needs your approval record.

## What changed since the budget proposal

Amazon Bedrock moved Llama 3.1 70B Instruct to **Legacy on 2026-09-30**, with **end of life on 2027-03-30** ([AWS model lifecycle](https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle-legacy.html); [model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-1-70b-instruct.html)):
- Legacy models **cannot be enabled by new customers**.
- Existing customers keep access until end of life, but **lose it after 15 days of inactivity**.
- A public extended-access period with possibly higher prices is "to be announced".
- Llama 3.3 70B has the same dates.

So Bedrock works only if your AWS account already has active access to this model. Even then, everything must finish by March 2027, and Bedrock cannot serve the live phase.

DeepInfra, the cheaper serverless option in the budget, forwards a retired model's requests to a "recommended replacement" after at least one week's notice ([DeepInfra](https://deepinfra.com/blog/model-deprecation-llm-apps)). That is a silent model swap, so it does not meet the model-version requirement. It is no longer recommended.

## The two acceptable options

| | **A. Amazon Bedrock** | **B. Dedicated Hugging Face endpoint** |
|---|---|---|
| Endpoint | `https://bedrock-runtime.us-west-2.amazonaws.com`, Converse API | `https://<name>.endpoints.huggingface.cloud/v1/chat/completions` (vLLM, OpenAI-compatible) |
| Model | `meta.llama3-1-70b-instruct-v1:0`, in-Region in us-west-2. The `us.` cross-Region profile is not used | `meta-llama/Llama-3.1-70B-Instruct` at one recorded commit (`AP3_MODEL_REVISION`) |
| Version guarantee | Versioned model ID; AWS does not change the model behind an ID. Serving precision is not published | Exact weights (commit), exact engine (pinned vLLM image tag), bfloat16, no quantisation. Unaffected by any provider retiring the model |
| Lifecycle risk | Legacy; end of life 2027-03-30; 15-day inactivity rule | None from the provider; Llama 3.1 Community License accepted on the Hugging Face account |
| Billing | Per token: $0.72 per million in and out (list price before Legacy). The guard counts at $0.99 for safety | Per minute of endpoint time: $5 an hour for 2×A100 80 GB on AWS ([HF pricing](https://huggingface.co/docs/inference-endpoints/en/pricing)) |
| Smoke test within $5 | Yes: estimate $0.26–1.02 | **No.** Start-up (loading about 140 GB) plus three months run one after another is about an hour or more. Needs a $10–15 cap, or the three months run in parallel |
| Development programme (approval B) | $19–73, unchanged estimate | Roughly $25–75, but only with many months running in parallel. A parallel driver is still to be built; run one after another, it would cost several hundred dollars |
| Credentials (environment secrets only) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION=us-west-2`. IAM policy allowing only `bedrock:InvokeModel` on `arn:aws:bedrock:us-west-2::foundation-model/meta.llama3-1-70b-instruct-v1:0` | `HF_TOKEN` (scoped to inference endpoints), `AP3_HF_ENDPOINT_URL`, `AP3_MODEL_REVISION` |
| Network allowlist | `bedrock-runtime.us-west-2.amazonaws.com` | The endpoint's host |

**Recommendation:**
- **Option A for the smoke test and the development programme, if your AWS account still has active access** to `meta.llama3-1-70b-instruct-v1:0` in us-west-2. Run the programme soon after approval to beat the inactivity rule and end of life.
- **Option B if the account has no access**, and in any case **for the live phase**. Moving from A to B counts as a model-serving change: canaries and a sample of months are re-run and compared before B's outputs are used.

**Note:** AWS credentials are already present in this environment. I have not used them for anything, not even a free read-only availability check. That check would also need `bedrock.us-west-2.amazonaws.com` (the management API) to be reachable.

## Stage A configuration (prepared, not approved)

| Item | Setting |
|---|---|
| Cap | $5, enforced by `CostGuard`. Before every call it adds that call's worst-case cost (all input at 3 characters per token, plus the full output allowance; or elapsed endpoint time) and stops if the cap could be passed. The ledger is append-only, so a restart keeps counting |
| Steps | 5 fixed canary prompts at temperature 0, whose response hashes become the reference for detecting a silent backend change. Then 3 months: 2015-03 (quiet), 2019-06 (typical), 2020-03 (stressed), from the inventory-v2 packets (hash-pinned) |
| Call limit | 200 |
| Evidence corpus | Not yet available. The Testing Agent's evidence step returns Insufficient, so this stage tests connectivity, JSON validity, citation discipline and token counts |
| Outputs | `native_backtest/out/ap3/smoke/<provider>/`. Real model outputs only: the runner refuses mock providers, and smoke records are never decision records and are never scored |
| Pass criteria | All canaries valid. At least 95% of agent replies validate against the locked schemas. Every cited pathway exists. Spend within the cap. Measured tokens per month replace the assumptions in the approval-B estimate |

## What I need from you to run stage A

1. **Provider choice** (A or B) and **approval of the cap** ($5 for A; $10–15 if you choose B).
2. **For A:**
   - Confirm the AWS account has active access to the model in us-west-2.
   - Confirm the credentials present here are the ones to use, scoped by the IAM policy above.
   - Allow `bedrock-runtime.us-west-2.amazonaws.com` for this environment.
3. **For B:**
   - Create the endpoint with the pinned commit and vLLM image, or authorise me to create it with your Hugging Face token.
   - Add the three secrets.
   - Allow the endpoint host.

On your approval I write the approval record (`native_backtest/config/approvals/ap3_inference_approval_A.json`), set `AP3_ALLOW_PAID_INFERENCE=1`, and run. The full development replay still needs a separate approval (B), based on the measured smoke-test usage.
