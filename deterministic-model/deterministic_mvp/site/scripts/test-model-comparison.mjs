// Exercise all generated page states without a browser or external packages.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'../dist');
const html=fs.readFileSync(path.join(root,'models.html'),'utf8');
const data=JSON.parse(fs.readFileSync(path.join(root,'downloads/model-comparison-results.json'),'utf8'));
const elements=new Map();
const element=id=>{
 assert(html.includes(`id="${id}"`),`Missing HTML element ${id}`);
 if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',clientWidth:960,attributes:{},setAttribute(name,value){this.attributes[name]=value;},listeners:{},addEventListener(t,fn){this.listeners[t]=fn;}});
 return elements.get(id);
};
const buttons=data.windows.map(w=>({dataset:{window:w.id},listeners:{},setAttribute(){},addEventListener(t,fn){this.listeners[t]=fn;}}));
const context=vm.createContext({window:{},document:{getElementById:element,querySelectorAll:selector=>{assert.equal(selector,'[data-window]');return buttons;}},console});
vm.runInContext(fs.readFileSync(path.join(root,'model-comparison-data.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'model-visuals.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'models.js'),'utf8'),context);
const models=Object.keys(data.models).filter(k=>data.models[k].stage!=='reference');
let count=0;
for(const viewport of [310,620,1100]){
for(const id of ['forecastChart','modelChart','drawdownChart','allocationChart'])element(id).clientWidth=viewport;
for(const button of buttons){
 button.listeners.click();
 const window=data.windows.find(w=>w.id===button.dataset.window);
 assert.equal(element('windowTitle').textContent,window.name);
 for(const model of models){
  assert(html.includes(`value="${model}"`));
  element('modelSelect').listeners.change({target:{value:model}});
  assert(element('selectedDescription').textContent.includes(data.models[model].name));
  for(const asset of ['equity','treasury','ig_credit']){
   element('assetSelect').listeners.change({target:{value:asset}});
   for(const id of ['coreForecastTable','extensionForecastTable','modelPortfolioTable','modelDecisionTable','modelYearTable','modelChart','forecastChart','drawdownChart','allocationChart','inputValues','contributionBars','blReturnBars','accuracyBars','skillGrid','observedOutcome']){
    assert(!/undefined|NaN|Invalid Date/.test(element(id).innerHTML),`${id} failed for ${model}/${asset}`);
   }
   assert.equal((element('coreForecastTable').innerHTML.match(/<tr/g)||[]).length,4);
   assert.equal((element('extensionForecastTable').innerHTML.match(/<tr/g)||[]).length,3);
   assert.equal((element('modelPortfolioTable').innerHTML.match(/<tr/g)||[]).length,8);
   assert.equal((element('modelDecisionTable').innerHTML.match(/<tr/g)||[]).length,window.results[model].decisions.length);
   const rows=window.results[model].decisions;
   const chosen=context.window.ModelVisuals.getSelectedDate();
   assert(rows.some(r=>r.date===chosen));
   assert.equal(element('forecastChart').attributes.viewBox.split(' ')[2],String(viewport));
   assert.equal(element('allocationChart').attributes.viewBox.split(' ')[2],String(viewport));
   element('decisionSelect').listeners.change({target:{value:rows[0].date}});
   assert.equal(context.window.ModelVisuals.getSelectedDate(),rows[0].date);
   assert(element('decisionPrev').disabled);
   element('decisionNext').listeners.click();
   assert.equal(context.window.ModelVisuals.getSelectedDate(),rows[1].date);
   element('decisionSelect').listeners.change({target:{value:rows.at(-1).date}});
   assert(element('decisionNext').disabled);
   element('largestMiss').listeners.click();
   const j=['equity','treasury','ig_credit'].indexOf(asset);
   const worst=window.results[model].predictions.reduce((a,b)=>Math.abs(a.q[j]-a.actual[j])>=Math.abs(b.q[j]-b.actual[j])?a:b);
   assert.equal(context.window.ModelVisuals.getSelectedDate(),worst.date);
   count++;
  }
 }
}
}
// Charts and error comparisons use the same model/month selection as native controls.
const testWindow=data.windows.at(-1),testDate=testWindow.results.ridge.decisions[0].date;
element('allocationChart').listeners.click({target:{closest:()=>({dataset:{date:testDate}})}});
assert.equal(context.window.ModelVisuals.getSelectedDate(),testDate);
element('skillGrid').listeners.click({target:{closest:()=>({dataset:{model:'ols',asset:'treasury'}})}});
assert.equal(element('modelSelect').value,'ols');assert.equal(element('assetSelect').value,'treasury');
assert(element('forecastContext').textContent.includes('IEF'));
// All-series overlays share dates and scales, support both units and cannot go blank.
const seriesCount=id=>(element(id).innerHTML.match(/data-return-series=/g)||[]).length;
assert.equal(seriesCount('modelChart'),6);
assert.equal(seriesCount('drawdownChart'),6);
const axisTicks=()=>element('modelChart').innerHTML.match(/<text[^>]*class="viz-tick">[^<]*<\/text>/g);
const beforeTicks=axisTicks();
const toggle=key=>element('modelLegend').listeners.click({target:{closest:()=>({dataset:{returnModel:key}})}});
toggle('ols');
assert.equal(seriesCount('modelChart'),5);assert.equal(seriesCount('drawdownChart'),5);
assert(!element('modelChart').innerHTML.includes('data-return-series="ols"'));
assert.deepEqual(axisTicks(),beforeTicks,'Hiding a line must not rescale the chart');
element('showAllReturns').listeners.click();assert.equal(seriesCount('modelChart'),6);
for(const key of models)toggle(key);
assert.equal(seriesCount('modelChart'),1,'The final visible line must remain');
element('showAllReturns').listeners.click();
element('returnUnits').listeners.change({target:{value:'dollars'}});
assert(element('returnsTitle').textContent.includes('$100'));
assert(element('modelLegend').innerHTML.includes('$'));
element('returnUnits').listeners.change({target:{value:'percent'}});
assert(element('returnsTitle').textContent.includes('Cumulative net returns'));
assert(element('modelLegend').innerHTML.includes('%'));
element('returnView').listeners.change({target:{value:'selected'}});
assert.equal(seriesCount('modelChart'),3);
element('returnView').listeners.change({target:{value:'all_references'}});
assert.equal(seriesCount('modelChart'),8);assert.equal(seriesCount('drawdownChart'),8);
element('returnView').listeners.change({target:{value:'all'}});
assert.equal(seriesCount('modelChart'),6);
for(const name of ['index.html','research.html'])assert(fs.readFileSync(path.join(root,name),'utf8').includes('href="models.html"'));
for(const match of html.matchAll(/(?:src|href)="([^"#]+)"/g)){
 if(!match[1].includes('://'))assert(fs.existsSync(path.resolve(root,match[1])),`Missing linked file ${match[1]}`);
}
console.log(`PASS: ${count} window/model/asset states, responsive charts at 310/620/1100px, linked month/model controls, decision coverage, all-model return overlays, stable scales, line visibility, return units and navigation/assets.`);
