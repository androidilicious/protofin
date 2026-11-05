/* Present the fixed primary specification and its saved development evidence. */
(() => {
  const R=window.RESEARCH_DATA, P=R.primary, F=window.PRIMARY_FREEZE;
  const get=id=>document.getElementById(id), pct=v=>`${(v*100).toFixed(2)}%`;
  const date=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'});
  const month=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{year:'numeric',month:'short'});
  const pp=v=>`${(v*100).toFixed(2)} pp`;
  const names={corrected:'Updated model',historical_mean:'Past-average forecast',fixed453520:'Fixed 45% SPY / 35% IEF / 20% LQD',sixtyForty:'Fixed 60% SPY / 40% IEF',spyOnly:'SPY only',prior_only:'Portfolio without model forecasts',clip_only:'Input limits only · earlier check',baseline:'Original model · unstable predictions'};
  const policyNames={policy_3m_level:'Expected policy rate · 3 months',policy_6m_level:'Expected policy rate · 6 months',policy_path_slope:'Difference between the 6- and 3-month rates',policy_3m_change:'Change in the expected 3-month rate',policy_6m_change:'Change in the expected 6-month rate'};
  const reasons={insufficient_source_history:'Too few original observations',insufficient_distinct_values:'Too few distinct values',near_constant_observations:'Observed values change too little',near_constant_processed_training:'Values change too little after processing',constant_processed_training:'No usable variation after processing'};
  const full=R.stability.cohorts.all_forecasts.results.corrected;
  const allocated=R.stability.cohorts.portfolio_dates.results;
  const stats=P.portfolio_results.corrected;
  const skillCount=Object.values(P.predictive_claims).filter(Boolean).length;
  get('primaryVerdict').textContent=!P.numerical_acceptance.passed ? 'The prediction checks failed. Review the model before final testing.' : skillCount===0 ? 'After the fix, the simple forecast still wins on accuracy.' : 'The prediction checks passed. Accuracy gains vary by asset.';
  get('primaryConclusion').textContent=`${skillCount===0?'None of the three assets passed our checks for better forecasts than the past-average approach.':`${skillCount} of three assets passed our checks for better forecasts than the past-average approach.`} We report the updated results without changing the rules to recover the original return. These are development results; final testing is still ahead.`;
  get('primaryReturn').textContent=pct(stats.cumulative_return);
  get('primaryMeanReturn').textContent=pct(P.portfolio_results.historical_mean.cumulative_return);
  const decisions=R.development.results.corrected.decisions;
  get('primaryDates').textContent=`${stats.months} months compared · ${month(decisions[0].holding_month)}–${month(decisions.at(-1).holding_month)}`;
  get('primaryMaxForecast').textContent=pct(full.largest_absolute_forecast);
  get('primaryWarningCount').textContent=`${full.extreme_asset_months} of ${full.asset_months} predictions were above +20% or below −20%`;
  get('primaryDrawdown').textContent=pct(stats.maximum_drawdown);
  const assets=['equity','treasury','ig_credit'], labels=['SPY · U.S. stocks','IEF · U.S. Treasuries','LQD · corporate bonds'];
  get('primaryAccuracy').innerHTML=assets.map((a,j)=>`<tr><td>${labels[j]}</td><td>${pp(allocated.corrected.assets[a].mae)}</td><td>${pp(allocated.historical_mean.assets[a].mae)}</td></tr>`).join('');
  get('primaryAccuracyDetails').innerHTML=assets.map((a,j)=>{const m=allocated.corrected.assets[a],b=allocated.historical_mean.assets[a];return `<tr><td>${labels[j]}</td><td>${pp(m.mae)}</td><td>${pp(b.mae)}</td><td>${pp(m.rmse)}</td><td>${pp(b.rmse)}</td><td>${m.oos_r2_vs_historical_mean.toFixed(3)}</td><td>${full.assets[a].oos_r2_vs_historical_mean.toFixed(3)}</td><td>${P.predictive_claims[a]?'Yes':'No'}</td></tr>`;}).join('');
  get('primaryPortfolioTable').innerHTML=P.comparisons.map(k=>{const s=P.portfolio_results[k];return `<tr class="${k==='corrected'?'selected-row':''}"><td>${names[k]||R.variants[k].name}${k==='baseline'?'<small class="research-type">Earlier result, shown for comparison only</small>':''}</td><td>${pct(s.cumulative_return)}</td><td>${pct(s.maximum_drawdown)}</td><td>${pct(s.average_turnover)}</td><td>${s.cost_bps_sum.toFixed(1)} bp</td></tr>`;}).join('');
  get('primaryPolicyDate').innerHTML=P.policy_activation.map(r=>`<option value="${r.decision_date}">${date(r.decision_date)}</option>`).join('');
  function policyTable(){
    const row=P.policy_activation.find(r=>r.decision_date===get('primaryPolicyDate').value);
    get('primaryPolicyTable').innerHTML=row.policy_features.map(f=>`<tr><td>${policyNames[f.feature]||f.feature}</td><td>${f.unique_source_observations}</td><td>${f.distinct_resolution_bins}</td><td>${f.observed_source_std.toFixed(5)}</td><td>${f.processed_training_std.toFixed(5)}</td><td>${f.enabled?'Yes':f.disabled_reasons.map(r=>reasons[r]||r.replaceAll('_',' ')).join('; ')}</td></tr>`).join('');
  }
  // Start with the diagnosed decision so readers see why policy is disabled.
  get('primaryPolicyDate').value=P.policy_activation.find(r=>r.decision_date==='2020-01-31')?.decision_date || P.policy_activation[0].decision_date;
  get('primaryPolicyDate').addEventListener('change',policyTable);policyTable();
  get('primaryFreezeStatus').textContent=`${F.id} · rules locked on ${new Date(F.frozen_at_utc).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric',timeZone:'America/New_York'})}. The prediction checks passed. The final test has not been run.`;
  get('primaryFreezeHash').textContent=`The saved record identifies the exact rules, model code and source data, so changes can be detected before final testing. Rules SHA-256: ${P.specification_sha256}.`;
})();
