const R = window.RESEARCH_DATA;
const modelKeys = Object.keys(R.variants).filter(k=>R.variants[k].kind==='model');
const periods = [{id:'development', name:'Full development history', description:'Primary comparison: every common eligible holding month through December 2022. Strategies run continuously before episode slices.', ...R.development}, ...R.periods];
const allKeys = Object.keys(R.variants);
const el = id => document.getElementById(id);
const put = (id, text) => { el(id).textContent = text; };
const percent = (v, digits=2) => v == null ? '—' : `${(v*100).toFixed(digits)}%`;
const pp = v => { const rounded=Math.abs(v)<.00005?0:v; return `${rounded > 0 ? '+' : ''}${(rounded*100).toFixed(2)} pp`; };
const dateLabel = d => new Date(`${d}T12:00:00`).toLocaleDateString('en-US', {month:'short',day:'numeric',year:'numeric'});
const monthLabel = d => new Date(`${d}T12:00:00`).toLocaleDateString('en-US', {month:'short',year:'numeric'});
let periodId = 'development';
let variantId = 'baseline';
let referenceId = 'historical_mean';
const featureInfo = {
  clip_only: {label:'Isolate preprocessing', title:'Clip extreme inputs only', description:'Keep the original Ridge grid and signals. Only training-fold input clipping changes, so its effect can be compared with stronger shrinkage.', formula:'Clip features to training 1st / 99th percentiles; α = 0.01, 0.1, 1, 10, 100.', timing:'Quantiles and scaling are fitted only on completed training data inside each validation fold.'},
  shrink_only: {label:'Isolate regularization', title:'Apply stronger shrinkage only', description:'Keep original inputs without clipping. Only the Ridge penalty grid changes.', formula:'No input clipping; α = 1, 10, 100, 1000.', timing:'Penalties are selected with the same completed-target chronological validation.'},
  supported_policy: {label:'Sparse-history safeguard', title:'Require observed policy history before using a policy feature', description:'Each policy feature is disabled until that training fold contains 12 observed values. Imputed entries do not count toward the threshold.', formula:'Observed policy training values < 12 → feature contribution fixed at zero. Original Ridge grid; no clipping.', timing:'The observation count is recomputed inside every training and validation fold. This is a fixed sensitivity check, not a chosen production policy.'},
  robust: {label:'Fixed robustness check', title:'Reduce input extrapolation and increase shrinkage', description:'The original signals are retained. This separately labeled sensitivity uses training-only input clipping and a stronger Ridge grid; it is not selected from episode returns.', formula:'Clip each input to its training 1st / 99th percentiles. Tune only over α = 1, 10, 100, 1000.', timing:'Quantiles, imputation and scaling are refit inside every chronological tuning fold. No predicted-return cap.'},
  no_policy: {label:'Missing-history sensitivity', title:'Remove the sparse policy-path fields', description:'The five policy fields are excluded over exactly the same dates. This tests how much the baseline depends on policy history beginning in September 2019.', formula:'Growth / inflation surprises + ANFCI / GPR and their existing interactions → Ridge → BL.', timing:'Same training, target-availability, covariance, trading and cost rules. It cannot reconstruct unavailable policy history.'},
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
  const pooled = result => {
    const values = Object.values(result.forecast_diagnostics || {});
    return values.length ? Math.sqrt(values.reduce((sum,d)=>sum+d.rmse*d.rmse,0)/values.length) : null;
  };
  const rmse=selected.forecast_rmse ?? pooled(period.results[variantId]);
  const baseRmse=base.forecast_rmse ?? pooled(period.results.baseline);
  el('researchExplanation').innerHTML=`<p class="kicker">Reading this result</p><h3>${period.name}: what changed?</h3><div class="research-explanation-grid"><div><h4>Return</h4><p>${returnStatement}</p></div><div><h4>Risk and recovery</h4><p>${riskStatement} ${recovery}</p></div></div><p><strong>Across the model experiments:</strong> ${R.variants[best.key].name} had the highest total return in this window (${percent(best.stats.cumulative_return)}). This is a description of this episode, not a selection of a new model.</p><details><summary>Inspect forecast accuracy before Black–Litterman</summary><p>Selected model Ridge RMSE: ${percent(rmse)}. Original model: ${percent(baseRmse)}. This is the pooled root mean squared error across all three assets and holding months, before BL moderation. Lower is better.${rmse>.2?' Raw Ridge forecasts were unstable within this selected period. Large errors show extrapolation risk; BL moderation and allocation limits reduce the influence of these views.':''}</p></details>`;
}

function decisionRows(period) {
  const signalName={baseline:'Existing macro inputs',claims:'Claims change, 3 months',credit:'Credit spread / 1m change',curve:'10y − 3m yield spread',robust:'Original inputs with robust preprocessing',no_policy:'Original inputs without policy fields',clip_only:'Original inputs with clipping only',shrink_only:'Original inputs with stronger shrinkage',supported_policy:'Original inputs with policy coverage safeguard'};
  put('signalColumn',signalName[variantId]);
  el('researchDecisions').innerHTML=period.results[variantId].decisions.map(d=>{
    const s=R.signal_observations.find(r=>r.date===d.date);
    let value='No added signal';
    if(s && variantId==='claims')value=percent(s.claims_change_3m);
    if(s && variantId==='credit')value=`${s.credit_level.toFixed(2)} pp / ${s.credit_change_1m.toFixed(2)} pp`;
    if(s && variantId==='curve')value=`${s.curve_level.toFixed(2)} pp`;
    return `<tr><td>${dateLabel(d.decision_date)}</td><td>${dateLabel(d.entry)} → ${dateLabel(d.exit)}</td><td>${value}</td><td>${d.weights.map(w=>percent(w,0)).join(' / ')}</td><td>${d.forecast.map(v=>percent(v)).join(' / ')}</td><td>${d.posterior.map(v=>percent(v)).join(' / ')}</td><td>${d.view_error_variance.map(v=>percent(Math.sqrt(v))).join(' / ')}</td><td>${percent(d.net_return)}</td></tr>`;
  }).join('');
}

function render() {
  const period=periods.find(p=>p.id===periodId), chosen=period.results[variantId], s=chosen.stats, f=featureInfo[variantId];
  document.querySelectorAll('[data-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.period===periodId)));
  put('periodName',period.name);put('periodDescription',period.description);put('holdingDates',`${s.months} monthly holdings · ${dateLabel(s.entry)} to ${dateLabel(s.exit)}`);
  put('featureLabel',f.label);put('featureTitle',f.title);put('featureDescription',f.description);put('featureFormula',f.formula);put('featureTiming',f.timing);
  put('researchReturn',percent(s.cumulative_return));put('researchEndValue',`$100 became $${s.end_value.toFixed(2)}`);put('researchDrawdown',percent(s.maximum_drawdown));put('researchDifference',pp(s.difference_vs_baseline));put('researchTurnover',percent(s.average_turnover));
  el('researchTable').innerHTML=allKeys.map(k=>{const a=period.results[k].stats;return `<tr class="${k===variantId?'selected-row':''}"><td>${R.variants[k].name}<small class="research-type">${R.variants[k].kind==='model'?'Three-asset experiment':R.variants[k].kind==='model_reference'?'Model reference':'Passive reference'}</small></td><td>${percent(a.cumulative_return)}</td><td>${percent(a.maximum_drawdown)}</td><td>${pp(a.difference_vs_baseline)}</td><td>${percent(a.annualized_volatility)}</td><td>${percent(a.average_turnover)}</td></tr>`;}).join('');
  chart(period);explain(period);decisionRows(period);auditRows(period);developmentChecks();inferenceChecks(period);
}

function consistency() {
  el('episodeMatrix').innerHTML=['claims','credit','curve'].map(k=>`<tr><td>${R.variants[k].name}</td>${R.periods.map(p=>{const v=p.results[k].stats.difference_vs_baseline;return `<td class="${v>=0?'positive-delta':'negative-delta'}">${pp(v)}</td>`;}).join('')}</tr>`).join('');
  const windows=R.rolling_windows;
  put('rollingCoverage',`${windows.length} overlapping windows of 12 holding months, from ${monthLabel(windows[0].start)}–${monthLabel(windows[0].end)} through ${monthLabel(windows.at(-1).start)}–${monthLabel(windows.at(-1).end)}.`);
  el('rollingTable').innerHTML=['claims','credit','curve'].map(k=>{const diffs=windows.map(w=>w.results[k].cumulative_return-w.results.baseline.cumulative_return).sort((a,b)=>a-b);const wins=diffs.filter(v=>v>1e-8).length,n=diffs.length;const median=n%2?diffs[(n-1)/2]:(diffs[n/2-1]+diffs[n/2])/2;return `<tr><td>${R.variants[k].name}</td><td>${wins} / ${n} (${(100*wins/n).toFixed(0)}%)</td><td>${pp(median)}</td><td>${pp(diffs[0])}</td></tr>`;}).join('');
}

function auditRows(period) {
  const diagnostics = period.results[variantId].forecast_diagnostics || {};
  const labels = {equity:'SPY', treasury:'IEF', ig_credit:'LQD'};
  el('forecastAudit').innerHTML = Object.entries(diagnostics).map(([asset,d])=>`<tr><td>${labels[asset]}</td><td>${percent(d.rmse)}</td><td>${percent(d.mae)}</td><td>${percent(d.bias)}</td><td>${percent(d.forecast_min)} to ${percent(d.forecast_max)}</td><td>${percent(d.realized_min)} to ${percent(d.realized_max)}</td><td>${d.forecast_over_20pct_months} / ${d.observations}</td></tr>`).join('');
  el('extremeForecastAudit').innerHTML = Object.entries(diagnostics).map(([asset,d])=>`<details class="research-details"><summary>${labels[asset]}: largest forecast error, decision ${dateLabel(d.worst_decision)}</summary><p>Forecast ${percent(d.worst_forecast)}; realized ${percent(d.worst_realized)}. The training mean contributes ${percent(d.worst_intercept)}. Feature contributions below sum with the training mean to reconstruct this forecast. Sparse training coverage can amplify extrapolation.</p><div class="comparison-table-wrap"><table><thead><tr><th>Feature</th><th>Forecast contribution</th><th>Input in training std. units</th><th>Observed training rows</th><th>Input clipped?</th><th>Enabled?</th></tr></thead><tbody>${d.worst_features.map(f=>`<tr><td>${f.feature}</td><td>${pp(f.contribution)}</td><td>${f.standardized_input.toFixed(2)}</td><td>${f.observed_training_rows}</td><td>${f.input_clipped?'Yes':'No'}</td><td>${f.enabled?'Yes':'No · sparse history'}</td></tr>`).join('')}</tbody></table></div></details>`).join('');
  const dates = new Set(period.results[variantId].decisions.map(d=>d.date));
  const rows = (R.monthly_attribution[variantId] || []).filter(d=>dates.has(d.date));
  const triple = values => values.map(v=>(v*100).toFixed(2)).join(' / ');
  el('monthlyAttribution').innerHTML = rows.length ? rows.map(d=>`<tr><td>${monthLabel(d.holding_month)}</td><td>${triple(d.forecast_delta)}</td><td>${triple(d.posterior_delta)}</td><td>${triple(d.weight_delta)}</td><td>${triple(d.asset_return_contribution)}</td><td>${pp(d.cost_effect)}</td><td>${pp(d.net_return_difference)}</td></tr>`).join('') : '<tr><td colspan="7">Select an added condition or robustness check to inspect changes versus the original model.</td></tr>';
}

function developmentChecks() {
  el('calendarYears').innerHTML = R.calendar_years.map(y=>{
    const base=y.results.baseline, selected=y.results[variantId];
    return `<tr><td>${y.year}${y.partial_year?` · partial (${base.months} months)`:''}</td><td>${percent(base.cumulative_return)}</td><td>${percent(selected.cumulative_return)}</td><td>${pp(selected.cumulative_return-base.cumulative_return)}</td><td>${percent(y.results.historical_mean.cumulative_return)}</td><td>${percent(y.results.prior_only.cumulative_return)}</td></tr>`;
  }).join('');
  const x=R.excluding_2020.results, selected=x[variantId], base=x.baseline;
  put('excludingCovid',`Excluding all 2020 holding months: selected ${percent(selected.cumulative_return)}, original ${percent(base.cumulative_return)} (${pp(selected.cumulative_return-base.cumulative_return)}) over ${selected.months} retained months. ${R.excluding_2020.description}`);
}

function inferenceChecks(period) {
  const interval = row => `${pp(row.lower)} to ${pp(row.upper)}`;
  const B=R.paired_block_bootstrap;
  el('bootstrapTable').innerHTML=modelKeys.filter(k=>k!=='baseline').map(k=>{const rows=B.results[k];return `<tr class="${k===variantId?'selected-row':''}"><td>${R.variants[k].name}</td><td>${pp(rows[0].mean_monthly_difference)}</td>${rows.map(r=>`<td>${interval(r)}</td>`).join('')}</tr>`;}).join('');
  el('leaveEpisodeOut').innerHTML=R.leave_episode_out.map(e=>{const a=e.results[variantId],b=e.results.baseline;return `<tr><td>${e.name}</td><td>${a.months}</td><td>${percent(b.cumulative_return)}</td><td>${percent(a.cumulative_return)}</td><td>${pp(a.cumulative_return-b.cumulative_return)}</td></tr>`;}).join('');
  el('boundaryChecks').innerHTML=R.episode_boundary_checks.map(e=>{const a=e.results[variantId],b=e.results.baseline;return `<tr><td>${e.name}</td><td>${e.requested_start} → ${e.requested_end}</td><td>${e.complete?a.months:'—'}</td><td>${e.complete?pp(a.cumulative_return-b.cumulative_return):'—'}</td><td>${e.complete?'Complete':'Not evaluated · outside development history'}</td></tr>`;}).join('');
  const C=R.credit_shared_information;
  put('creditCoverage',`${C.months} common development dates; ANFCI projection is fitted on earlier feature observations only.`);
  el('creditOverlap').innerHTML=Object.entries(C.features).map(([key,d])=>`<tr><td>${key==='credit_level'?'Baa–Treasury spread level':'Monthly spread change'}</td><td>${d.correlation_with_anfci_level.toFixed(3)}</td><td>${d.out_of_sample_r2_vs_expanding_mean.toFixed(3)}</td></tr>`).join('');
  const last=period.results[variantId].decisions.at(-1);
  const signal=R.signal_observations.find(s=>s.date===last.date);
  put('freshnessCutoff',`Decision cutoff: ${dateLabel(last.decision_date)}. Policy after-cutoff withholding: ${signal.policy_withheld_after_cutoff?'Yes':'No'}.`);
  const sourceKeys=['claims','credit','curve','anfci','gpr'];
  el('inputFreshness').innerHTML=sourceKeys.map(key=>{const source=signal[`${key}_source_date`],available=signal[`${key}_available_date`]||signal[`${key}_assumed_available_date`];const days=Math.round((new Date(`${last.decision_date}T12:00:00`)-new Date(`${source}T12:00:00`))/86400000);return `<tr><td>${key.toUpperCase()}</td><td>${dateLabel(source)}</td><td>${dateLabel(available)}</td><td>${days} days</td></tr>`;}).join('');
}

const developmentStats=R.development.results.baseline.stats;
const developmentDecisions=R.development.results.baseline.decisions;
put('developmentSummary',`${developmentStats.months} common holding months, ${monthLabel(developmentDecisions[0].holding_month)}–${monthLabel(developmentDecisions.at(-1).holding_month)}. The original returned ${percent(developmentStats.cumulative_return)}; the historical-mean reference returned ${percent(R.development.results.historical_mean.stats.cumulative_return)}.`);
el('unitAudit').innerHTML=Object.entries(R.unit_audit).map(([key,value])=>`<p><strong>${key.replaceAll('_',' ')}:</strong> ${value}</p>`).join('');
el('referenceSelect').value=referenceId;

el('periodTabs').innerHTML=periods.map((p,i)=>`<button type="button" data-period="${p.id}" aria-pressed="${i===0}"><span>0${i+1}</span>${p.name}</button>`).join('');
document.querySelectorAll('[data-period]').forEach(b=>b.addEventListener('click',()=>{periodId=b.dataset.period;render();}));
el('variantSelect').addEventListener('change',e=>{variantId=e.target.value;render();});
el('referenceSelect').addEventListener('change',e=>{referenceId=e.target.value;render();});
el('researchSources').innerHTML=R.sources.map(s=>`<article><a href="${s.url}" target="_blank" rel="noopener">${s.name} ↗</a><p>${s.feature}</p><p>${s.availability}</p></article>`).join('');
put('researchGenerated',`Research run ${new Date(R.generated_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'America/New_York'})}`);
consistency();render();
