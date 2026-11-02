import fs from 'node:fs';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '..');
const outputs = process.argv[2];
if (!outputs) throw new Error('Pass the absolute path to deterministic_mvp/research/outputs');
const data = JSON.parse(fs.readFileSync(path.join(outputs, 'research_results.json'), 'utf8'));
if (data.periods.length !== 3 || !data.settings.development_only) throw new Error('Unexpected research scope');
for (const period of data.periods) {
  const counts = Object.values(period.results).map(r => r.stats.months);
  if (!counts.every(c => c === counts[0])) throw new Error('Unmatched sample dates');
}
fs.writeFileSync(path.join(root, 'dist/research-data.js'), `window.RESEARCH_DATA = ${JSON.stringify(data)};\n`);
fs.mkdirSync(path.join(root, 'dist/downloads'), { recursive: true });
fs.copyFileSync(path.join(outputs, 'research_results.json'), path.join(root, 'dist/downloads/research-results.json'));
console.log(JSON.stringify({periods: data.periods.length, rollingWindows: data.rolling_windows.length}));
