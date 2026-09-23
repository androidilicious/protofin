# How a decision is made, step by step

Written for anyone who wants to follow one run from raw prices to a stock/bond split without knowing the model's vocabulary. The numbers are from the run of 22 September 2026; the live page at https://protofin.pages.dev/how.html fills in the same steps from whichever run is selected.

---

## Step 1. Measure the wobble

From the last year of daily prices we measure how much each fund moves and how much they move together.

| Measurement | Value | What it means |
| --- | --- | --- |
| Stocks, yearly variance | 0.01688 | 13.0% volatility, squared |
| Bonds, yearly variance | 0.00841 | 9.2% volatility, squared |
| Co-movement of the two | 0.00312 | slightly positive: they tend to move the same way |

These are measurements, not assumptions.

## Step 2. The rule the optimizer follows

The optimizer holds more of an asset only if the asset pays for the risk it adds. For each asset the rule is:

> expected return over cash = δ × (risk the asset adds to the portfolio)

δ is a fixed number for how much extra return is demanded per unit of risk. It is 2.5 in the current code. It was inherited from textbooks; deriving it from a 3–4% expected premium for 60/40 and today's volatility would give about 4, which would make the allocation calmer. See "The δ question" below.

## Step 3. Work the rule backwards to get the baseline

Instead of feeding the optimizer returns and reading off weights, we decide the answer is 60/40 and ask what returns would make the optimizer agree.

Risk stocks add to a 60/40 portfolio: 0.6 × 0.01688 + 0.4 × 0.00312 = 0.01138. Times δ: **2.84%** over cash.

Risk bonds add: 0.6 × 0.00312 + 0.4 × 0.00841 = 0.00524. Times δ: **1.31%** over cash.

These two numbers are the **baseline**: the returns the market must be expecting if 60/40 is the sensible portfolio. They are not a forecast and not a profit target. Feed them into the optimizer with nothing else and it returns exactly 60/40. The baseline is where the portfolio stays if the committee has nothing new to say.

## Step 4. Ask the committee, and convert its answer to "over cash"

Three model calls. The economist and the risk manager each see the same data and give an independent view with their own numbers; neither sees the other. The CIO reads both, picks sides, and gives the final numbers plus one word of confidence.

The CIO's numbers are total returns. Cash (a 13-week T-bill) pays about 4.0%, so subtract it:

| CIO said | Cash | Over cash | Reading |
| --- | --- | --- | --- |
| Stocks 5.0% | 4.0% | +1.0 | stocks beat a T-bill by one point |
| Bonds 2.5% | 4.0% | −1.5 | bonds earn less than a T-bill: a bearish bond call |

The committee speaks **relative to the baseline**. Above the baseline means "more attractive than the market already assumes"; below means "less attractive". Today the committee was below the baseline on both, and far below on bonds.

## Step 5. Decide how much to trust the committee

Only the CIO states a confidence, defined as how far the evidence justifies moving away from a neutral 60/40 stance, not how strongly anyone argued. The word becomes weights:

| CIO says | Committee's numbers get | Baseline gets |
| --- | --- | --- |
| High | 2/3 | 1/3 |
| Medium | 1/2 | 1/2 |
| Low | 1/3 | 2/3 |

One adjustment first: if the policy-uncertainty or geopolitical-risk index is elevated, the word is moved down one step. It never moves up. Today: Medium, gauges elevated, so **Low** was used and the committee got one-third.

## Step 6. Blend

Weighted average of baseline and committee, per asset:

- Stocks: 2/3 × 2.84 + 1/3 × 1.0 = 1.89 + 0.33 = **2.2**
- Bonds: 2/3 × 1.31 + 1/3 × (−1.5) = 0.87 − 0.50 = **0.4**

The committee pulled bonds down hard and stocks down a little. The gap between stocks and bonds widened from 1.5 to 1.8 points, so stocks now look relatively better than the baseline assumed. If the committee had agreed with the baseline, the blend would equal the baseline and nothing would move.

## Step 7. Turn the blend into a split

The optimizer takes the blended returns and the wobble measurements and tilts away from 60/40 in proportion to the stock-over-bond edge, braked by δ. A 1.8-point edge instead of 1.5 moves the split to about **65% stocks / 35% bonds**. The result is then checked against a hard band of 40–80% stocks; 65 is inside, so it stands. In prototype mode that target is applied directly. With the stability controls on, a 2-point no-trade band and a 10-point move cap are applied against the current holding.

## Step 8. Show and record

The dashboard shows every number above, the flow diagram lights each step, and the run is logged with its prompts and raw replies.

---

## The δ question

δ appears twice: it builds the baseline (step 3) and it brakes the tilt (step 7). Because it is in both, a committee that agrees with the baseline lands on 60/40 whatever δ is; δ only scales the response to *disagreement*. With δ = 2.5 and this year's low volatility, one point of change in the committee's stock-minus-bond view moves the split by roughly 10 weight points at Medium confidence, which is why the backtest weights often sit at the band edges. Backing δ out of a 3–4% expected premium for 60/40 gives about 4, and would halve that sensitivity without adding any rule.

## Glossary in one line each

- **Over cash**: a return minus the T-bill yield. Negative means cash would have been better.
- **Baseline (prior)**: the returns that make 60/40 self-consistent under the optimizer's rule.
- **Confidence**: the CIO's one-word statement of how far the evidence justifies deviating; it sets the blend weights.
- **Regime gate**: elevated uncertainty lowers the confidence one step.
- **δ (delta)**: the price of risk; scales the baseline and brakes the tilt.
- **Band**: the hard 40–80% limit on the stock share.
- **Prior only**: the strategy that uses the baseline with no committee; it isolates what the rules do on their own.
