import fs from "node:fs";
import path from "node:path";

const siteRoot = path.resolve(import.meta.dirname, "..");
const mvpRoot = path.resolve(siteRoot, "..");
const outputRoot = path.join(mvpRoot, "outputs");

function parseCsv(file) {
  const text = fs.readFileSync(file, "utf8").trim();
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { field += '"'; i++; }
      else quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(field); field = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += char;
  }
  row.push(field); rows.push(row);
  const headers = rows.shift();
  return rows.filter(r => r.some(Boolean)).map(values => Object.fromEntries(headers.map((h, i) => [h, values[i] ?? ""])));
}

function numericRows(rows) {
  return rows.map(row => Object.fromEntries(Object.entries(row).map(([key, value]) => {
    if (key === "date" || key.includes("status") || key.includes("asset") || key.includes("detail") || key.includes("field") || key.includes("source") || key.includes("proxy") || key.includes("transformation") || key.includes("limitation") || key.includes("downloaded")) return [key, value];
    if (value === "") return [key, null];
    const number = Number(value);
    return [key, Number.isFinite(number) ? number : value];
  })));
}

const latestSurprise = JSON.parse(fs.readFileSync(path.join(outputRoot, "latest_surprise_signal.json"), "utf8"));
const latestForecast = JSON.parse(fs.readFileSync(path.join(outputRoot, "latest_forecast.json"), "utf8"));
const latestPortfolio = JSON.parse(fs.readFileSync(path.join(outputRoot, "latest_portfolio.json"), "utf8"));
const surpriseSignals = numericRows(parseCsv(path.join(outputRoot, "surprise_signals.csv"))).filter(row => row.growth_surprise !== null);
const forecastMetrics = numericRows(parseCsv(path.join(outputRoot, "forecast_metrics.csv")));
const portfolioMetrics = numericRows(parseCsv(path.join(outputRoot, "portfolio_metrics.csv")))[0];
const backtest = numericRows(parseCsv(path.join(outputRoot, "portfolio_backtest.csv")));
const ridgePredictions = numericRows(parseCsv(path.join(outputRoot, "ridge_predictions.csv")));
const modelDataset = numericRows(parseCsv(path.join(outputRoot, "model_dataset.csv")));
const sources = parseCsv(path.join(mvpRoot, "data_sources.csv"));
const releases = numericRows(parseCsv(path.join(outputRoot, "clean_releases.csv")));
const latestMonth = latestSurprise.date.slice(0, 7);
const latestReleases = releases.filter(row => row.decision_month?.startsWith(latestMonth)).map(row => ({
  variable: row.variable,
  group: row.group,
  release_date: row.release_date,
  actual: row.actual_first,
  consensus: row.survey_median,
  raw_surprise: row.raw_surprise,
  sigma: row.historical_surprise_sigma,
  z: row.standardized_surprise,
}));
const latestBacktest = backtest.at(-1);
const blackLitterman = {
  benchmarkWeights: { equity: 0.45, treasury: 0.35, ig_credit: 0.20 },
  ridgeViews: latestForecast.forecasts,
  posteriorReturns: {
    equity: latestBacktest.equity_bl_return,
    treasury: latestBacktest.treasury_bl_return,
    ig_credit: latestBacktest.ig_credit_bl_return,
  },
  viewRmse: Object.fromEntries(forecastMetrics.map(row => [row.asset, row.rmse])),
  settings: { tau: 0.05, riskAversion: 2.5, covarianceWindowMonths: 36, viewMatrix: "Identity" },
};

const decisionHistory = backtest.map(portfolio => {
  const date = portfolio.date;
  const month = date.slice(0, 7);
  const signal = surpriseSignals.find(row => row.date === date) ?? null;
  const predictions = ridgePredictions.filter(row => row.date === date);
  const modelRow = modelDataset.find(row => row.date === date) ?? null;
  return {
    date,
    signal,
    releases: releases.filter(row => row.decision_month?.startsWith(month)).map(row => ({
      variable: row.variable,
      group: row.group,
      release_date: row.release_date,
      actual: row.actual_first,
      consensus: row.survey_median,
      raw_surprise: row.raw_surprise,
      sigma: row.historical_surprise_sigma,
      z: row.standardized_surprise,
    })),
    forecasts: Object.fromEntries(predictions.map(row => [row.asset, row.forecast_next_month])),
    forecastAlpha: Object.fromEntries(predictions.map(row => [row.asset, row.alpha])),
    realizedAssetReturns: Object.fromEntries(predictions.map(row => [row.asset, row.realized_next_month])),
    posteriorReturns: {
      equity: portfolio.equity_bl_return,
      treasury: portfolio.treasury_bl_return,
      ig_credit: portfolio.ig_credit_bl_return,
    },
    weights: {
      equity: portfolio.equity_weight,
      treasury: portfolio.treasury_weight,
      ig_credit: portfolio.ig_credit_weight,
    },
    outcome: {
      grossReturn: portfolio.gross_return,
      transactionCost: portfolio.transaction_cost,
      netReturn: portfolio.net_return,
      benchmarkReturn: portfolio.benchmark_return,
      turnover: portfolio.turnover,
    },
    nextReturnsFromModel: modelRow ? {
      equity: modelRow.next_equity_return,
      treasury: modelRow.next_treasury_return,
      ig_credit: modelRow.next_ig_credit_return,
    } : null,
  };
});

const data = { latestSurprise, latestForecast, latestPortfolio, surpriseSignals, forecastMetrics, portfolioMetrics, backtest, sources, latestReleases, blackLitterman, decisionHistory };
fs.writeFileSync(path.join(siteRoot, "dist", "data.js"), `window.MVP_DATA = ${JSON.stringify(data)};\n`);
console.log(JSON.stringify({ output: path.join(siteRoot, "dist", "data.js"), latestMonth, releaseCount: latestReleases.length }));
