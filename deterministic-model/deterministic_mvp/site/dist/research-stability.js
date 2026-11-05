/* This panel reads saved development diagnostics; it never fits or selects a model. */
(() => {
  const report = window.RESEARCH_DATA, S = report.stability;
  const get = id => document.getElementById(id);
  const pct = v => v == null ? '—' : `${(v * 100).toFixed(2)}%`;
  const number = v => v == null ? '—' : Number(Number(v).toPrecision(7)).toString();
  const date = d => new Date(`${d}T12:00:00`).toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric'});
  const assetKeys = ['equity', 'treasury', 'ig_credit'], assetNames = ['SPY', 'IEF', 'LQD'];
  const name = k => report.variants[k].name;
  get('stabilityModel').innerHTML = S.comparison_order.map(k => `<option value="${k}">${name(k)}</option>`).join('');
  get('stabilityModel').value = 'corrected';

  function chart(rows, reference, j, key) {
    const W=1000, H=340, p={l:74,r:24,t:24,b:38};
    const values = rows.flatMap((r,i) => [r.q[j], r.actual[j], reference[i].q[j]]);
    const low=Math.min(0,...values), high=Math.max(0,...values), pad=Math.max((high-low)*.08,.005);
    const lo=low-pad, hi=high+pad;
    const x=i=>p.l+i/Math.max(rows.length-1,1)*(W-p.l-p.r);
    const y=v=>p.t+(hi-v)/(hi-lo)*(H-p.t-p.b);
    const parts=[];
    for(let i=0;i<=4;i++) {
      const v=lo+i*(hi-lo)/4, yy=y(v);
      parts.push(`<line class="chart-grid" x1="${p.l}" x2="${W-p.r}" y1="${yy}" y2="${yy}"/><text class="chart-label" x="5" y="${yy+4}">${pct(v)}</text>`);
    }
    parts.push(`<line x1="${p.l}" x2="${W-p.r}" y1="${y(0)}" y2="${y(0)}" stroke="#aab6bd" stroke-dasharray="4 4"/>`);
    const line=(values,color,dashed=false)=>`<path d="${values.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2.4"${dashed?' stroke-dasharray="6 4"':''}/>`;
    parts.push(line(rows.map(r=>r.actual[j]),'#b44c26'), line(reference.map(r=>r.q[j]),'#64748b',true), line(rows.map(r=>r.q[j]),'#008aa1'));
    rows.forEach((r,i)=>parts.push(`<circle cx="${x(i)}" cy="${y(r.q[j])}" r="3" fill="#008aa1"><title>${date(r.holding_month)}: forecast ${pct(r.q[j])}; realized ${pct(r.actual[j])}; mean ${pct(reference[i].q[j])}</title></circle>`));
    [0,Math.floor((rows.length-1)/2),rows.length-1].forEach((i,n)=>parts.push(`<text class="chart-label" x="${x(i)}" y="${H-8}" text-anchor="${n===0?'start':n===2?'end':'middle'}">${date(rows[i].holding_month)}</text>`));
    get('stabilityChartTitle').textContent = `${assetNames[j]}: ${name(key)} vs. what happened`;
    get('stabilityChartNote').textContent = 'Monthly total returns before BL. Horizontal axis: holding month. The vertical scale fits the complete range for this selection; no extreme point is hidden. Values are also available in the downloaded report.';
    get('stabilityChart').innerHTML = parts.join('');
  }

  function render() {
    const cohort=S.cohorts[get('stabilityCohort').value], j=Number(get('stabilityAsset').value), asset=assetKeys[j], key=get('stabilityModel').value;
    const metrics=cohort.results, base=metrics.baseline;
    get('stabilityCoverage').textContent = `${base.months} matched forecast months (${base.asset_months} asset-months), decisions ${date(cohort.first_decision)}–${date(cohort.last_decision)}. All holding months end by December 2022.`;
    get('stabilityVerdict').textContent = report.primary.numerical_acceptance.passed ? 'The corrected primary passes the recorded numerical checks.' : 'The corrected primary needs attention: numerical checks failed.';
    const stable=['corrected','clip_only','robust'].filter(k=>metrics[k].extreme_asset_months===0);
    const worse=S.comparison_order.filter(k=>k!=='historical_mean' && Object.values(metrics[k].assets).every(a=>a.oos_r2_vs_historical_mean<0));
    get('stabilityFinding').textContent = `Across all three assets, ${stable.map(name).join(', ')} have no forecasts beyond ±20% in this sample. The coverage safeguard has ${metrics.supported_policy.extreme_asset_months} flagged asset-month(s); removing policy has ${metrics.no_policy.extreme_asset_months}. ${worse.length} of the ${S.comparison_order.length-1} learned versions have higher squared forecast error than the historical mean for every asset. Stability and predictive skill are evaluated separately.`;
    get('stabilityForecastTable').innerHTML=S.comparison_order.map(k=>{const m=metrics[k].assets[asset];return `<tr class="${k===key?'selected-row':''}"><td>${name(k)}</td><td>${pct(m.mae)}</td><td>${pct(m.rmse)}</td><td>${m.oos_r2_vs_historical_mean?.toFixed(3)??'—'}</td><td>${pct(m.largest_absolute_forecast)}<small class="research-type">${date(m.largest_forecast_decision)} decision</small></td><td>${m.extreme_count} / ${metrics[k].months} (${pct(m.extreme_rate)})</td></tr>`;}).join('');
    chart(cohort.timeline[key],cohort.timeline.historical_mean,j,key);
    get('stabilityEvents').innerHTML=S.comparison_order.flatMap(k=>cohort.extreme_events[k].map(e=>`<tr><td>${name(k)}</td><td>${date(e.decision_date)}</td><td>${assetNames[assetKeys.indexOf(e.asset)]}</td><td>${pct(e.forecast)}</td><td>${pct(e.actual)}</td><td>${e.dominant_feature?`${e.dominant_feature.feature}: ${pct(e.dominant_feature.contribution)}`:'—'}</td></tr>`)).join('') || '<tr><td colspan="6">No flags in this sample.</td></tr>';
    get('stabilityYears').innerHTML=S.calendar_years.map(y=>{const m=y.results[key],a=m.assets[asset];return `<tr><td>${y.year}${y.partial_year?' · partial':''}</td><td>${m.months}</td><td>${pct(a.rmse)}</td><td>${pct(y.results.historical_mean.assets[asset].rmse)}</td><td>${a.oos_r2_vs_historical_mean?.toFixed(3)??'—'}</td><td>${pct(a.largest_absolute_forecast)}</td></tr>`;}).join('');
    get('stabilityPortfolios').innerHTML=S.comparison_order.map(k=>{const m=report.development.results[k].stats,b=S.allocation_limits[k];return `<tr class="${k===key?'selected-row':''}"><td>${name(k)}</td><td>${pct(m.cumulative_return)}</td><td>${pct(m.maximum_drawdown)}</td><td>${pct(m.average_turnover)}</td><td>${m.cost_bps_sum.toFixed(1)} bp</td><td>${b.months_at_any_limit} / ${b.months} (${pct(b.fraction_at_any_limit)})</td></tr>`;}).join('');
  }

  const T=S.january_2020;
  get('stabilityCause').textContent=`The ${date(T.decision_date)} decision forecast ${pct(T.assets.equity.forecast)} for SPY during the February holding interval. The supplied workbook calculation reproduces it. The six-month policy-change field has only ${T.observed_values.length} finite training entries among ${T.training_rows} completed targets; ${T.missing_training_rows} earlier entries are median-imputed.`;
  get('stabilityCalculation').textContent=`Raw change ${number(T.raw_decision_input)} pp − training mean ${number(T.training_mean_after_imputation)} pp\n÷ training standard deviation ${number(T.training_std_after_imputation)} pp\n= ${T.standardized_input.toFixed(2)} training standard deviations`;
  get('stabilityMechanism').textContent=`The two observed changes are ${T.observed_values.map(number).join(' and ')} pp. Their observed-only standard deviation is ${number(T.observed_only_std)} pp; median imputation reduces the full fitted scale further. ${T.conclusion}`;
  get('stabilityReconstruction').innerHTML=assetKeys.map((a,j)=>{const m=T.assets[a];return `<tr><td>${assetNames[j]}</td><td>${pct(m.training_target_mean)}</td><td>${pct(m.sum_feature_contributions)}</td><td>${pct(m.reconstructed_forecast)}</td><td>${number(m.policy_change_coefficient)}</td><td>${pct(m.policy_change_contribution)}</td><td>${pct(m.realized)}</td></tr>`;}).join('');
  get('stabilityRawPolicy').innerHTML=T.raw_policy_snapshots.map(r=>`<tr><td>${r.sheet}</td><td>${date(r.source_date)}</td><td>${number(r.level_percentage_points)}</td><td>${number(r.change_percentage_points)}</td></tr>`).join('');
  get('stabilityTrainingPolicy').innerHTML=T.policy_training_rows.map(r=>`<tr><td>${date(r.date)}</td><td>${date(r.policy_data_date)}</td><td>${date(r.exit)}</td><td>${number(r.policy_6m_level)}</td><td>${number(r.policy_6m_change)}</td></tr>`).join('');
  get('stabilityUnits').textContent=T.units;
  get('stabilityMissing').textContent=T.missing_data;
  ['stabilityCohort','stabilityAsset','stabilityModel'].forEach(id=>get(id).addEventListener('change',render));
  render();
})();
