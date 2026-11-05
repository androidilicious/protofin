// Exercise the new panel against the real artifact, including every selection.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const root=path.resolve(import.meta.dirname,'../dist');
const html=fs.readFileSync(path.join(root,'research.html'),'utf8');
const frameworkHtml=fs.readFileSync(path.join(root,'framework.html'),'utf8');
let activeHtml=frameworkHtml;
const data=JSON.parse(fs.readFileSync(path.join(root,'downloads/research-results.json'),'utf8'));
const elements=new Map();
const element=id=>{
  assert(activeHtml.includes(`id="${id}"`),`Missing element: ${id}`);
  if(!elements.has(id)) elements.set(id,{value:id==='stabilityCohort'?'all_forecasts':id==='stabilityAsset'?'0':'',innerHTML:'',textContent:'',listeners:{},addEventListener(t,fn){this.listeners[t]=fn;}});
  return elements.get(id);
};
const freeze=JSON.parse(fs.readFileSync(path.join(root,'downloads/primary-freeze.json'),'utf8'));
const buttons=['development',...data.periods.map(p=>p.id)].map(id=>({dataset:{period:id},listeners:{},setAttribute(){},addEventListener(t,fn){this.listeners[t]=fn;}}));
const context=vm.createContext({window:{RESEARCH_DATA:data,PRIMARY_FREEZE:freeze},document:{getElementById:element,querySelectorAll:selector=>{assert.equal(selector,'[data-period]');return buttons;}}});
vm.runInContext(fs.readFileSync(path.join(root,'research-primary.js'),'utf8'),context);
assert(element('primaryVerdict').textContent.includes('After the fix, the simple forecast still wins on accuracy.'));
assert.equal(element('primaryReturn').textContent,`${(data.primary.portfolio_results.corrected.cumulative_return*100).toFixed(2)}%`);
assert(element('primaryFreezeStatus').textContent.includes(freeze.id));
for(const row of data.primary.policy_activation){
  element('primaryPolicyDate').value=row.decision_date;
  element('primaryPolicyDate').listeners.change();
  assert.equal((element('primaryPolicyTable').innerHTML.match(/<tr/g)||[]).length,5);
  assert(!/undefined|NaN|Invalid Date/.test(element('primaryPolicyTable').innerHTML));
}
activeHtml=html;
vm.runInContext(fs.readFileSync(path.join(root,'research.js'),'utf8'),context);
assert(element('featureTitle').textContent.includes('Are layoffs increasing?'));
let researchStates=0;
for(const button of buttons){
  button.listeners.click();
  for(const [key,variant] of Object.entries(data.variants).filter(([k])=>['baseline','claims','credit','curve'].includes(k))){
    element('variantSelect').listeners.change({target:{value:key}});
    assert(element('researchLegend').innerHTML.includes(variant.name));
    for(const id of ['researchTable','researchExplanation','researchChart','forecastAudit','calendarYears'])assert(!/undefined|NaN|Invalid Date/.test(element(id).innerHTML));
    researchStates++;
  }
}
activeHtml=frameworkHtml;
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
      assert.equal((element('stabilityForecastTable').innerHTML.match(/<tr/g)||[]).length,data.stability.comparison_order.length);
      assert.equal((element('stabilityPortfolios').innerHTML.match(/<tr/g)||[]).length,data.stability.comparison_order.length);
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
console.log(`PASS: ${states} cohort/asset/model states, ${researchStates} research period/model states, ${data.primary.policy_activation.length} policy decisions; corrected-primary headline/freeze, matched forecast coverage, original result preserved and linked assets.`);
