import fs from "node:fs";
import path from "node:path";

const siteRoot = path.resolve(import.meta.dirname, "..");
const dataRoot = path.join(siteRoot, "data");

function parseCsv(file) {
  const text = fs.readFileSync(file, "utf8").trim();
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { field += '"'; i++; }
      else quoted = !quoted;
    } else if (char === "," && !quoted) { row.push(field); field = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += char;
  }
  row.push(field); rows.push(row);
  const headers = rows.shift();
  return rows.filter(r => r.some(Boolean)).map(values => Object.fromEntries(headers.map((h, i) => [h, values[i] ?? ""])));
}

function typed(rows) {
  const textFields = new Set(["date", "decision_month", "release_date", "variable", "group", "asset", "scenario", "window_start", "window_end", "reference_status"]);
  return rows.map(row => Object.fromEntries(Object.entries(row).map(([key, value]) => {
    if (textFields.has(key) || key.endsWith("_date")) return [key, value];
    if (value === "") return [key, null];
    const n = Number(value);
    return [key, Number.isFinite(n) ? n : value];
  })));
}

const releases = typed(parseCsv(path.join(dataRoot, "clean_releases.csv")));
const signals = typed(parseCsv(path.join(dataRoot, "surprise_signals.csv"))).filter(r => Number.isFinite(r.growth_surprise));
const predictions = typed(parseCsv(path.join(dataRoot, "ridge_predictions.csv")));
const backtest = typed(parseCsv(path.join(dataRoot, "portfolio_backtest.csv")));
const metrics = typed(parseCsv(path.join(dataRoot, "portfolio_metrics.csv")));
const forecastMetrics = typed(parseCsv(path.join(dataRoot, "forecast_metrics.csv")));
const sources = parseCsv(path.join(dataRoot, "data_sources.csv"));
const runSummary = JSON.parse(fs.readFileSync(path.join(dataRoot, "run_summary.json"), "utf8"));

function monthReleases(month) {
  const selected = releases.filter(r => r.decision_month?.startsWith(month) && Number.isFinite(r.standardized_surprise));
  const latest = new Map();
  selected.forEach(r => {
    if (!latest.has(r.variable) || r.release_date > latest.get(r.variable).release_date) latest.set(r.variable, r);
  });
  return [...latest.values()].map(r => ({
    variable: r.variable, group: r.group, releaseDate: r.release_date,
    actual: r.actual_first, consensus: r.survey_median, raw: r.raw_surprise,
    priorSigma: r.historical_surprise_sigma, z: r.standardized_surprise,
  }));
}

const decisions = backtest.filter(row => row.date <= "2026-09-30").map(row => {
  const date = row.date;
  const monthPredictions = predictions.filter(p => p.date === date);
  return {
    date,
    phase: date <= "2022-12-31" ? "development" : "sealed",
    signal: signals.find(s => s.date === date) ?? null,
    releases: monthReleases(date.slice(0, 7)),
    forecasts: Object.fromEntries(monthPredictions.map(p => [p.asset, p.forecast_next_month])),
    alpha: Object.fromEntries(monthPredictions.map(p => [p.asset, p.alpha])),
    posterior: { equity: row.equity_bl_return, treasury: row.treasury_bl_return, ig_credit: row.ig_credit_bl_return },
    dynamicWeights: { equity: row.equity_weight, treasury: row.treasury_weight, ig_credit: row.ig_credit_weight },
    outcomes: {
      dynamic: { return: row.net_return, turnover: row.turnover, cost: row.transaction_cost },
      sixtyForty: { return: row.sixty_forty_net_return, turnover: row.sixty_forty_turnover, cost: row.sixty_forty_transaction_cost },
      spyOnly: { return: row.spy_only_net_return, turnover: row.spy_only_turnover, cost: row.spy_only_transaction_cost },
    },
  };
});

const scoredBacktest = backtest.filter(r => r.date >= "2020-10-31" && r.date <= "2022-12-31");
const scenarioSeries = scoredBacktest.map(r => ({ date: r.date, dynamic: r.net_return, sixtyForty: r.sixty_forty_net_return, spyOnly: r.spy_only_net_return }));

const data = {
  asOf: "2026-10-26",
  workbook: "deterministic_data2 - Oct26.xlsx",
  runSummary,
  signals,
  forecastMetrics,
  metrics,
  scenarioSeries,
  decisions,
  latest: decisions.at(-1),
  sources,
  methodology: {
    training: ["2015-02-01", "2019-02-28"],
    development: ["2019-03-01", "2022-12-31"],
    scoredOverlap: ["2020-10-31", "2022-12-31"],
    sealed: ["2023-01-01", "2026-10-26"],
    costBps: 5,
    decisionTime: "8:00 p.m. New York time on the last trading day of each month",
  },
};

fs.writeFileSync(path.join(siteRoot, "dist", "data.js"), `window.MVP_DATA = ${JSON.stringify(data)};\n`);
console.log(JSON.stringify({ decisions: decisions.length, scoredMonths: scenarioSeries.length, latest: data.latest.date }));
