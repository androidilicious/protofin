const R = window.RESEARCH_DATA;
const modelKeys = ['baseline', 'claims', 'credit', 'curve'];
const allKeys = [...modelKeys, 'fixed453520', 'sixtyForty', 'spyOnly'];
const el = id => document.getElementById(id);
const put = (id, text) => { el(id).textContent = text; };
const percent = (v, digits=2) => v == null ? '—' : `${(v*100).toFixed(digits)}%`;
const pp = v => `${v > 0 ? '+' : ''}${(v*100).toFixed(2)} pp`;
const dateLabel = d => new Date(`${d}T12:00:00`).toLocaleDateString('en-US', {month:'short',day:'numeric',year:'numeric'});
const monthLabel = d => new Date(`${d}T12:00:00`).toLocaleDateString('en-US', {month:'short',year:'numeric'});
let periodId = R.periods[0].id;
let variantId = 'baseline';
let referenceId = 'fixed453520';
const featureInfo = {
  baseline: {label:'Research baseline', title:'The original macro model, rerun', description:'Eight macro release surprises, policy expectations, ANFCI, and GPR feed the original Ridge and Black–Litterman pipeline. No candidate signal is added.', formula:'Growth and Inflation composites + policy and risk context → three return forecasts → BL → weights.', timing:'Uses the same research execution and training rules as every added-signal version.'},
  claims: {label:'Labor-market deterioration', title:'Are layoffs increasing?', description:'A rise in unemployment claims can add information about labor-market weakness between monthly payroll releases. We test the change rather than the raw number of claims.', formula:'Latest available four-week average ÷ its value three months earlier − 1.', timing:'Weekly Saturday observations are assumed available five calendar days later. Values use revised history.'},
  credit: {label:'Corporate credit conditions', title:'Are investors demanding more credit compensation?', description:'The Baa corporate–Treasury yield spread is a broad measure of credit conditions. It may add information for corporate bonds and equities beyond the existing ANFCI input.', formula:'Latest available spread level + change from the previous month (both in percentage points).', timing:'One business-day observation lag. Baa spread is a proxy, not the option-adjusted spread of LQD.'},
  curve: {label:'Interest-rate conditions', title:'What does the yield curve add?', description:'The gap between long-term and short-term Treasury yields adds a different view of rate and economic conditions from the workbook’s short policy-path measures.', formula:'10-year Treasury yield − 3-month Treasury yield, measured in percentage points.', timing:'Uses the latest observation available after a conservative one business-day lag.'},
};

function chart(period) {
  const keys = [...new Set(['baseline', variantId, referenceId])];
  const W=1000,H=330,p={l:58,r:18,t:20,b:40};
  const points = keys.map(k => period.results[k].path);
  const all = points.flat().map(p=>p.wealth);
  const lo = Math.min(100,...all)-2, hi=Math.max(100,...all)+2;
  const n=points[0].length;
  const x=i=>p.l+i/(n-1)*(W-p.l-p.r),y=v=>p.t+(hi-v)/(hi-lo)*(H-p.t-p.b);
  const output=[];
  for(let i=0;i<5;i++){const v=lo+i*(hi-lo)/4, yy=y(v);output.push(`<line class="chart-grid" x1="${p.l}" x2="${W-p.r}" y1="${yy}" y2="${yy}"/><text class="chart-label" x="4" y="${yy+4}">$${v.toFixed(0)}</text>`);}
  points.forEach((rows,j)=>{const k=keys[j];output.push(`<path d="${rows.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(1)},${y(v.wealth).toFixed(1)}`).join(' ')}" fill="none" stroke="${R.variants[k].color}" stroke-width="${k===variantId?3.5:2.3}" stroke-linejoin="round"/>`);});
  [0,Math.floor((n-1)/2),n-1].forEach((i,j)=>output.push(`<text class="chart-label" x="${x(i)}" y="${H-8}" text-anchor="${j===0?'start':j===2?'end':'middle'}">${dateLabel(points[0][i].date)}</text>`));
  el('researchChart').innerHTML=output.join('');
  el('researchLegend').innerHTML=keys.map(k=>`<span><i style="background:${R.variants[k].color}"></i>${R.variants[k].name}</span>`).join('');
}

function explain(period) {
  const selected=period.results[variantId].stats, base=period.results.baseline.stats;
  const delta=selected.difference_vs_baseline;
  const models=modelKeys.map(key=>({key,stats:period.results[key].stats}));
  const best=models.reduce((a,b)=>a.stats.cumulative_return>b.stats.cumulative_return?a:b);
  const returnStatement=variantId==='baseline'
    ? `The rerun original model returned ${percent(base.cumulative_return)}. Use the selector to see whether each added signal changes the result.`
    : `${R.variants[variantId].name} returned ${percent(selected.cumulative_return)}, ${Math.abs(delta)<.00005?'approximately the same as':delta>0?'above':'below'} the original model’s ${percent(base.cumulative_return)} (${pp(delta)}).`;
  const riskChange=selected.maximum_drawdown-base.maximum_drawdown;
  const riskStatement=variantId==='baseline'
    ? `The original model’s largest daily peak-to-trough loss was ${percent(base.maximum_drawdown)}. This includes losses inside a month that monthly snapshots can miss.`
    : `Its largest daily drawdown was ${percent(selected.maximum_drawdown)}, compared with ${percent(base.maximum_drawdown)} for the original. ${Math.abs(riskChange)<.00005?'Drawdown protection was essentially unchanged.':riskChange>0?'The added signal reduced the drawdown in this window.':'The added signal produced a deeper drawdown in this window.'}`;
  const recovery=selected.recovery_date?`The portfolio regained its pre-drawdown peak by ${dateLabel(selected.recovery_date)} within this window.`:'The portfolio had not regained its pre-drawdown peak by the end of this window.';
  const rmse=selected.forecast_rmse;
  el('researchExplanation').innerHTML=`<p class="kicker">Reading this result</p><h3>${period.name}: what changed?</h3><div class="research-explanation-grid"><div><h4>Return</h4><p>${returnStatement}</p></div><div><h4>Risk and recovery</h4><p>${riskStatement} ${recovery}</p></div></div><p><strong>Across the model experiments:</strong> ${R.variants[best.key].name} had the highest total return in this window (${percent(best.stats.cumulative_return)}). This is a description of this episode, not a selection of a new model.</p><details><summary>Inspect forecast accuracy before Black–Litterman</summary><p>Selected model Ridge RMSE: ${percent(rmse)}. Original model: ${percent(base.forecast_rmse)}. This is the pooled root mean squared error across all three assets and holding months, before BL moderation. Lower is better.${rmse>.2?' Raw Ridge forecasts were unstable during this shock. Large errors show extrapolation risk; BL moderation and allocation limits reduce the influence of these views.':''}</p></details>`;
}

function decisionRows(period) {
  const signalName={baseline:'Existing macro inputs',claims:'Claims change, 3 months',credit:'Credit spread / 1m change',curve:'10y − 3m yield spread'};
  put('signalColumn',signalName[variantId]);
  el('researchDecisions').innerHTML=period.results[variantId].decisions.map(d=>{
    const s=R.signal_observations.find(r=>r.date===d.date);
    let value='No added signal';
    if(s && variantId==='claims')value=percent(s.claims_change_3m);
    if(s && variantId==='credit')value=`${s.credit_level.toFixed(2)} pp / ${s.credit_change_1m.toFixed(2)} pp`;
    if(s && variantId==='curve')value=`${s.curve_level.toFixed(2)} pp`;
    return `<tr><td>${dateLabel(d.decision_date)}</td><td>${dateLabel(d.entry)} → ${dateLabel(d.exit)}</td><td>${value}</td><td>${d.weights.map(w=>percent(w,0)).join(' / ')}</td><td>${percent(d.net_return)}</td></tr>`;
  }).join('');
}

function render() {
  const period=R.periods.find(p=>p.id===periodId), chosen=period.results[variantId], s=chosen.stats, f=featureInfo[variantId];
  document.querySelectorAll('[data-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.period===periodId)));
  put('periodName',period.name);put('periodDescription',period.description);put('holdingDates',`${s.months} monthly holdings · ${dateLabel(s.entry)} to ${dateLabel(s.exit)}`);
  put('featureLabel',f.label);put('featureTitle',f.title);put('featureDescription',f.description);put('featureFormula',f.formula);put('featureTiming',f.timing);
  put('researchReturn',percent(s.cumulative_return));put('researchEndValue',`$100 became $${s.end_value.toFixed(2)}`);put('researchDrawdown',percent(s.maximum_drawdown));put('researchDifference',pp(s.difference_vs_baseline));put('researchTurnover',percent(s.average_turnover));
  el('researchTable').innerHTML=allKeys.map(k=>{const a=period.results[k].stats;return `<tr class="${k===variantId?'selected-row':''}"><td>${R.variants[k].name}<small class="research-type">${R.variants[k].kind==='model'?'Three-asset model':'Passive reference'}</small></td><td>${percent(a.cumulative_return)}</td><td>${percent(a.maximum_drawdown)}</td><td>${pp(a.difference_vs_baseline)}</td><td>${percent(a.annualized_volatility)}</td><td>${percent(a.average_turnover)}</td></tr>`;}).join('');
  chart(period);explain(period);decisionRows(period);
}

function consistency() {
  el('episodeMatrix').innerHTML=['claims','credit','curve'].map(k=>`<tr><td>${R.variants[k].name}</td>${R.periods.map(p=>{const v=p.results[k].stats.difference_vs_baseline;return `<td class="${v>=0?'positive-delta':'negative-delta'}">${pp(v)}</td>`;}).join('')}</tr>`).join('');
  const windows=R.rolling_windows;
  put('rollingCoverage',`${windows.length} overlapping windows of 12 holding months, from ${monthLabel(windows[0].start)}–${monthLabel(windows[0].end)} through ${monthLabel(windows.at(-1).start)}–${monthLabel(windows.at(-1).end)}.`);
  el('rollingTable').innerHTML=['claims','credit','curve'].map(k=>{const diffs=windows.map(w=>w.results[k].cumulative_return-w.results.baseline.cumulative_return).sort((a,b)=>a-b);const wins=diffs.filter(v=>v>1e-8).length,n=diffs.length;const median=n%2?diffs[(n-1)/2]:(diffs[n/2-1]+diffs[n/2])/2;return `<tr><td>${R.variants[k].name}</td><td>${wins} / ${n} (${(100*wins/n).toFixed(0)}%)</td><td>${pp(median)}</td><td>${pp(diffs[0])}</td></tr>`;}).join('');
}

el('periodTabs').innerHTML=R.periods.map((p,i)=>`<button type="button" data-period="${p.id}" aria-pressed="${i===0}"><span>0${i+1}</span>${p.name}</button>`).join('');
document.querySelectorAll('[data-period]').forEach(b=>b.addEventListener('click',()=>{periodId=b.dataset.period;render();}));
el('variantSelect').addEventListener('change',e=>{variantId=e.target.value;render();});
el('referenceSelect').addEventListener('change',e=>{referenceId=e.target.value;render();});
el('researchSources').innerHTML=R.sources.map(s=>`<article><a href="${s.url}" target="_blank" rel="noopener">${s.name} ↗</a><p>${s.feature}</p><p>${s.availability}</p></article>`).join('');
put('researchGenerated',`Research run ${new Date(R.generated_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'America/New_York'})}`);
consistency();render();
