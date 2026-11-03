import fs from 'node:fs';
import path from 'node:path';
const site = path.resolve(import.meta.dirname, '..');
const outputs = process.argv[2];
if (!outputs) throw new Error('Pass model_comparison/outputs path');
const file = path.join(outputs, 'model_comparison_results.json');
const data = JSON.parse(fs.readFileSync(file, 'utf8'));
if (data.specification.id !== 'model-comparison-v1' || data.specification.last_holding_month !== '2022-12-31') throw new Error('Unexpected experiment scope');
for (const window of data.windows) {
 const values=Object.values(window.results);
 const dates=values.map(r=>JSON.stringify(r.decisions.map(d=>d.holding_month)));
 if (!dates.every(d=>d===dates[0])) throw new Error('Unmatched portfolio dates');
 for (const result of values) if(result.decisions.some(d=>d.holding_month>'2022-12-31')) throw new Error('Reserved holding month');
}
fs.writeFileSync(path.join(site,'dist/model-comparison-data.js'),`window.MODEL_COMPARISON_DATA = ${JSON.stringify(data)};\n`);
fs.mkdirSync(path.join(site,'dist/downloads'),{recursive:true});
fs.copyFileSync(file,path.join(site,'dist/downloads/model-comparison-results.json'));
console.log(JSON.stringify({models:Object.keys(data.models).length,forecastMonths:data.sample.common_forecast_months,portfolioMonths:data.sample.common_portfolio_months}));
