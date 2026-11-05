(() => {
  const D=window.HORIZON_DATA, get=id=>document.getElementById(id);
  const pct=v=>v==null?'—':`${v>=0?'+':''}${(v*100).toFixed(2)}%`;
  const pp=v=>`${(v*100).toFixed(2)} pp`;
  const date=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{month:'short',year:'numeric'});
  const names={corrected:'Corrected model',historical_mean:'Historical mean → BL',fixed453520:'Fixed 45 / 35 / 20',sixtyForty:'Fixed 60% SPY / 40% IEF',spyOnly:'100% SPY'};
  const assets={equity:'SPY · U.S. stocks',treasury:'IEF · U.S. Treasuries',ig_credit:'LQD · corporate bonds'};
  function summaryRow(label,d){const corrected=d.portfolio_results?.corrected?.cumulative_return??d.cumulative_return;const mean=d.portfolio_results?.historical_mean?.cumulative_return??d.historical_mean_return;return `<tr><th scope="row">${label}</th><td>${d.eligible_forecasts}</td><td>${d.portfolio_holdings}</td><td>${pct(corrected)}</td><td>${pct(mean)}</td><td>${date(d.target_last_month||d.last_holding_month)}</td></tr>`;}
  get('horizonSummary').innerHTML=summaryRow('1 month · frozen primary',D.one_month)+Object.entries(D.horizons).map(([key,d])=>summaryRow(`${key} months · corrected extension`,d)).join('');
  get('horizonHeadline').textContent=`The 3-month corrected portfolio returned ${pct(D.horizons['3'].portfolio_results.corrected.cumulative_return)} across ${D.horizons['3'].portfolio_holdings} non-overlapping holdings; the 6-month result returned ${pct(D.horizons['6'].portfolio_results.corrected.cumulative_return)} across only ${D.horizons['6'].portfolio_holdings}. These portfolio samples are shorter than the monthly forecast samples and should be read descriptively.`;
  const select=get('horizonSelect');
  if(!select.value)select.value='3';
  function render(){
    const key=select.value,d=D.horizons[key],scores=d.forecast_scores;
    get('horizonForecastTable').innerHTML=Object.entries(scores.assets).map(([asset,v])=>`<tr><th scope="row">${assets[asset]}</th><td>${pp(v.mae)}</td><td>${pp(v.rmse)}</td><td>${v.oos_r2_vs_historical_mean.toFixed(3)}</td><td>${pct(v.forecast_min)} to ${pct(v.forecast_max)}</td></tr>`).join('');
    get('horizonForecastNote').textContent=`${scores.months} eligible monthly forecasts from ${date(d.target_first_month)} through ${date(d.target_last_month)}. ${scores.extreme_asset_months} of ${scores.asset_months} asset forecasts crossed the unchanged ±20% inspection threshold; largest absolute forecast was ${pct(scores.largest_absolute_forecast)}. Positive OOS R² means squared errors beat the same-date expanding historical mean.`;
    get('horizonPortfolioTable').innerHTML=Object.entries(d.portfolio_results).map(([k,v])=>`<tr class="${k==='corrected'?'selected-row':''}"><th scope="row">${names[k]||k}</th><td>${v.holding_periods}</td><td>${pct(v.cumulative_return)}</td><td>${pct(v.maximum_drawdown)}</td><td>${pct(v.average_turnover)}</td><td>${v.cost_bps_sum.toFixed(1)} bp</td></tr>`).join('');
  }
  select.addEventListener('change',render); render();
  get('horizonGenerated').textContent=`Run ${new Date(D.generated_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}`;
})();
