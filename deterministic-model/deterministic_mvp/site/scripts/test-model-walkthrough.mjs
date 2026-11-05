// Check the explanation against every saved development decision, without refitting.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'../dist');
const R=JSON.parse(fs.readFileSync(path.join(root,'downloads/research-results.json'),'utf8'));
const html=fs.readFileSync(path.join(root,'framework.html'),'utf8');
const script=fs.readFileSync(path.join(root,'model-walkthrough.js'),'utf8');
function mount(data){
  const elements=new Map(), listeners=new Map();
  function getElementById(id){
    assert(html.includes(`id="${id}"`),`Missing walkthrough element: ${id}`);
    if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',open:false,addEventListener(event,fn){listeners.set(`${id}:${event}`,fn);}});
    return elements.get(id);
  }
  vm.runInNewContext(script,{window:{RESEARCH_DATA:data},document:{getElementById}});
  return {elements,listeners};
}
const {elements,listeners}=mount(R), get=id=>elements.get(id);
const rows=R.development.results.corrected.decisions;
assert.equal(rows.length,44);
assert.equal(get('walkthroughMonth').value,rows[0].decision_date,'Start chronologically, not with a chosen winning month');
assert.equal((get('walkthroughMonth').innerHTML.match(/<option /g)||[]).length,rows.length);
const percent=v=>`${(Math.abs(v)<.00005?0:v*100).toFixed(2)}%`;
const strip=s=>s.replace(/<[^>]+>/g,' ');
const date=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
const scales=new Set();
for(const d of rows){
  get('walkthroughOutcome').open=true;
  get('walkthroughMonth').value=d.decision_date;
  listeners.get('walkthroughMonth:change')();
  assert.equal(get('walkthroughOutcome').open,false,'Changing month must conceal the later outcome again');
  const timing=get('walkthroughTiming').innerHTML;
  for(const value of [d.decision_date,d.entry,d.exit])assert(timing.includes(date(value)));
  assert(get('walkthroughTraining').textContent.includes(`${d.training_rows} completed monthly`));
  assert(get('walkthroughTraining').textContent.includes(date(d.last_training_exit)));
  assert(get('walkthroughErrorHistory').textContent.includes(date(d.last_error_exit)));
  assert(d.last_training_exit<=d.decision_date&&d.last_error_exit<=d.decision_date);
  const tableRows=[...get('walkthroughReturns').innerHTML.matchAll(/<tr>(.*?)<\/tr>/g)].map(m=>m[1]);
  assert.equal(tableRows.length,3);
  for(let j=0;j<3;j++){
    assert(tableRows[j].includes(['SPY','IEF','LQD'][j]));
    assert(strip(tableRows[j]).includes(percent(d.forecast[j])));
    assert(strip(tableRows[j]).includes(percent(d.posterior[j])));
    assert(strip(tableRows[j]).includes(`${(Math.sqrt(d.view_error_variance[j])*100).toFixed(2)} pp`));
    assert(get('walkthroughOutcomeValues').innerHTML.includes(percent(d.actual[j])));
    assert(get('walkthroughWeights').innerHTML.includes(`${(d.weights[j]*100).toFixed(1)}%`));
  }
  for(const m of get('walkthroughReturns').innerHTML.matchAll(/left:([\d.]+)%;width:([\d.]+)%/g)){
    assert(+m[1]>=0&&+m[2]<=50&&+m[1]+ +m[2]<=100,'Return bar must fit the shared symmetric axis');
  }
  scales.add(get('walkthroughReturnScale').textContent);
  assert(get('walkthroughTrading').textContent.includes(`${(d.cost*10000).toFixed(2)} bp`));
  assert(get('walkthroughOutcomeValues').innerHTML.includes(percent(d.net_return)));
  const policy=R.primary.policy_activation.find(p=>p.decision_date===d.decision_date);
  assert(get('walkthroughPolicy').textContent.startsWith(`${policy.policy_features.filter(f=>f.enabled).length} of 5`));
  for(const [id,node] of elements)assert(!/undefined|NaN|Invalid Date/.test(node.innerHTML+node.textContent),`Invalid displayed value in ${id}`);
}
assert.equal(scales.size,1,'Return bars must not rescale when selecting months');
assert(get('walkthroughMonth').innerHTML.includes('2022'));
assert(!get('walkthroughMonth').innerHTML.includes('2023'));
const invalid=structuredClone(R);
invalid.development.results.corrected.decisions[0].holding_month='2023-01-31';
assert.throws(()=>mount(invalid),/development-only/,'Reject accidental reserved outcomes');
assert(html.indexOf('id="how-it-works"')<html.indexOf('id="decision-flow"'));
assert(html.includes('Illustrative numbers, not an observed release'));
assert(html.includes('not a confidence interval or RMSE'));
console.log('PASS: 44 saved walkthrough decisions, date/input/forecast/weight/outcome rendering, fixed return scale, outcome reset and reserved-period exclusion.');
