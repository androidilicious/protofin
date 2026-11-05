/* Explain saved corrected-model decisions; never fit a model or read reserved outcomes. */
(() => {
  const R=window.RESEARCH_DATA;
  const rows=R.development.results.corrected.decisions;
  if(!rows.length||rows.some(d=>d.holding_month>'2022-12-31'))throw new Error('Walkthrough requires development-only decisions');
  const get=id=>document.getElementById(id), select=get('walkthroughMonth');
  const assets=['SPY · U.S. stocks','IEF · U.S. Treasuries','LQD · Corporate bonds'];
  const spec=R.primary.specification.portfolio;
  const date=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  const month=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{month:'short',year:'numeric'});
  const pct=(v,signed=false)=>`${signed&&v>=.00005?'+':''}${(Math.abs(v)<.00005?0:v*100).toFixed(2)}%`;
  const weight=v=>`${(v*100).toFixed(1)}%`;
  const number=v=>Number.isFinite(v)?v.toFixed(2):'Missing';
  // Keep the same symmetric scale while switching dates, even for very small views.
  const scale=Math.max(.05,Math.ceil(Math.max(...rows.flatMap(d=>[...d.forecast,...d.posterior].map(Math.abs)))*100)/100);
  function returnCell(value,stage){
    const width=Math.abs(value)/scale*50;
    return `<div class="return-estimate"><b>${pct(value,true)}</b><span class="return-track" aria-hidden="true"><i class="${stage}" style="left:${value<0?50-width:50}%;width:${width}%"></i></span></div>`;
  }
  select.innerHTML=rows.map(d=>`<option value="${d.decision_date}">${date(d.decision_date)} → ${month(d.holding_month)} holding</option>`).join('');
  function render(){
    const index=rows.findIndex(d=>d.decision_date===select.value), d=rows[index];
    const inputs=R.signal_observations.find(s=>s.decision_date===d.decision_date);
    const policy=R.primary.policy_activation.find(s=>s.decision_date===d.decision_date);
    const previous=index?rows[index-1]:null;
    const before=previous?previous.weights.map((w,j)=>w*(1+previous.actual[j])/(1+previous.gross_return)):spec.starting_weights;
    get('walkthroughTiming').innerHTML=`<span><small>Decision · 8 p.m. New York</small><b>${date(d.decision_date)}</b></span><span><small>Enter · next trading-day close</small><b>${date(d.entry)}</b></span><span><small>Exit · next rebalance close</small><b>${date(d.exit)}</b></span>`;
    get('walkthroughInputs').innerHTML=[
      ['Growth surprise',number(inputs?.growth_surprise),'Average standardized release surprise'],
      ['Inflation surprise',number(inputs?.inflation_surprise),'Average standardized release surprise'],
      ['Financial conditions (ANFCI)',number(inputs?.anfci),'Index value'],
      ['Geopolitical risk (GPR)',number(inputs?.gpr),'Index value'],
    ].map(([label,value,unit])=>`<div><dt>${label}<small>${unit}</small></dt><dd>${value}</dd></div>`).join('');
    const enabled=policy.policy_features.filter(f=>f.enabled).length;
    get('walkthroughPolicy').textContent=`${enabled} of ${policy.policy_features.length} policy fields passed the history and variation checks for this decision. Inactive fields contribute zero. Policy inputs describe expected rates in 3 and 6 months; the return target is still one month.`;
    get('walkthroughTraining').textContent=`The forecast used ${d.training_rows} completed monthly training observations. The latest training return ended on ${date(d.last_training_exit)}, before the ${date(d.decision_date)} decision.`;
    get('walkthroughErrorHistory').textContent=`The latest completed outcome used in the forecast-error history ended on ${date(d.last_error_exit)}. The upcoming holding period could not enter this uncertainty estimate.`;
    get('walkthroughReturns').innerHTML=assets.map((a,j)=>`<tr><th scope="row">${a}</th><td>${returnCell(d.forecast[j],'raw')}</td><td>${returnCell(d.posterior[j],'adjusted')}</td><td>${(Math.sqrt(d.view_error_variance[j])*100).toFixed(2)} pp</td></tr>`).join('');
    get('walkthroughReturnScale').textContent=`Bar scale: −${(scale*100).toFixed(0)}% to +${(scale*100).toFixed(0)}%, with zero at the center. Purple: raw Ridge. Teal: after Black–Litterman. Values are return estimates, not portfolio weights.`;
    get('walkthroughWeights').innerHTML=assets.map((a,j)=>`<div class="weight-readout"><div><b>${a}</b><strong>${weight(d.weights[j])}</strong></div><div class="weight-track" aria-hidden="true"><i style="width:${d.weights[j]*100}%"></i><span style="left:${spec.starting_weights[j]*100}%"></span></div><small>Reference ${weight(spec.starting_weights[j])} · before trade ${weight(before[j])}</small></div>`).join('');
    get('walkthroughTrading').textContent=`Total absolute weight traded: ${weight(d.turnover)}. At ${spec.cost_bps_per_dollar_traded} bp per dollar traded, the entry cost was ${(d.cost*10000).toFixed(2)} bp of portfolio capital. Reference markers on the bars show the 45 / 35 / 20 mix.`;
    get('walkthroughOutcome').open=false;
    get('walkthroughOutcomeValues').innerHTML=`<p>Observed from ${date(d.entry)} close to ${date(d.exit)} close:</p><dl class="input-readout">${assets.map((a,j)=>`<div><dt>${a}</dt><dd>${pct(d.actual[j],true)}</dd></div>`).join('')}</dl><p>Portfolio before costs: <strong>${pct(d.gross_return,true)}</strong><br>Portfolio after costs: <strong>${pct(d.net_return,true)}</strong></p><p class="evidence-note">Net return = (1 − entry cost) × (1 + weighted asset return) − 1. These are holding-period returns, not calendar-month close-to-close returns.</p>`;
  }
  select.value=rows[0].decision_date;
  select.addEventListener('change',render);
  render();
})();
