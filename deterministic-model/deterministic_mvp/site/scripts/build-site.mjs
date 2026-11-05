// Rebuild presentation pages from reusable templates; never fit or alter a model.
import fs from 'node:fs';
import path from 'node:path';
const site=path.resolve(import.meta.dirname,'..'), dist=path.join(site,'dist');
const template=name=>fs.readFileSync(path.join(site,'templates',name),'utf8');
const core=[['overview','index.html','Research overview'],['framework','framework.html','Backtesting framework'],['experiments','research.html','Experiments &amp; results']];
const studies=[['signals','research.html','Added signals'],['models','models.html','Forecasting methods'],['horizons','horizons.html','Forecast horizons']];
function render({page,title,description,body,scripts,study,generated}){
  const active=study?'experiments':page;
  const links=core.map(([key,url,label])=>`<a href="${url}"${key===active?` class="selected" aria-current="${study&&study!=='signals'?'location':'page'}"`:''}>${label}</a>`).join('');
  const tabs=study?`<nav class="study-tabs shell" aria-label="Experiment type">${studies.map(([key,url,label])=>`<a href="${url}"${key===study?' class="selected" aria-current="page"':''}>${label}</a>`).join('')}</nav>`:'';
  return `<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="${description}"><title>${title} · Deterministic Macro Model</title><link rel="icon" href="favicon.svg"><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="research.css">${study==='models'?'<link rel="stylesheet" href="models.css">':''}<link rel="stylesheet" href="research-site.css"></head>
<body data-research-page="${page}"><a class="skip-link" href="#main">Skip to content</a><header class="topbar"><a class="brand" href="index.html"><span class="brand-mark">D</span><span>Deterministic <b>Macro Model</b></span></a><span class="asof">Research framework · development through 2022</span></header><nav class="page-tabs shell" aria-label="Research pages">${links}</nav>${tabs}
<main id="main">${body}</main>
<footer class="shell site-footer"><span>Macro signals · forecasts · portfolio evaluation</span><div><a href="mvp.html">Original MVP archive</a>${generated?`<span id="${generated}"></span>`:''}</div></footer>
${scripts.map(name=>`<script src="${name}"></script>`).join('')}<script src="research-site.js"></script></body></html>\n`;
}
const framework=template('framework-main.html').replace('{{HOW_IT_WORKS}}',template('how-it-works.html')).replace('{{RELIABILITY}}',template('reliability.html')).replace('{{REFERENCE}}',template('reference-model.html')).replace('{{DATA_METHOD}}',template('data-method.html'));
const signals=`<section class="shell study-hero"><p class="eyebrow">Experiment 1 · added signals</p><h1>Does adding a macro signal<br>improve the result?</h1><p class="lede">Add unemployment claims, credit spreads or the yield curve one at a time. The page preserves the original exploratory comparison and adds a rerun on the corrected reference model.</p><p id="developmentSummary" class="evidence-note"></p><div class="scope-note"><b>Two signal comparisons are shown.</b><p>The earlier runs use the original wider-input model and remain preliminary. The corrected-model rerun below uses the frozen safeguards and matched development dates. Neither result is a reserved-period test.</p><a href="framework.html#stability">See what the reliability checks found →</a></div></section>${template('signals-main.html')}`;
const pages=[
 ['index.html',{page:'overview',title:'Research overview',description:'A backtesting framework for controlled macro-signal and forecasting-method comparisons.',body:template('overview-main.html'),scripts:['research-data.js','model-comparison-data.js','research-overview.js'],generated:'overviewGenerated'}],
 ['framework.html',{page:'framework',title:'Backtesting framework',description:'How the model works, a saved monthly walkthrough, historical timing, matched evaluation and reliability checks.',body:framework,scripts:['research-data.js','model-comparison-data.js','primary-freeze.js','research-primary.js','research-stability.js','framework-page.js','model-walkthrough.js'],generated:'researchGenerated'}],
 ['research.html',{page:'signals',study:'signals',title:'Added signals · Experiments',description:'Original exploratory and corrected-model comparisons of claims, credit and yield-curve inputs.',body:signals,scripts:['research-data.js','corrected-signals-data.js','research.js','corrected-signals.js'],generated:'researchGenerated'}],
 ['models.html',{page:'models',study:'models',title:'Forecasting methods · Experiments',description:'Matched historical-mean, OLS, Ridge, Elastic Net and targeted Ridge extension comparisons.',body:template('models-main.html'),scripts:['model-comparison-data.js','model-visuals.js','models.js'],generated:'modelGenerated'}],
 ['horizons.html',{page:'horizons',study:'horizons',title:'Forecast horizons · Development extension',description:'One-, three- and six-month return target comparisons with explicit overlap and portfolio timing rules.',body:template('horizons-main.html'),scripts:['horizon-data.js','horizons.js'],generated:'horizonGenerated'}],
 ['mvp.html',{page:'archive',title:'Original MVP archive',description:'Historical context for the original macro-surprise forecasting and allocation demonstration.',body:template('archive-main.html'),scripts:[]}],
];
for(const [name,options] of pages)fs.writeFileSync(path.join(dist,name),render(options));
console.log('Built research overview, framework, added-signals, forecasting-method and horizon-extension pages.');
