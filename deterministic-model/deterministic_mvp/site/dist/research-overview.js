(() => {
  const R=window.RESEARCH_DATA, M=window.MODEL_COMPARISON_DATA;
  const get=id=>document.getElementById(id), pct=v=>`${(v*100).toFixed(2)}%`;
  const month=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{month:'short',year:'numeric'});
  const rows=R.development.results.baseline.decisions;
  get('overviewSignalScope').textContent=`3 added-signal tests · ${rows.length} common holdings · ${month(rows[0].holding_month)}–${month(rows.at(-1).holding_month)}`;
  get('overviewModelScope').textContent=`4 core forecasts + 2 Ridge extensions · ${M.sample.common_portfolio_months} common holdings · ${month(M.sample.first_holding_month)}–${month(M.sample.last_holding_month)}`;
  const base=R.development.results.baseline.stats.cumulative_return;
  const improvements=['claims','credit','curve'].filter(k=>R.development.results[k].stats.cumulative_return>base).length;
  get('overviewSignalFinding').textContent=`In the initial signal study, ${improvements} of 3 additions increased total portfolio return over the original baseline on the full common development sample. This is a result for that study’s model and dates, not proof that those signals can never help.`;
  const p=R.primary.portfolio_results;
  get('overviewReliabilityFinding').textContent=`The evaluation uncovered extreme forecasts. A separately corrected reference model returned ${pct(p.corrected.cumulative_return)}, versus ${pct(p.historical_mean.cumulative_return)} for the past-average forecast portfolio on the same dates. It had no forecasts beyond the 20% warning threshold, but did not meet the recorded accuracy-improvement rule for any asset.`;
  get('overviewGenerated').textContent=`Development evidence through ${month(rows.at(-1).holding_month)} · reserved test not run`;
})();
