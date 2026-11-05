// Check the new navigation, study boundaries, data summaries and old saved links.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'../dist');
const files=['index.html','framework.html','research.html','models.html','horizons.html','mvp.html'];
const pages=new Map(files.map(name=>[name,fs.readFileSync(path.join(root,name),'utf8')]));
const ids=html=>[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
for(const [name,html] of pages){
  const all=ids(html);
  assert.equal(new Set(all).size,all.length,`Duplicate IDs in ${name}`);
  assert.equal((html.match(/<h1(?:\s|>)/g)||[]).length,1,`One main heading required: ${name}`);
  const mainNav=html.match(/<nav[^>]*aria-label="Research pages"[^>]*>(.*?)<\/nav>/s)?.[1];
  assert(mainNav,`Missing main navigation: ${name}`);
  assert.equal((mainNav.match(/<a /g)||[]).length,3);
  for(const label of ['Research overview','Backtesting framework','Experiments &amp; results'])assert(mainNav.includes(label));
  assert(!mainNav.includes('archive'),'Archives must not displace a main research tab');
  assert(html.includes('href="mvp.html"'));
  if(['research.html','models.html','horizons.html'].includes(name)){
    assert(html.includes('aria-label="Experiment type"'));
    for(const label of ['Added signals','Forecasting methods','Forecast horizons'])assert(html.includes(label));
  }
  for(const match of html.matchAll(/(?:src|href)="([^"]+)"/g)){
    const ref=match[1];
    if(/^(?:https?:|mailto:|data:)/.test(ref))continue;
    const [file,hash]=ref.split('#');
    const target=path.resolve(root,file||name);
    assert(fs.existsSync(target),`Missing link: ${name} → ${ref}`);
    if(hash&&target.endsWith('.html'))assert(ids(fs.readFileSync(target,'utf8')).includes(hash),`Missing anchor: ${name} → ${ref}`);
  }
}
assert(pages.get('horizons.html').includes('not yet been implemented or backtested'));
assert(!pages.get('horizons.html').includes('<select'),'Do not imply an implemented horizon selector');
assert(pages.get('research.html').includes('added signals have not yet been rerun'));
assert(!pages.get('research.html').includes('id="stability"'));
assert(pages.get('framework.html').includes('id="stability"'));
assert(!pages.get('index.html').includes('id="performanceChart"'),'Legacy MVP cannot remain the homepage');
const archive=fs.readFileSync(path.join(root,'mvp.html'),'utf8');
assert(archive.includes('older interactive replay depends on data bundles absent from this checkout'));
assert(!archive.includes('src="data.js"'),'Do not publish a broken archive replay');
assert(fs.readFileSync(path.join(root,'../templates/original-mvp.html'),'utf8').includes('id="performanceChart"'));

const R=JSON.parse(fs.readFileSync(path.join(root,'downloads/research-results.json'),'utf8'));
const M=JSON.parse(fs.readFileSync(path.join(root,'downloads/model-comparison-results.json'),'utf8'));
for(const [page,script] of [['index.html','research-overview.js'],['framework.html','framework-page.js']]){
  const elements=new Map();
  const getElementById=id=>{
    assert(pages.get(page).includes(`id="${id}"`),`${page}: missing ${id}`);
    if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:''});
    return elements.get(id);
  };
  vm.runInNewContext(fs.readFileSync(path.join(root,script),'utf8'),{window:{RESEARCH_DATA:R,MODEL_COMPARISON_DATA:M},document:{getElementById}});
  for(const [id,node] of elements)assert(!/undefined|NaN|Invalid Date/.test(node.textContent+node.innerHTML),`${page}: invalid ${id}`);
  if(page==='index.html'){
    assert(elements.get('overviewSignalScope').textContent.includes('44'));
    assert(elements.get('overviewModelScope').textContent.includes('43'));
    assert(elements.get('overviewReliabilityFinding').textContent.includes('12.63%'));
  }
}
const routeScript=fs.readFileSync(path.join(root,'research-site.js'),'utf8');
for(const pathname of ['/research','/research.html']){
  for(const hash of ['#primary','#stability','#research-method']){
    let redirected;
    vm.runInNewContext(routeScript,{URL,location:{pathname,hash,href:`https://example.com${pathname}${hash}`,replace(url){redirected=url;}}});
    assert.equal(redirected,`https://example.com/framework.html${hash}`);
  }
}
let revealed=false;
const details={tagName:'DETAILS',open:false,parentElement:null};
const target={tagName:'SECTION',parentElement:details,scrollIntoView(){revealed=true;}};
vm.runInNewContext(routeScript,{location:{pathname:'/framework.html',hash:'#primary'},document:{getElementById:()=>target},window:{addEventListener(){}},requestAnimationFrame:fn=>fn()});
assert(details.open&&revealed,'Saved reference-model links must open the containing details panel');
console.log('PASS: 5 research pages, 3 main tabs, study subtabs, unique headings/IDs, links/assets, separate samples, planned horizon status, archived MVP and saved-link compatibility.');
