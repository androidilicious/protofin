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
 if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',listeners:{},addEventListener(t,fn){this.listeners[t]=fn;}});
 return elements.get(id);
};
const buttons=data.windows.map(w=>({dataset:{window:w.id},listeners:{},setAttribute(){},addEventListener(t,fn){this.listeners[t]=fn;}}));
const context=vm.createContext({window:{},document:{getElementById:element,querySelectorAll:selector=>{assert.equal(selector,'[data-window]');return buttons;}},console});
vm.runInContext(fs.readFileSync(path.join(root,'model-comparison-data.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'models.js'),'utf8'),context);
const models=Object.keys(data.models).filter(k=>data.models[k].stage!=='reference');
let count=0;
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
   for(const id of ['coreForecastTable','extensionForecastTable','modelPortfolioTable','modelDecisionTable','modelYearTable','modelChart']){
    assert(!/undefined|NaN|Invalid Date/.test(element(id).innerHTML),`${id} failed for ${model}/${asset}`);
   }
   assert.equal((element('coreForecastTable').innerHTML.match(/<tr/g)||[]).length,4);
   assert.equal((element('extensionForecastTable').innerHTML.match(/<tr/g)||[]).length,3);
   assert.equal((element('modelPortfolioTable').innerHTML.match(/<tr/g)||[]).length,8);
   assert.equal((element('modelDecisionTable').innerHTML.match(/<tr/g)||[]).length,window.results[model].decisions.length);
   count++;
  }
 }
}
for(const name of ['index.html','research.html'])assert(fs.readFileSync(path.join(root,name),'utf8').includes('href="models.html"'));
for(const match of html.matchAll(/(?:src|href)="([^"#]+)"/g)){
 if(!match[1].includes('://'))assert(fs.existsSync(path.resolve(root,match[1])),`Missing linked file ${match[1]}`);
}
console.log(`PASS: ${count} window/model/asset states, table counts, decision coverage and local navigation/assets.`);
