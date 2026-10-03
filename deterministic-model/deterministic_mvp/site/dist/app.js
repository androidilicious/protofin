const D = window.MVP_DATA;

const names = {
  nfp: "Nonfarm Payrolls", retail_sales: "Retail Sales", industrial_production: "Industrial Production",
  ism_manufacturing: "ISM Manufacturing", cpi: "CPI", core_cpi: "Core CPI", ppi: "PPI", ahe: "Avg. Hourly Earnings",
  equity: "Equity", treasury: "Treasury", ig_credit: "IG Credit"
};
const colors = { equity: "#27b6c7", treasury: "#4f76d9", ig_credit: "#8e64c5" };
const pct = (x, d = 2) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}%`;
const sigma = x => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(2)}σ`;
const plainPct = (x, d = 2) => `${(x * 100).toFixed(d)}%`;

function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }
const formatDecisionDate = date => new Date(`${date}T12:00:00`).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
const formatMonth = date => new Date(`${date}T12:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" });
let activeDecision = D.decisionHistory.at(-1);
let currentReleases = activeDecision.releases;
let blMode = "ridge";

function hydrateHeadline(decision = activeDecision) {
  const s = decision.signal, w = decision.weights;
  setText("latestDate", formatDecisionDate(decision.date));
  setText("heroGrowth", sigma(s.growth_surprise));
  setText("heroInflation", sigma(s.inflation_surprise));
  const stateText = value => `${Math.abs(value) < .25 ? "Modestly" : Math.abs(value) < .75 ? "Clearly" : "Sharply"} ${value >= 0 ? "above" : "below"} consensus`;
  setText("heroGrowthText", stateText(s.growth_surprise));
  setText("heroInflationText", stateText(s.inflation_surprise));
  setText("releaseStatus", `${decision.releases.length} / 8 releases observed`);
  setText("heroEquity", `${Math.round(w.equity * 100)}%`);
  setText("heroTreasury", `${Math.round(w.treasury * 100)}%`);
  setText("heroCredit", `${Math.round(w.ig_credit * 100)}%`);
  setText("compositeGrowth", sigma(s.growth_surprise));
  setText("compositeInflation", sigma(s.inflation_surprise));
  document.getElementById("growthFill").style.width = `${Math.min(100, Math.abs(s.growth_surprise) / 1.5 * 100)}%`;
  document.getElementById("inflationFill").style.width = `${Math.min(100, Math.abs(s.inflation_surprise) / 1.5 * 100)}%`;
}

function buildCalculator() {
  const select = document.getElementById("releaseSelect");
  const inputs = ["actualInput", "consensusInput", "sigmaInput"].map(id => document.getElementById(id));
  function choose() {
    const r = currentReleases[Number(select.value)];
    if (!r) return;
    inputs[0].value = r.actual; inputs[1].value = r.consensus; inputs[2].value = r.sigma;
    inputs.forEach(input => input.dataset.group = r.group);
    calculate();
  }
  function calculate() {
    const actual = Number(inputs[0].value), consensus = Number(inputs[1].value), volatility = Number(inputs[2].value);
    const raw = actual - consensus, z = volatility > 0 ? raw / volatility : 0;
    setText("actualFormula", actual.toLocaleString()); setText("consensusFormula", consensus.toLocaleString());
    setText("rawResult", raw.toLocaleString(undefined, { maximumFractionDigits: 2 })); setText("rawFormula", raw.toLocaleString(undefined, { maximumFractionDigits: 2 }));
    setText("sigmaFormula", volatility.toLocaleString(undefined, { maximumFractionDigits: 2 })); setText("zResult", sigma(z));
    const marker = document.getElementById("scaleMarker"); marker.style.left = `${Math.max(2, Math.min(98, 50 + z / 4 * 50))}%`;
    const magnitude = Math.abs(z) < .25 ? "small" : Math.abs(z) < .75 ? "moderate" : "large";
    const direction = z >= 0 ? "positive" : "negative";
    setText("signalInterpretation", `A ${magnitude} ${direction} ${inputs[0].dataset.group === "growth" ? "Growth" : "Inflation"} surprise.`);
  }
  select.addEventListener("change", choose); inputs.forEach(input => input.addEventListener("input", calculate)); choose();
  window.loadCalculatorMonth = releases => {
    currentReleases = releases;
    select.innerHTML = "";
    currentReleases.forEach((r, i) => {
      const option = document.createElement("option"); option.value = i; option.textContent = names[r.variable]; select.appendChild(option);
    });
    choose();
  };
  window.loadCalculatorMonth(currentReleases);
}

function buildComponentBars(decision = activeDecision) {
  const root = document.getElementById("componentBars");
  root.innerHTML = "";
  const fields = ["nfp", "retail_sales", "industrial_production", "ism_manufacturing", "cpi", "core_cpi", "ppi", "ahe"];
  fields.forEach((field, i) => {
    const value = decision.signal[field], group = i < 4 ? "growth" : "inflation";
    const row = document.createElement("div"); row.className = "component-row";
    const left = value < 0 ? 50 - Math.min(50, Math.abs(value) / 1.5 * 50) : 50;
    const width = Math.max(.3, Math.min(50, Math.abs(value) / 1.5 * 50));
    row.innerHTML = `<span class="name">${names[field]}</span><div class="bar-track"><i class="bar-value ${group}" style="left:${left}%;width:${width}%"></i></div><b>${sigma(value)}</b>`;
    root.appendChild(row);
  });
}

function linePath(values, x, y) { return values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" "); }
function buildLineChart(svg, series, opts = {}) {
  const W = 1000, H = 300, pad = { l: 54, r: 18, t: 20, b: 38 };
  const all = series.flatMap(s => s.values).filter(Number.isFinite);
  let min = opts.min ?? Math.min(...all), max = opts.max ?? Math.max(...all);
  if (min === max) { min -= 1; max += 1; }
  const extra = (max - min) * .12; min -= extra; max += extra;
  const length = series[0].values.length;
  const x = i => pad.l + i / Math.max(1, length - 1) * (W - pad.l - pad.r);
  const y = v => pad.t + (max - v) / (max - min) * (H - pad.t - pad.b);
  const parts = [];
  for (let i = 0; i <= 4; i++) {
    const val = min + (max - min) * i / 4, yy = y(val);
    parts.push(`<line class="chart-grid" x1="${pad.l}" x2="${W-pad.r}" y1="${yy}" y2="${yy}"/><text class="chart-label" x="4" y="${yy+4}">${opts.percent ? `${(val*100).toFixed(0)}%` : val.toFixed(1)}</text>`);
  }
  if (min < 0 && max > 0) parts.push(`<line class="chart-zero" x1="${pad.l}" x2="${W-pad.r}" y1="${y(0)}" y2="${y(0)}"/>`);
  series.forEach(s => parts.push(`<path d="${linePath(s.values, x, y)}" fill="none" stroke="${s.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`));
  const labels = opts.labels || [];
  [0, Math.floor((length-1)/2), length-1].forEach(i => parts.push(`<text class="chart-label" x="${x(i)}" y="${H-7}" text-anchor="${i===0?"start":i===length-1?"end":"middle"}">${labels[i] || ""}</text>`));
  svg.innerHTML = parts.join("");
}

function buildSignalChart() {
  const rows = D.surpriseSignals.filter(r => Number.isFinite(r.growth_surprise) && Number.isFinite(r.inflation_surprise));
  buildLineChart(document.getElementById("signalChart"), [
    { values: rows.map(r => r.growth_surprise), color: "#27b6c7" },
    { values: rows.map(r => r.inflation_surprise), color: "#efad3f" }
  ], { labels: rows.map(r => r.date.slice(0,7)) });
}

function buildForecasts(decision = activeDecision) {
  const root = document.getElementById("forecastRows");
  root.innerHTML = "";
  Object.entries(decision.forecasts).forEach(([asset, value]) => {
    const row = document.createElement("div"); row.className = "forecast-row";
    row.innerHTML = `<span>${names[asset]}</span><b>${pct(value, 2)}</b><small>Expected next-month total return</small>`; root.appendChild(row);
  });
  setText("forecastDecisionLabel", `${new Date(`${decision.date}T12:00:00`).toLocaleDateString("en-US", {month:"short", day:"numeric"})} decision`);
  const penalties = [...new Set(Object.values(decision.forecastAlpha))];
  setText("ridgePenaltyNote", `Expanding-window Ridge used only earlier observations. Selected penalty α = ${penalties.join(" / ")}.`);
}

function buildDonut(decision = activeDecision) {
  const svg = document.getElementById("allocationDonut"), legend = document.getElementById("allocationLegend");
  legend.innerHTML = "";
  let offset = 0; const radius = 82, circumference = 2 * Math.PI * radius;
  svg.innerHTML = `<circle cx="110" cy="110" r="${radius}" fill="none" stroke="#e6eaf0" stroke-width="24"/>`;
  Object.entries(decision.weights).forEach(([asset, weight]) => {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", 110); circle.setAttribute("cy", 110); circle.setAttribute("r", radius); circle.setAttribute("fill", "none"); circle.setAttribute("stroke", colors[asset]); circle.setAttribute("stroke-width", 24); circle.setAttribute("transform", "rotate(-90 110 110)"); circle.setAttribute("stroke-dasharray", `${weight*circumference} ${circumference}`); circle.setAttribute("stroke-dashoffset", `${-offset*circumference}`); svg.appendChild(circle); offset += weight;
    legend.insertAdjacentHTML("beforeend", `<div><i style="background:${colors[asset]}"></i>${names[asset]} <b>${Math.round(weight*100)}%</b></div>`);
  });
}

function buildMetrics() {
  const root = document.getElementById("metricRows");
  D.forecastMetrics.forEach(row => {
    root.insertAdjacentHTML("beforeend", `<div class="metric-row"><div class="metric-head"><span>${names[row.asset]}</span><b>${plainPct(row.directional_accuracy, 0)} direction</b></div><div class="metric-bar"><i style="width:${row.directional_accuracy*100}%"></i></div><div class="metric-rmse">RMSE ${plainPct(row.rmse, 2)}</div></div>`);
  });
}

function buildPerformance() {
  let mvp = 1, benchmark = 1; const dates = [], mvpValues = [], benchmarkValues = [];
  D.backtest.filter(r => Number.isFinite(r.net_return)).forEach(r => { mvp *= 1+r.net_return; benchmark *= 1+r.benchmark_return; dates.push(r.date.slice(0,7)); mvpValues.push(mvp-1); benchmarkValues.push(benchmark-1); });
  buildLineChart(document.getElementById("performanceChart"), [
    { values: mvpValues, color: "#27b6c7" }, { values: benchmarkValues, color: "#8791a2" }
  ], { labels: dates, percent: true });
  const p = D.portfolioMetrics;
  setText("annualReturn", plainPct(p.annualized_return)); setText("benchmarkReturn", `Benchmark ${plainPct(p.benchmark_annualized_return)}`);
  setText("sharpe", p.sharpe_zero_rf.toFixed(2)); setText("benchmarkSharpe", `Benchmark ${p.benchmark_sharpe_zero_rf.toFixed(2)}`);
  setText("drawdown", pct(p.maximum_drawdown)); setText("benchmarkDrawdown", `Benchmark ${pct(p.benchmark_maximum_drawdown)}`);
  setText("turnover", plainPct(p.average_turnover));
}

function buildBlackLitterman() {
  const root = document.getElementById("blComparison");
  const ridgeButton = document.getElementById("ridgeViewButton");
  const posteriorButton = document.getElementById("posteriorViewButton");
  function render(mode) {
    blMode = mode;
    const values = mode === "ridge" ? activeDecision.forecasts : activeDecision.posteriorReturns;
    root.innerHTML = "";
    Object.entries(values).forEach(([asset, value]) => {
      const extent = .008, left = value < 0 ? 50 - Math.min(50, Math.abs(value) / extent * 50) : 50;
      const width = Math.max(.5, Math.min(50, Math.abs(value) / extent * 50));
      root.insertAdjacentHTML("beforeend", `<div class="bl-asset-row"><span>${names[asset]}</span><div class="bl-return-track"><i class="bl-return-bar" style="left:${left}%;width:${width}%;background:${mode === "ridge" ? colors[asset] : "#0f7d8b"}"></i></div><b>${pct(value,2)}</b></div>`);
    });
    ridgeButton.classList.toggle("active", mode === "ridge"); posteriorButton.classList.toggle("active", mode === "posterior");
    setText("blExplanation", mode === "ridge"
      ? "Raw Ridge views are the model’s standalone forecasts. Select the Black–Litterman result to see how the prior and forecast uncertainty moderate them."
      : "The posterior pulls extreme or uncertain views toward the benchmark-implied prior. Treasury and Credit become small positive returns instead of direct negative bets.");
  }
  ridgeButton.addEventListener("click", () => render("ridge"));
  posteriorButton.addEventListener("click", () => render("posterior"));
  window.renderBlackLitterman = render;
  render(blMode);
}

function buildOutcome(decision = activeDecision) {
  const root = document.getElementById("outcomeContent");
  const o = decision.outcome;
  const nextMonth = new Date(`${decision.date}T12:00:00`); nextMonth.setMonth(nextMonth.getMonth() + 1);
  setText("outcomePeriodLabel", nextMonth.toLocaleDateString("en-US", { month: "short", year: "numeric" }));
  if (!Number.isFinite(o.netReturn)) {
    root.innerHTML = `<div class="outcome-pending"><strong>Not observed yet</strong><span>The selected decision is the latest month, so its next-month realized return is still pending.</span></div>`;
    return;
  }
  const relative = o.netReturn - o.benchmarkReturn;
  root.innerHTML = `
    <div class="outcome-primary"><span>MVP net return</span><strong>${pct(o.netReturn)}</strong><small>After ${plainPct(o.transactionCost, 3)} modeled cost</small></div>
    <div class="outcome-row"><span>45 / 35 / 20 benchmark</span><b>${pct(o.benchmarkReturn)}</b></div>
    <div class="outcome-row"><span>Difference vs benchmark</span><b class="${relative >= 0 ? "positive" : "negative"}">${pct(relative)}</b></div>
    <div class="outcome-row"><span>One-way turnover</span><b>${plainPct(o.turnover)}</b></div>`;
}

function renderDecision(decision) {
  activeDecision = decision;
  hydrateHeadline(decision);
  window.loadCalculatorMonth(decision.releases);
  buildComponentBars(decision);
  buildForecasts(decision);
  buildDonut(decision);
  buildOutcome(decision);
  setText("signalMonthLabel", formatMonth(decision.date));
  setText("blDecisionLabel", `${formatMonth(decision.date)} decision`);
  const ranked = decision.releases.filter(r => Number.isFinite(r.z)).sort((a, b) => Math.abs(b.z) - Math.abs(a.z));
  const strongest = ranked.slice(0, 3).map(r => `${names[r.variable]} (${sigma(r.z)})`).join(", ");
  setText("stateExplanation", strongest ? `The largest standardized surprises were ${strongest}. The composites average Growth and Inflation releases separately.` : "No standardized release surprises were available for this month.");
  const ridgeMini = document.getElementById("blRidgeMini");
  const posteriorMini = document.getElementById("blPosteriorMini");
  ridgeMini.innerHTML = Object.entries(decision.forecasts).map(([asset, value]) => `<b title="${names[asset]}">${pct(value)}</b>`).join("");
  posteriorMini.innerHTML = Object.entries(decision.posteriorReturns).map(([asset, value]) => `<b title="${names[asset]}">${pct(value)}</b>`).join("");
  window.renderBlackLitterman(blMode);
}

function buildDecisionSelector() {
  const select = document.getElementById("decisionMonthSelect");
  setText("historyCoverage", `${D.decisionHistory.length} complete portfolio decisions from ${formatMonth(D.decisionHistory[0].date)} to ${formatMonth(D.decisionHistory.at(-1).date)}. Earlier months are used as model warm-up history; later outcomes were never inputs to the decision.`);
  [...D.decisionHistory].reverse().forEach(decision => {
    const option = document.createElement("option");
    option.value = decision.date;
    option.textContent = `${formatMonth(decision.date)}${Number.isFinite(decision.outcome.netReturn) ? "" : " · outcome pending"}`;
    select.appendChild(option);
  });
  select.value = activeDecision.date;
  select.addEventListener("change", () => renderDecision(D.decisionHistory.find(row => row.date === select.value)));
}

document.getElementById("presentButton").addEventListener("click", event => {
  const on = document.body.classList.toggle("presentation"); event.currentTarget.setAttribute("aria-pressed", String(on)); event.currentTarget.textContent = on ? "Exit presentation" : "Presentation mode";
});

hydrateHeadline(); buildCalculator(); buildComponentBars(); buildSignalChart(); buildForecasts(); buildDonut(); buildMetrics(); buildPerformance(); buildBlackLitterman(); buildOutcome(); buildDecisionSelector(); renderDecision(activeDecision);
