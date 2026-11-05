// Exercise the new panel against the real artifact, including every selection.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const root=path.resolve(import.meta.dirname,'../dist');
const html=fs.readFileSync(path.join(root,'research.html'),'utf8');
const data=JSON.parse(fs.readFileSync(path.join(root,'downloads/research-results.json'),'utf8'));
const elements=new Map();
const element=id=>{
  assert(html.includes(`id="${id}"`),`Missing element: ${id}`);
  if(!elements.has(id)) elements.set(id,{value:id==='stabilityCohort'?'all_forecasts':id==='stabilityAsset'?'0':'',innerHTML:'',textContent:'',listeners:{},addEventListener(t,fn){this.listeners[t]=fn;}});
  return elements.get(id);
};
const context=vm.createContext({window:{RESEARCH_DATA:data},document:{getElementById:element}});
vm.runInContext(fs.readFileSync(path.join(root,'research-stability.js'),'utf8'),context);
let states=0;
for(const cohort of ['all_forecasts','portfolio_dates']) {
  element('stabilityCohort').value=cohort;
  for(const asset of ['0','1','2']) {
    element('stabilityAsset').value=asset;
    for(const key of data.stability.comparison_order) {
      element('stabilityModel').value=key;
      element('stabilityModel').listeners.change();
      for(const [id,e] of elements) assert(!/undefined|NaN|Invalid Date/.test(e.innerHTML+e.textContent),`${id}: ${cohort}/${asset}/${key}`);
      assert.equal((element('stabilityForecastTable').innerHTML.match(/<tr/g)||[]).length,7);
      assert.equal((element('stabilityPortfolios').innerHTML.match(/<tr/g)||[]).length,7);
      assert.equal((element('stabilityChart').innerHTML.match(/<circle/g)||[]).length,data.stability.cohorts[cohort].results[key].months);
      assert(element('stabilityChartTitle').textContent.includes(data.variants[key].name));
      assert(element('stabilityPortfolios').innerHTML.includes('23.99%'));
      states++;
    }
  }
}
assert(element('stabilityCalculation').textContent.includes('-5454.09'));
assert(element('stabilityCause').textContent.includes('589.45%'));
for(const match of html.matchAll(/(?:src|href)="([^"#]+)"/g)) {
  if(!match[1].includes('://')) assert(fs.existsSync(path.resolve(root,match[1])),`Missing asset: ${match[1]}`);
}
console.log(`PASS: ${states} cohort/asset/model states; matched forecast chart coverage, original result preserved, January reconstruction and linked assets.`);
