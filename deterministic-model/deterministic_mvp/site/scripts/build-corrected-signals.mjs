// Publish a compact summary of the corrected-model signal rerun.
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const modelRoot=path.resolve(root,'..');
const output=JSON.parse(fs.readFileSync(path.join(modelRoot,'research/outputs/corrected_signals_results.json'),'utf8'));
const corrected={
  generated_at:output.generated_at,
  specification:output.specification,
  sample:{holdings:output.development.results.baseline.stats.months,first:output.settings.common_first_decision,last:output.settings.common_last_decision},
  variants:Object.fromEntries(Object.entries(output.specification.variants).map(([key,meta])=>{
    const stats=output.development.results[key].stats;
    const forecast=output.forecast_cohorts.portfolio_dates[key];
    return [key,{name:meta.name,return:stats.cumulative_return,drawdown:stats.maximum_drawdown,turnover:stats.average_turnover,cost_bps:stats.cost_bps_sum,forecast_months:forecast.months,largest_forecast:forecast.largest_absolute_forecast,extreme_flags:forecast.extreme_asset_months,assets:forecast.assets}];
  })),
};
fs.writeFileSync(path.join(root,'dist/corrected-signals-data.js'),`window.CORRECTED_SIGNALS_DATA = ${JSON.stringify(corrected)};\n`);
fs.mkdirSync(path.join(root,'dist/downloads'),{recursive:true});
fs.copyFileSync(path.join(modelRoot,'research/outputs/corrected_signals_results.json'),path.join(root,'dist/downloads/corrected-signals-results.json'));
fs.copyFileSync(path.join(modelRoot,'research/corrected_signals_spec.json'),path.join(root,'dist/downloads/corrected-signals-spec.json'));
console.log(JSON.stringify({sample:corrected.sample,variants:Object.keys(corrected.variants)}));
await import('./build-site.mjs');
