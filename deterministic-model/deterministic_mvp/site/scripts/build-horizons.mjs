// Publish a compact horizon summary while preserving the full downloadable artifact.
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const modelRoot=path.resolve(root,'..');
const output=JSON.parse(fs.readFileSync(path.join(modelRoot,'research/outputs/horizon_results.json'),'utf8'));
const original=JSON.parse(fs.readFileSync(path.join(root,'dist/downloads/research-results.json'),'utf8'));
const oneMonthDecisions=original.development.results.corrected.decisions;
const compact={
  generated_at:output.generated_at,
  specification:output.specification,
  one_month:{
    target_months:1,
    eligible_forecasts:original.stability.cohorts.all_forecasts.results.corrected.months,
    portfolio_holdings:original.primary.portfolio_results.corrected.months,
    cumulative_return:original.primary.portfolio_results.corrected.cumulative_return,
    historical_mean_return:original.primary.portfolio_results.historical_mean.cumulative_return,
    first_holding_month:oneMonthDecisions[0].holding_month,
    last_holding_month:oneMonthDecisions.at(-1).holding_month,
  },
  horizons:Object.fromEntries(Object.entries(output.horizons).map(([key,value])=>[key,{
    months:value.months,
    eligible_forecasts:value.forecast_scores.months,
    target_first_month:value.target_first_month,
    target_last_month:value.target_last_month,
    forecast_scores:value.forecast_scores,
    portfolio_holdings:value.portfolio_results.corrected.holding_periods,
    portfolio_results:value.portfolio_results,
  }])),
};
fs.writeFileSync(path.join(root,'dist/horizon-data.js'),`window.HORIZON_DATA = ${JSON.stringify(compact)};\n`);
fs.mkdirSync(path.join(root,'dist/downloads'),{recursive:true});
fs.copyFileSync(path.join(modelRoot,'research/outputs/horizon_results.json'),path.join(root,'dist/downloads/horizon-results.json'));
fs.copyFileSync(path.join(modelRoot,'research/horizons_spec.json'),path.join(root,'dist/downloads/horizons-spec.json'));
console.log(JSON.stringify({horizons:Object.keys(compact.horizons),oneMonth:compact.one_month}));
await import('./build-site.mjs');
