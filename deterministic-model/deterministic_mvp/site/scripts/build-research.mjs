import fs from 'node:fs';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '..');
const modelRoot = path.resolve(root, '..');
const outputs = process.argv[2];
if (!outputs) throw new Error('Pass the absolute path to deterministic_mvp/research/outputs');
const data = JSON.parse(fs.readFileSync(path.join(outputs, 'research_results.json'), 'utf8'));
if (data.periods.length !== 3 || !data.settings.development_only || !data.development || !data.specification_sha256) throw new Error('Unexpected research scope or missing audit');
for (const period of [...data.periods, data.development]) {
  const dates = Object.values(period.results).map(r => r.decisions.map(d => d.holding_month));
  if (!dates.every(d => JSON.stringify(d) === JSON.stringify(dates[0]))) throw new Error('Unmatched sample dates');
  if (dates.flat().some(d => d > '2022-12-31')) throw new Error('Reserved-test holding month in research artifact');
}
fs.writeFileSync(path.join(root, 'dist/research-data.js'), `window.RESEARCH_DATA = ${JSON.stringify(data)};\n`);
fs.mkdirSync(path.join(root, 'dist/downloads'), { recursive: true });
fs.copyFileSync(path.join(outputs, 'research_results.json'), path.join(root, 'dist/downloads/research-results.json'));
// Keep the existing downloadable source snapshot consistent with the runnable source.
const sourceDir = path.join(root, 'research');
fs.mkdirSync(sourceDir, { recursive: true });
for (const name of ['deterministic_mvp.py', 'research_backtest.py', 'research_diagnostics.py']) {
  fs.copyFileSync(path.join(modelRoot, 'src', name), path.join(sourceDir, name));
}
fs.copyFileSync(path.join(modelRoot, 'tests/test_research_backtest.py'), path.join(sourceDir, 'test_research_backtest.py'));
fs.copyFileSync(path.join(modelRoot, 'research/README.md'), path.join(sourceDir, 'README.md'));
fs.copyFileSync(path.join(modelRoot, 'research/experiment_spec.json'), path.join(sourceDir, 'experiment_spec.json'));
console.log(JSON.stringify({periods: data.periods.length, developmentMonths: data.development.results.baseline.stats.months, rollingWindows: data.rolling_windows.length}));
