const C=window.MODEL_COMPARISON_DATA;
const core=['historical_mean','ols','ridge','elastic_net'];
const extensions=['ridge','ridge_lags','ridge_interactions'];
const allModels=[...core,'ridge_lags','ridge_interactions'];
const node=id=>document.getElementById(id);
const put=(id,value)=>{node(id).textContent=value;};
const pct=(value,digits=2)=>value==null?'—':`${(100*value).toFixed(digits)}%`;
const ratio=value=>value==null?'—':value.toFixed(3);
const pp=value=>`${value>.00005?'+':''}${(Math.abs(value)<.00005?0:100*value).toFixed(2)} pp`;
const date=value=>new Date(`${value}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
const month=value=>new Date(`${value}T12:00:00`).toLocaleDateString('en-US',{month:'short',year:'numeric'});
const triple=values=>values.map(v=>pct(v)).join(' / ');
let windowId='development',asset='equity',model='ridge';
const assetIndex={equity:0,treasury:1,ig_credit:2};

function forecastRows(window,keys){
 return keys.map(key=>{const f=window.results[key].forecast[asset];return `<tr class="${key===model?'selected-model':''}"><td>${C.models[key].name}</td><td>${pct(f.mae)}</td><td>${pct(f.rmse)}</td><td>${ratio(f.oos_r2_vs_mean)}</td><td>${pct(f.forecast_min)} to ${pct(f.forecast_max)}</td><td>${f.over_20pct} / ${f.months}</td><td>${f.mean_nonzero_features.toFixed(1)}</td></tr>`;}).join('');
}

function chart(window){
 const keys=[...new Set([model,'historical_mean',...(C.models[model].stage==='extension'?['ridge']:[]),'fixed453520'])];
 const W=1000,H=340,p={l:62,r:20,t:20,b:40};
 const paths=keys.map(k=>window.results[k].path);
 const values=paths.flat().map(d=>d.wealth),low=Math.min(100,...values)-2,high=Math.max(100,...values)+2;
 const first=new Date(paths[0][0].date).getTime(),last=new Date(paths[0].at(-1).date).getTime();
 const x=d=>p.l+(new Date(d).getTime()-first)/(last-first)*(W-p.l-p.r);
 const y=v=>p.t+(high-v)/(high-low)*(H-p.t-p.b);
 const parts=[];
 for(let i=0;i<5;i++){const v=low+(high-low)*i/4;parts.push(`<line x1="${p.l}" x2="${W-p.r}" y1="${y(v)}" y2="${y(v)}" stroke="#e3e8eb"/><text x="5" y="${y(v)+4}" class="chart-label">$${v.toFixed(0)}</text>`);}
 paths.forEach((rows,i)=>parts.push(`<path d="${rows.map((d,j)=>`${j?'L':'M'}${x(d.date).toFixed(1)},${y(d.wealth).toFixed(1)}`).join(' ')}" fill="none" stroke="${C.models[keys[i]].color}" stroke-width="${keys[i]===model?3.2:2}"/>`));
 [paths[0][0],paths[0][Math.floor(paths[0].length/2)],paths[0].at(-1)].forEach((d,i)=>parts.push(`<text x="${x(d.date)}" y="${H-8}" text-anchor="${i===0?'start':i===2?'end':'middle'}" class="chart-label">${month(d.date)}</text>`));
 node('modelChart').innerHTML=parts.join('');
 node('modelLegend').innerHTML=keys.map(k=>`<span><i style="background:${C.models[k].color}"></i>${C.models[k].name}</span>`).join('');
}

function render(){
 const w=C.windows.find(w=>w.id===windowId),selected=w.results[model];
 document.querySelectorAll('[data-window]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.window===windowId)));
 put('windowTitle',w.name);put('windowCoverage',`${selected.portfolio.months} common holdings · ${date(selected.portfolio.entry)} to ${date(selected.portfolio.exit)}`);
 node('coreForecastTable').innerHTML=forecastRows(w,core);
 node('extensionForecastTable').innerHTML=forecastRows(w,extensions);
 const flags=allModels.reduce((n,k)=>n+w.results[k].forecast[asset].over_20pct,0);
 put('stabilitySummary',flags?`${flags} forecasts for this asset exceed the 20% inspection threshold across the six methods in this window. Inspect them before interpreting model performance.`:'No raw forecast for this asset exceeds 20% in the selected window. This checks extreme extrapolation; it does not establish forecast accuracy.');
 put('selectedDescription',`${C.models[model].name} · ${C.models[model].stage==='extension'?'focused Ridge extension':'core comparison'}. All portfolio totals below use identical holding dates.`);
 const reference=w.results.historical_mean.portfolio.cumulative_return;
 node('modelPortfolioTable').innerHTML=Object.entries(w.results).map(([key,result])=>{const p=result.portfolio;return `<tr class="${key===model?'selected-model':''}"><td>${C.models[key].name}<small class="model-stage">${C.models[key].stage}</small></td><td>${pct(p.cumulative_return)}</td><td>${pct(p.maximum_drawdown)}</td><td>${pct(p.average_turnover)}</td><td>${p.cost_bps_sum.toFixed(2)}</td><td>${pp(p.cumulative_return-reference)}</td></tr>`;}).join('');
 const predictions=new Map(selected.predictions.map(p=>[p.date,p]));
 node('modelDecisionTable').innerHTML=selected.decisions.map(d=>{const p=predictions.get(d.date),j=assetIndex[asset],alpha=p.alpha[j],l1=p.l1_ratio[j];return `<tr><td>${month(d.holding_month)}</td><td>${date(d.decision_date)} → ${date(d.entry)} → ${date(d.exit)}</td><td>${triple(d.forecast)}</td><td>${triple(d.posterior)}</td><td>${triple(d.view_error_variance.map(v=>Math.sqrt(v)))}</td><td>${triple(d.weights)}</td><td>${alpha==null?'No tuning':`${alpha}${l1==null?'':` / ${l1}`}`}</td><td>${pct(d.net_return)}</td></tr>`;}).join('');
 node('modelYearTable').innerHTML=C.calendar_years.map(y=>{const s=y.results[model],p=s.portfolio;return `<tr><td>${y.year} · ${p.months} months${y.partial_year?' (partial)':''}</td><td>${pct(p.cumulative_return)}</td><td>${pct(y.results.historical_mean.portfolio.cumulative_return)}</td><td>${pct(y.results.ridge.portfolio.cumulative_return)}</td><td>${pct(p.maximum_drawdown)}</td><td>${ratio(s.forecast[asset].oos_r2_vs_mean)}</td></tr>`;}).join('');
 chart(w);
}
node('modelPeriodTabs').innerHTML=C.windows.map((w,i)=>`<button type="button" data-window="${w.id}" aria-pressed="${i===0}"><span>0${i+1}</span>${w.name}</button>`).join('');
document.querySelectorAll('[data-window]').forEach(b=>b.addEventListener('click',()=>{windowId=b.dataset.window;render();}));
node('assetSelect').addEventListener('change',e=>{asset=e.target.value;render();});
node('modelSelect').addEventListener('change',e=>{model=e.target.value;render();});
put('sampleSummary',`${C.sample.common_portfolio_months} common portfolio months, ${month(C.sample.first_holding_month)}–${month(C.sample.last_holding_month)}. One-month targets only; the reserved 2023-onward period is excluded.`);
put('warmupSummary',`${C.sample.common_forecast_months} common forecasts per model begin before the ${C.sample.common_portfolio_months}-month portfolio comparison. Portfolio construction waits for 12 earlier completed forecast errors. The headline forecast tables use the portfolio comparison dates; all-forecast metrics are retained in the download. The first lagged-macro row is unavailable, so every method shares the later common training start.`);
node('modelLimitations').innerHTML=C.limitations.map(t=>`<p>${t}</p>`).join('');
put('modelGenerated',`Run ${new Date(C.generated_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'America/New_York'})}`);
render();
