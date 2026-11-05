(() => {
  const R=window.RESEARCH_DATA, M=window.MODEL_COMPARISON_DATA, get=id=>document.getElementById(id);
  const month=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{month:'short',year:'numeric'});
  const rows=R.development.results.baseline.decisions;
  get('frameworkSignalSample').textContent=`${rows.length} holdings · ${month(rows[0].holding_month)}–${month(rows.at(-1).holding_month)}`;
  get('frameworkModelSample').textContent=`${M.sample.common_portfolio_months} holdings · ${month(M.sample.first_holding_month)}–${month(M.sample.last_holding_month)}; ${M.sample.common_forecast_months} common forecasts including warm-up`;
  get('unitAudit').innerHTML=Object.entries(R.unit_audit).map(([key,value])=>`<p><strong>${key.replaceAll('_',' ')}:</strong> ${value}</p>`).join('');
  get('researchSources').innerHTML=R.sources.map(s=>`<article><a href="${s.url}" target="_blank" rel="noopener">${s.name} ↗</a><p>${s.feature}</p><p>${s.availability}</p></article>`).join('');
  get('researchGenerated').textContent=`Research run ${new Date(R.generated_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'America/New_York'})}`;
})();
