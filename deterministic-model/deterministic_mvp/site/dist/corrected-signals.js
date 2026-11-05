(() => {
  const D=window.CORRECTED_SIGNALS_DATA,get=id=>document.getElementById(id);
  const pct=v=>`${v>=0?'+':''}${(v*100).toFixed(2)}%`,pp=v=>`${v>=0?'+':''}${(v*100).toFixed(2)} pp`;
  const base=D.variants.baseline;
  const labels={baseline:'Corrected baseline',claims:'+ Unemployment claims',credit:'+ Credit spread',curve:'+ Yield curve'};
  const assets={equity:'SPY',treasury:'IEF',ig_credit:'LQD'};
  get('correctedSignalScope').textContent=`${D.sample.holdings} matched holding months · corrected model · development through December 2022`;
  get('correctedSignalTable').innerHTML=Object.entries(D.variants).map(([key,v])=>`<tr class="${key==='baseline'?'selected-row':''}"><th scope="row">${labels[key]}</th><td>${pct(v.return)}</td><td>${pp(v.return-base.return)}</td><td>${pct(v.drawdown)}</td><td>${pct(v.turnover)}</td><td>${pct(v.largest_forecast)}</td><td>${v.extreme_flags}</td></tr>`).join('');
  get('correctedSignalHeadline').textContent=`On the corrected model, claims returned ${pct(D.variants.claims.return)}, credit returned ${pct(D.variants.credit.return)} and the yield curve returned ${pct(D.variants.curve.return)}, versus ${pct(base.return)} for the corrected baseline. These are development portfolio comparisons; they do not establish forecast skill by themselves.`;
  get('correctedSignalForecastTable').innerHTML=Object.entries(D.variants).map(([key,v])=>`<tr class="${key==='baseline'?'selected-row':''}"><th scope="row">${labels[key]}</th>${Object.entries(v.assets).map(([asset,m])=>`<td>${assets[asset]}: ${m.oos_r2_vs_historical_mean.toFixed(3)} R²<br><small>MAE ${pp(m.mae)}</small></td>`).join('')}</tr>`).join('');
  get('correctedSignalNote').textContent=`Each row uses ${base.forecast_months} matched monthly forecast dates and the same corrected preprocessing, policy eligibility checks, Ridge tuning and portfolio rules. No 2023-onward target was evaluated. The earlier original-model signal results remain available below for comparison.`;
  get('correctedSignalGenerated').textContent=`Corrected signal rerun ${new Date(D.generated_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}`;
})();
