import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const root = path.resolve(import.meta.dirname, '..');
const modelRoot = path.resolve(root, '..');
const outputs = process.argv[2];
if (!outputs) throw new Error('Pass the absolute path to deterministic_mvp/research/outputs');
const data = JSON.parse(fs.readFileSync(path.join(outputs, 'research_results.json'), 'utf8'));
if (data.periods.length !== 3 || !data.settings.development_only || !data.development || !data.specification_sha256 || !data.stability || !data.primary) throw new Error('Unexpected research scope or missing audit');
const freeze=JSON.parse(fs.readFileSync(path.join(modelRoot,'research/primary_freeze.json'),'utf8'));
for(const [name,digest] of Object.entries({...freeze.files,...freeze.inputs})) {
  const actual=crypto.createHash('sha256').update(fs.readFileSync(path.join(modelRoot,name))).digest('hex');
  if(actual!==digest)throw new Error(`Frozen primary changed: ${name}`);
}
if(!data.primary.numerical_acceptance.passed || data.primary.specification_sha256!==freeze.files['research/primary_spec.json']) throw new Error('Unverified corrected primary');
for(const [name,digest] of Object.entries(data.code_hashes))if(freeze.files[`src/${name}`]!==digest)throw new Error(`Stale primary research result: ${name}`);
if(data.specification_sha256!==freeze.files['research/experiment_spec.json'])throw new Error('Stale research experiment settings');
for (const cohort of Object.values(data.stability.cohorts)) {
  const dates = Object.values(cohort.timeline).map(rows => rows.map(r => r.holding_month));
  if (!dates.every(d => JSON.stringify(d) === JSON.stringify(dates[0]))) throw new Error('Unmatched stability dates');
  if (dates.flat().some(d => d > '2022-12-31')) throw new Error('Reserved-test month in stability artifact');
}
for (const period of [...data.periods, data.development]) {
  const dates = Object.values(period.results).map(r => r.decisions.map(d => d.holding_month));
  if (!dates.every(d => JSON.stringify(d) === JSON.stringify(dates[0]))) throw new Error('Unmatched sample dates');
  if (dates.flat().some(d => d > '2022-12-31')) throw new Error('Reserved-test holding month in research artifact');
}
fs.writeFileSync(path.join(root, 'dist/research-data.js'), `window.RESEARCH_DATA = ${JSON.stringify(data)};\n`);
fs.writeFileSync(path.join(root, 'dist/primary-freeze.js'), `window.PRIMARY_FREEZE = ${JSON.stringify(freeze)};\n`);
fs.mkdirSync(path.join(root, 'dist/downloads'), { recursive: true });
fs.copyFileSync(path.join(outputs, 'research_results.json'), path.join(root, 'dist/downloads/research-results.json'));
for(const [source,name] of [['primary_spec.json','primary-spec.json'],['primary_freeze.json','primary-freeze.json']]) {
  fs.copyFileSync(path.join(modelRoot,'research',source),path.join(root,'dist/downloads',name));
}
// Keep the existing downloadable source snapshot consistent with the runnable source.
const sourceDir = path.join(root, 'research');
fs.mkdirSync(sourceDir, { recursive: true });
for (const name of ['deterministic_mvp.py', 'research_backtest.py', 'research_diagnostics.py', 'research_inference.py', 'research_stability.py', 'corrected_primary.py']) {
  fs.copyFileSync(path.join(modelRoot, 'src', name), path.join(sourceDir, name));
}
for (const name of ['test_research_backtest.py', 'test_research_inference.py', 'test_research_stability.py', 'test_corrected_primary.py']) {
  fs.copyFileSync(path.join(modelRoot, 'tests', name), path.join(sourceDir, name));
}
fs.copyFileSync(path.join(modelRoot, 'research/README.md'), path.join(sourceDir, 'README.md'));
fs.copyFileSync(path.join(modelRoot, 'research/STABILITY_REVIEW.md'), path.join(sourceDir, 'STABILITY_REVIEW.md'));
fs.copyFileSync(path.join(modelRoot, 'research/experiment_spec.json'), path.join(sourceDir, 'experiment_spec.json'));
fs.copyFileSync(path.join(modelRoot, 'research/experiment_spec.v1.json'), path.join(sourceDir, 'experiment_spec.v1.json'));
fs.copyFileSync(path.join(modelRoot, 'research/experiment_spec.v2.json'), path.join(sourceDir, 'experiment_spec.v2.json'));
for(const name of ['experiment_spec.v3.json','primary_spec.json','primary_freeze.json','PRIMARY_MODEL.md']) {
  fs.copyFileSync(path.join(modelRoot,'research',name),path.join(sourceDir,name));
}
console.log(JSON.stringify({periods: data.periods.length, developmentMonths: data.development.results.baseline.stats.months, rollingWindows: data.rolling_windows.length}));
await import('./build-site.mjs');
