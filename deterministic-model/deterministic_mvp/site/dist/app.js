const D = window.MVP_DATA;
const names = {nfp:"Payrolls",retail_sales:"Retail sales",industrial_production:"Industrial production",ism_manufacturing:"ISM",cpi:"CPI",core_cpi:"Core CPI",ppi:"PPI",ahe:"Hourly earnings",equity:"SPY",treasury:"IEF",ig_credit:"LQD"};
const colors = {equity:"#19b6c6",treasury:"#2d67c8",ig_credit:"#7b62c8"};
const scenarioMeta = {
  dynamic:{metric:"dynamic_three_asset",label:"Original three-asset model",title:"Start at 45 / 35 / 20",description:"The original model starts at 45% SPY (equities), 35% IEF (Treasuries), and 20% LQD (investment-grade credit). Macro signals, Ridge forecasts, and Black–Litterman adjust these weights each month.",allocation:{equity:.45,treasury:.35,ig_credit:.20}},
  sixtyForty:{metric:"sixty_forty",label:"60% SPY / 40% IEF",title:"A simple balanced portfolio",description:"The portfolio returns to 60% U.S. equities and 40% intermediate Treasuries each month. It does not use the macro signal.",allocation:{equity:.60,treasury:.40}},
  spyOnly:{metric:"spy_only",label:"100% S&P 500",title:"Pure U.S. equity exposure",description:"All capital remains in SPY. This is the simplest and most concentrated reference case, with no macro timing or bond allocation.",allocation:{equity:1}},
};
const $ = id => document.getElementById(id);
const set = (id,v) => { const el=$(id); if(el) el.textContent=v; };
const pct = (v,d=1,sign=false) => `${sign&&v>=0?"+":""}${(v*100).toFixed(d)}%`;
const sig = v => `${v>=0?"+":"−"}${Math.abs(v).toFixed(2)}σ`;
const month = d => new Date(`${d}T12:00:00`).toLocaleDateString("en-US",{month:"short",year:"numeric"});

function buildCalculator(decision){
  const select=$("releaseSelect");
  select.innerHTML="";
  decision.releases.forEach((r,i)=>{const o=document.createElement("option");o.value=i;o.textContent=names[r.variable]||r.variable;select.appendChild(o)});
  const inputs=[$("actualInput"),$("forecastInput"),$("volInput")];
  function load(){const r=decision.releases[Number(select.value)];if(!r)return;inputs[0].value=r.actual;inputs[1].value=r.consensus;inputs[2].value=r.priorSigma;calc()}
  function calc(){const a=+inputs[0].value,f=+inputs[1].value,v=+inputs[2].value,raw=a-f,z=v>0?raw/v:0;set("rawFormula",`${a.toLocaleString()} − ${f.toLocaleString()} = ${raw.toLocaleString(undefined,{maximumFractionDigits:2})}`);set("zFormula",sig(z));const m=Math.abs(z)<.25?"Close to expectations":Math.abs(z)<.75?"A moderate miss":"An unusually large miss";set("signalMeaning",`${m} · ${z>=0?"above":"below"} forecast`);$("scaleMarker").style.left=`${Math.max(2,Math.min(98,50+z/3*50))}%`}
  select.onchange=load;inputs.forEach(i=>i.oninput=calc);load();
}

function buildPerformance(){
  const rows=D.scenarioSeries, keys=["dynamic","sixtyForty","spyOnly"], palette=["#008aa1","#2d67c8","#efa62f"], W=1000,H=320,p={l:55,r:18,t:20,b:38};
  const series=keys.map(k=>{let w=100;return rows.map(r=>{w*=1+r[k];return w})});
  const all=series.flat(),lo=Math.min(...all)*.97,hi=Math.max(...all)*1.03,x=i=>p.l+i/Math.max(1,rows.length-1)*(W-p.l-p.r),y=v=>p.t+(hi-v)/(hi-lo)*(H-p.t-p.b),parts=[];
  for(let i=0;i<5;i++){const v=lo+(hi-lo)*i/4,yy=y(v);parts.push(`<line class="chart-grid" x1="${p.l}" x2="${W-p.r}" y1="${yy}" y2="${yy}"/><text class="chart-label" x="5" y="${yy+4}">$${v.toFixed(0)}</text>`)}
  series.forEach((s,j)=>parts.push(`<path d="${s.map((v,i)=>`${i?"L":"M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}" fill="none" stroke="${palette[j]}" stroke-width="3" stroke-linecap="round"/>`));
  [0,Math.floor((rows.length-1)/2),rows.length-1].forEach((i,j)=>parts.push(`<text class="chart-label" x="${x(i)}" y="${H-8}" text-anchor="${j===0?"start":j===2?"end":"middle"}">${month(rows[i].date)}</text>`));
  $("performanceChart").innerHTML=parts.join("");
}

function metricFor(key){return D.metrics.find(r=>r.scenario===scenarioMeta[key].metric)}
function showScenario(key){
  document.querySelectorAll(".scenario-tabs button").forEach(b=>b.classList.toggle("active",b.dataset.scenario===key));
  const meta=scenarioMeta[key],m=metricFor(key);set("scenarioLabel",meta.label);set("scenarioTitle",meta.title);set("scenarioDescription",meta.description);set("focusReturn",pct(m.annualized_return));set("focusVol",pct(m.annualized_volatility));set("focusSharpe",m.sharpe_zero_rf.toFixed(2));set("focusDrawdown",pct(m.maximum_drawdown));
  const alloc=meta.allocation;
  set("allocationCaption",key==="dynamic"?"Original starting allocation · adjusted monthly by the model":"Fixed allocation");
  $("scenarioAllocation").innerHTML=Object.entries(alloc).map(([a,w])=>`<i style="width:${w*100}%;background:${colors[a]}">${names[a]} ${Math.round(w*100)}%</i>`).join("");
}

function buildScenarioTable(){
  const order=["dynamic","sixtyForty","spyOnly"];
  $("comparisonBody").innerHTML=order.map(k=>{const m=metricFor(k);return `<tr><td>${scenarioMeta[k].label}</td><td>${pct(m.annualized_return)}</td><td>${pct(m.annualized_volatility)}</td><td>${m.sharpe_zero_rf.toFixed(2)}</td><td>${pct(m.maximum_drawdown)}</td><td>${pct(m.cumulative_return)}</td></tr>`}).join("");
  document.querySelectorAll(".scenario-tabs button").forEach(b=>b.onclick=()=>showScenario(b.dataset.scenario));showScenario("dynamic");
}

function renderReplay(decision){
  const s=decision.signal||{};set("growthState",Number.isFinite(s.growth_surprise)?sig(s.growth_surprise):"—");set("inflationState",Number.isFinite(s.inflation_surprise)?sig(s.inflation_surprise):"—");
  $("sealedNotice").hidden=decision.phase!=="sealed";
  $("releaseBars").innerHTML=decision.releases.map(r=>{const z=r.z,left=z<0?50-Math.min(50,Math.abs(z)/2*50):50,width=Math.max(1,Math.min(50,Math.abs(z)/2*50));return `<div class="release-row"><span>${names[r.variable]}</span><div class="release-track"><i style="left:${left}%;width:${width}%"></i></div><b>${sig(z)}</b></div>`}).join("");
  $("forecastRows").innerHTML=Object.entries(decision.forecasts).map(([a,v])=>`<div class="forecast-row"><span>${names[a]}</span><b>${pct(v,2,true)}</b><small>Ridge view → BL ${pct(decision.posterior[a],2,true)}</small></div>`).join("");
  const weights=decision.dynamicWeights;$("weightGraphic").innerHTML=Object.entries(weights).map(([a,w])=>`<i title="${names[a]} ${pct(w,0)}" style="height:${w*100}%;background:${colors[a]}"></i>`).join("");$("weightLegend").innerHTML=Object.entries(weights).map(([a,w])=>`<div><span>${names[a]}</span><b>${pct(w,0)}</b></div>`).join("");
  if(decision.phase==="sealed") $("outcomeBox").innerHTML=`<div class="outcome-locked"><div><div class="lock-icon">▣</div><b>Outcome hidden</b><span>Reserved historical-test performance is not displayed.</span></div></div>`;
  else {const o=decision.outcomes.dynamic;$("outcomeBox").innerHTML=`<div class="outcome-primary"><span>Dynamic net return</span><strong>${pct(o.return,2,true)}</strong><small>After ${pct(o.cost,3)} modeled cost</small></div><p>Turnover: <b>${pct(o.turnover)}</b></p>`}
  buildCalculator(decision);
}

function buildReplay(){
  const select=$("monthSelect");[...D.decisions].reverse().forEach(d=>{const o=document.createElement("option");o.value=d.date;o.textContent=`${month(d.date)}${d.phase==="sealed"?" · sealed":""}`;select.appendChild(o)});select.value=D.latest.date;select.onchange=()=>renderReplay(D.decisions.find(d=>d.date===select.value));renderReplay(D.latest);
}

buildPerformance();buildScenarioTable();buildReplay();
