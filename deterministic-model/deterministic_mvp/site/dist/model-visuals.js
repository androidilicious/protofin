/* Explain recorded decisions; controls never change forecasts or trading rules. */
window.ModelVisuals=(()=>{
 const $=id=>document.getElementById(id);
 const put=(id,text)=>{$(id).textContent=text;};
 const assets=['equity','treasury','ig_credit'];
 const names={equity:'SPY',treasury:'IEF',ig_credit:'LQD'};
 const colors={equity:'#007f86',treasury:'#426eb4',ig_credit:'#b17b24'};
 const featureNames={growth_surprise:'Growth surprise',inflation_surprise:'Inflation surprise',anfci:'Financial conditions · ANFCI',gpr:'Geopolitical risk · GPR',lag_equity_return:'Last known SPY return',lag_treasury_return:'Last known IEF return',lag_ig_credit_return:'Last known LQD return',lag_growth_surprise:'Previous growth surprise',lag_inflation_surprise:'Previous inflation surprise',growth_x_anfci:'Growth × ANFCI',inflation_x_anfci:'Inflation × ANFCI'};
 const descriptions={historical_mean:'Historical mean predicts each asset’s average completed past return. It ignores the input values; its feature contributions are zero.',ols:'OLS estimates a linear relationship between the inputs and each asset’s next return. It does not penalize large coefficients.',ridge:'Ridge starts from a fitted intercept and adds weighted inputs. Its penalty shrinks coefficients to reduce sensitivity to limited training data.',elastic_net:'Elastic Net both shrinks coefficients and can set some to zero. A zero contribution may reflect a removed predictor or an input at its training mean.',ridge_lags:'Dynamic Ridge adds return information already known at the decision and the previous month’s macro surprises. It forecasts the next holding interval.',ridge_interactions:'Interaction Ridge lets the effect of growth and inflation surprises depend on ANFCI. It adds the two interaction terms without adding lags.'};
 const pct=(v,d=2)=>v==null?'—':`${(100*v).toFixed(d)}%`;
 const signed=v=>`${v>0.00005?'+':''}${(Math.abs(v)<.00005?0:100*v).toFixed(2)} pp`;
 const fmtDate=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
 const fmtMonth=d=>new Date(`${d}T12:00:00`).toLocaleDateString('en-US',{month:'short',year:'numeric'});
 const value=(name,v)=>v==null?'Missing':name.startsWith('lag_')&&name.endsWith('_return')?pct(v):v.toFixed(2);
 const shortName=key=>({historical_mean:'Historical mean',ols:'OLS',ridge:'Ridge',elastic_net:'Elastic Net',ridge_lags:'Ridge + lags',ridge_interactions:'Ridge + interactions',fixed453520:'Fixed 45/35/20',prior_only:'BL prior only'}[key]||key);
 let state=null,choose=null,selectedDate=null;
 let returnView='all',returnUnits='percent';
 const hiddenReturns=new Set();
 const linePatterns={historical_mean:'6 4',ols:'',ridge:'',elastic_net:'10 3',ridge_lags:'3 3',ridge_interactions:'12 3 2 3',fixed453520:'2 4',prior_only:'8 3 2 3'};
 const result=()=>state.window.results[state.model];
 const decision=()=>result().decisions.find(d=>d.date===selectedDate);
 const prediction=()=>result().predictions.find(p=>p.date===selectedDate);
 const index=()=>assets.indexOf(state.asset);
 const width=id=>Math.max(280,Math.floor($(id).clientWidth||960));
 function svg(id,w,h,parts,title,description){
  $(id).setAttribute('viewBox',`0 0 ${w} ${h}`);
  $(id).innerHTML=`<title>${title}</title><desc>${description}</desc>${parts.join('')}`;
 }
 function grid(w,h,p,lo,hi,format){
  const y=v=>p.t+(hi-v)/(hi-lo)*(h-p.t-p.b),parts=[];
  for(let i=0;i<5;i++){
   const v=lo+(hi-lo)*i/4;
   parts.push(`<line x1="${p.l}" x2="${w-p.r}" y1="${y(v)}" y2="${y(v)}" class="viz-gridline"/><text x="${p.l-10}" y="${y(v)+4}" text-anchor="end" class="viz-tick">${format(v)}</text>`);
  }
  if(lo<=0&&hi>=0)parts.push(`<line x1="${p.l}" x2="${w-p.r}" y1="${y(0)}" y2="${y(0)}" class="viz-zero"/>`);
  return {y,parts};
 }
 function dateTicks(parts,rows,x,h,w){
  const indices=w<560?[0,rows.length-1]:[0,Math.floor((rows.length-1)/2),rows.length-1];
  indices.forEach((i,j)=>parts.push(`<text x="${x(rows[i])}" y="${h-12}" text-anchor="${j===0?'start':j===indices.length-1?'end':'middle'}" class="viz-tick">${fmtMonth(rows[i].holding_month||rows[i].date)}</text>`));
 }
 function line(rows,x,y,get){return rows.map((d,i)=>`${i?'L':'M'}${x(d).toFixed(2)},${y(get(d)).toFixed(2)}`).join(' ');}
 function worstDate(){
  const j=index();
  return result().predictions.reduce((a,b)=>Math.abs(a.q[j]-a.actual[j])>=Math.abs(b.q[j]-b.actual[j])?a:b).date;
 }
 function effects(id,rows){
  const max=Math.max(...rows.map(r=>Math.abs(r.value)),.0001);
  $(id).setAttribute('aria-label',rows.map(r=>`${r.label}: ${signed(r.value)}`).join('; '));
  $(id).innerHTML=rows.map(r=>{
   const n=Math.abs(r.value)/max*46,left=r.value>=0?50:50-n;
   return `<div class="effect-row"><span class="effect-label">${r.label}${r.note?`<small>${r.note}</small>`:''}</span><span class="effect-track" aria-hidden="true"><i class="effect-center"></i><i class="effect-mark" style="left:${left}%;width:${n}%;background:${r.color||'#007f86'}"></i></span><strong>${signed(r.value)}</strong></div>`;
  }).join('');
 }
 function explainDecision(){
  const d=decision(),p=prediction(),j=index(),labels=p.feature_columns,prep=p.preprocessing;
  $('decisionSelect').innerHTML=result().decisions.map(row=>`<option value="${row.date}">${fmtMonth(row.holding_month)}</option>`).join('');
  $('decisionSelect').value=selectedDate;
  const position=result().decisions.findIndex(row=>row.date===selectedDate);
  $('decisionPrev').disabled=position===0;$('decisionNext').disabled=position===result().decisions.length-1;
  const alpha=p.alpha[j],l1=p.l1_ratio[j];
  put('trainingContext',`${state.data.models[state.model].name} · ${names[state.asset]} · decided ${fmtDate(d.decision_date)}, held ${fmtDate(d.entry)}–${fmtDate(d.exit)}. Trained on ${p.training_rows} completed months through ${fmtDate(p.last_training_exit)}.${alpha==null?' No penalty tuning.':` Selected α ${alpha}${l1==null?'':`, L1 ratio ${l1}`} from ${p.validation_folds} earlier validation folds.`} Active predictors for ${names[state.asset]}: ${p.nonzero_features[j]} of ${labels.length}.`);
  put('modelExplanation',descriptions[state.model]);
  $('inputValues').innerHTML=labels.map((name,i)=>`<div class="input-row"><span>${featureNames[name]}<small>${name==='gpr'?'Risk index level':name==='anfci'?'Conditions index':name.includes('_x_')?'Interaction term':name.endsWith('_return')?'Known monthly return':'Surprise score'}</small></span><strong>${value(name,prep.raw_input[i])}${p.input_clipped[i]?` <span class="input-arrow">→</span> ${value(name,prep.used_input[i])}<small>Clipped to earlier training range</small>`:''}</strong></div>`).join('');
  $('inputTransformTable').innerHTML=labels.map((name,i)=>`<tr><td>${featureNames[name]}</td><td>${value(name,prep.clip_low[i])} to ${value(name,prep.clip_high[i])}</td><td>${prep.standardized_input[i].toFixed(2)}</td></tr>`).join('');
  put('contributionTitle',`${names[state.asset]} forecast: ${pct(p.q[j])}`);
  const terms=p.feature_contributions[j],sum=terms.reduce((a,b)=>a+b,0);
  put('baseEstimate',`Starting estimate (intercept): ${pct(p.base_return[j])}. The bars below show the input contributions added to it.`);
  effects('contributionBars',labels.map((name,i)=>({label:featureNames[name],value:terms[i],color:state.data.models[state.model].color,note:state.model==='elastic_net'&&p.coefficients[j][i]===0?'Coefficient set to zero':''})));
  put('forecastEquation',`Starting estimate ${pct(p.base_return[j])}; inputs add ${signed(sum)}; forecast ${pct(p.q[j])}.`);
  effects('blReturnBars',[{label:'Historical-risk prior',value:d.bl_prior[j],color:'#6b7785'},{label:'Model forecast',value:d.forecast[j],color:state.data.models[state.model].color},{label:'BL adjusted estimate',value:d.posterior[j],color:'#007f86'}]);
  put('blReadout',`For ${names[state.asset]}, BL changes the model estimate by ${signed(d.posterior[j]-d.forecast[j])}. Earlier prediction errors had a standard deviation of ${pct(Math.sqrt(d.view_error_variance[j]))}; this describes past errors, not a calibrated prediction interval.`);
  $('allocationSnapshot').innerHTML=assets.map((a,i)=>`<span style="width:${100*d.weights[i]}%;background:${colors[a]}" aria-hidden="true"></span>`).join('');
  $('allocationSnapshot').setAttribute('aria-label',assets.map((a,i)=>`${names[a]} ${pct(d.weights[i],0)}`).join(', '));
  const bounds=[[.2,.7],[.15,.6],[.1,.4]];
  $('allocationSnapshotLegend').innerHTML=assets.map((a,i)=>`<div><span class="asset-swatch" style="background:${colors[a]}"></span><b>${names[a]} ${pct(d.weights[i],0)}</b><small>${Math.abs(d.weights[i]-bounds[i][0])<1e-8?'At lower bound':Math.abs(d.weights[i]-bounds[i][1])<1e-8?'At upper bound':`Allowed ${pct(bounds[i][0],0)}–${pct(bounds[i][1],0)}`}</small></div>`).join('');
  put('allocationReadout',`This rebalance traded ${pct(d.turnover)} of portfolio value and incurred ${(d.cost*10000).toFixed(2)} basis points of cost. Weights sum to 100%.`);
  $('observedOutcome').innerHTML=`<div><span>Observed afterward · ${names[state.asset]}</span><strong>${pct(d.actual[j])}</strong><small>Forecast ${pct(d.forecast[j])}; realized minus forecast ${signed(d.actual[j]-d.forecast[j])}</small></div><div><span>Whole portfolio · net holding return</span><strong>${pct(d.net_return)}</strong><small>After the recorded rebalance cost</small></div>`;
 }
 function forecastChart(){
  const rows=result().predictions,j=index(),mean=new Map(state.window.results.historical_mean.predictions.map(p=>[p.date,p.q[j]]));
  const w=width('forecastChart'),h=w<560?280:330,p={l:57,r:20,t:24,b:42};
  const values=rows.flatMap(r=>[r.q[j],r.actual[j],mean.get(r.date)]),padding=Math.max(.005,(Math.max(...values)-Math.min(...values))*.12);
  const lo=Math.min(0,...values)-padding,hi=Math.max(0,...values)+padding;
  const x=r=>p.l+rows.indexOf(r)/Math.max(1,rows.length-1)*(w-p.l-p.r),{y,parts}=grid(w,h,p,lo,hi,v=>pct(v,hi-lo<.08?1:0));
  const row=rows.find(r=>r.date===selectedDate);
  parts.push(`<line x1="${x(row)}" x2="${x(row)}" y1="${p.t}" y2="${h-p.b}" class="selection-line"/>`);
  parts.push(`<path d="${line(rows,x,y,r=>r.actual[j])}" class="actual-line"/>${state.model==='historical_mean'?'':`<path d="${line(rows,x,y,r=>mean.get(r.date))}" class="mean-line"/>`}<path d="${line(rows,x,y,r=>r.q[j])}" fill="none" stroke="${state.data.models[state.model].color}" stroke-width="3" stroke-dasharray="7 4"/>`);
  for(const r of rows){
   const cell=(w-p.l-p.r)/Math.max(rows.length-1,1),tooltip=`${fmtMonth(state.window.results[state.model].decisions.find(d=>d.date===r.date).holding_month)}: forecast ${pct(r.q[j])}; actual ${pct(r.actual[j])}; historical mean ${pct(mean.get(r.date))}`;
   parts.push(`<rect data-date="${r.date}" x="${Math.max(p.l,x(r)-cell/2)}" y="${p.t}" width="${Math.min(cell,w-p.r-Math.max(p.l,x(r)-cell/2))}" height="${h-p.t-p.b}" fill="transparent"><title>${tooltip}</title></rect>`);
  }
  parts.push(`<circle cx="${x(row)}" cy="${y(row.q[j])}" r="5" fill="${state.data.models[state.model].color}" stroke="white" stroke-width="2"/><circle cx="${x(row)}" cy="${y(row.actual[j])}" r="5" fill="#263748" stroke="white" stroke-width="2"/>`);
  const dated=rows.map(r=>({...r,holding_month:state.window.results[state.model].decisions.find(d=>d.date===r.date).holding_month}));
  dateTicks(parts,dated,r=>p.l+dated.indexOf(r)/Math.max(1,dated.length-1)*(w-p.l-p.r),h,w);
  svg('forecastChart',w,h,parts,`${names[state.asset]} forecast and realized monthly return`,'Solid dark line shows observed returns. Dashed colored line shows the selected forecast. The dotted gray line is the expanding historical mean. The vertical line marks the selected month.');
  put('forecastContext',`${state.data.models[state.model].name} · ${names[state.asset]} · ${state.window.name}. Vertical axis: monthly return.`);
  $('forecastLegend').innerHTML=`<span><i class="legend-solid" style="border-color:#263748"></i>Actual return</span><span><i class="legend-dashed" style="border-color:${state.data.models[state.model].color}"></i>${shortName(state.model)} forecast</span>${state.model==='historical_mean'?'':'<span><i class="legend-dotted" style="border-color:#88929d"></i>Historical mean</span>'}`;
  put('forecastReadout',`${fmtMonth(decision().holding_month)}: forecast ${pct(row.q[j])} · observed ${pct(row.actual[j])} · historical mean ${pct(mean.get(row.date))}.`);
 }
 function accuracy(){
  put('accuracyContext',`RMSE for ${names[state.asset]} in ${state.window.name.toLowerCase()}. Shorter bars mean smaller forecast errors. Select a model to inspect it.`);
  const keys=['historical_mean','ols','ridge','elastic_net','ridge_lags','ridge_interactions'];
  const max=Math.max(...keys.map(k=>state.window.results[k].forecast[state.asset].rmse),.0001);
  $('accuracyBars').innerHTML=keys.map(k=>{const value=state.window.results[k].forecast[state.asset].rmse;return `<button type="button" class="accuracy-row${k===state.model?' is-active':''}" data-model="${k}" aria-pressed="${k===state.model}"><span>${shortName(k)}</span><span class="accuracy-track"><i style="width:${value/max*100}%;background:${state.data.models[k].color}"></i></span><strong>${pct(value)}</strong></button>`;}).join('');
  $('skillGrid').innerHTML=`<table><caption class="visually-hidden">Forecast skill relative to historical mean by model and asset</caption><thead><tr><th>Model</th>${assets.map(a=>`<th>${names[a]}</th>`).join('')}</tr></thead><tbody>${keys.map(k=>`<tr><th>${shortName(k)}</th>${assets.map(a=>{const v=state.window.results[k].forecast[a].oos_r2_vs_mean;return `<td><button type="button" data-model="${k}" data-asset="${a}" class="skill-cell ${v>1e-6?'skill-positive':v< -1e-6?'skill-negative':'skill-neutral'}${k===state.model&&a===state.asset?' is-active':''}" aria-label="${shortName(k)}, ${names[a]}, out-of-sample R squared ${v==null?'unavailable':v.toFixed(3)}" aria-pressed="${k===state.model&&a===state.asset}">${v==null?'—':v.toFixed(3)}</button></td>`;}).join('')}</tr>`).join('')}</tbody></table>`;
 }
 function returnCandidates(){
  if(returnView==='all_references')return Object.keys(state.data.models);
  return returnView==='all'?Object.keys(state.data.models).filter(k=>state.data.models[k].stage!=='reference'):[...new Set([state.model,'historical_mean',...(state.data.models[state.model].stage==='extension'?['ridge']:[]),'fixed453520'])];
 }
 function portfolioCharts(){
  const candidates=returnCandidates();
  let keys=candidates.filter(k=>!hiddenReturns.has(k));
  if(!keys.length){hiddenReturns.delete(state.model);keys=candidates.filter(k=>!hiddenReturns.has(k));}
  // Draw the inspected model last so overlapping peer lines cannot obscure it.
  const drawKeys=[...keys.filter(k=>k!==state.model),...keys.filter(k=>k===state.model)];
  const paths=drawKeys.map(k=>state.window.results[k].path);
  for(const mode of ['growth','drawdown']){
   const id=mode==='growth'?'modelChart':'drawdownChart',w=width(id),h=mode==='growth'?360:250,p={l:62,r:22,t:22,b:42};
   const transform=rows=>{let peak=rows[0].wealth;return rows.map(r=>{peak=Math.max(peak,r.wealth);return {...r,value:mode==='growth'?(returnUnits==='dollars'?r.wealth:r.wealth/100-1):r.wealth/peak-1};});};
   const series=paths.map(transform);
   // Keep the scale fixed for this view even when legend entries are hidden.
   const values=candidates.flatMap(k=>transform(state.window.results[k].path).map(r=>r.value));
   const anchor=mode==='growth'&&returnUnits==='dollars'?100:0;
   const padding=mode==='growth'&&returnUnits==='dollars'?2:Math.max(.005,(Math.max(...values)-Math.min(...values))*.06);
   const lo=mode==='growth'?Math.min(anchor,...values)-padding:Math.min(-.01,...values)*1.1;
   const hi=mode==='growth'?Math.max(anchor,...values)+padding:0;
   const first=new Date(paths[0][0].date).getTime(),last=new Date(paths[0].at(-1).date).getTime();
   const x=r=>p.l+(new Date(r.date).getTime()-first)/(last-first)*(w-p.l-p.r);
   const format=v=>mode==='growth'&&returnUnits==='dollars'?`$${v.toFixed(0)}`:pct(v,hi-lo<.08?1:0);
   const {y,parts}=grid(w,h,p,lo,hi,format);
   series.forEach((rows,i)=>{
    const key=drawKeys[i],selected=key===state.model,dash=linePatterns[key];
    const endpoint=rows.at(-1),endLabel=mode==='growth'&&returnUnits==='dollars'?`$${endpoint.value.toFixed(2)}`:pct(endpoint.value);
    parts.push(`<path data-return-series="${key}" d="${line(rows,x,y,r=>r.value)}" fill="none" stroke="${state.data.models[key].color}" stroke-width="${selected?3.8:1.9}" opacity="${selected?1:.8}" ${dash?`stroke-dasharray="${dash}"`:''}><title>${shortName(key)}: ending ${mode==='growth'?'value':'drawdown'} ${endLabel}</title></path>`);
    parts.push(`<circle cx="${x(endpoint)}" cy="${y(endpoint.value)}" r="${selected?4.5:2.8}" fill="${state.data.models[key].color}"/>`);
   });
   dateTicks(parts,series[0],x,h,w);
   svg(id,w,h,parts,mode==='growth'?'Cumulative portfolio net returns':'Portfolio losses below earlier peaks',`${keys.map(shortName).join(', ')} over the same selected dates. ${mode==='growth'?(returnUnits==='dollars'?'Each starts at $100.':'Cumulative net returns start at zero.'):'Drawdown is zero at each new peak and negative below it.'}`);
  }
  put('returnsTitle',returnUnits==='dollars'?'Growth of $100 after costs':'Cumulative net returns after costs');
  put('seriesVisibility',`${keys.length} of ${candidates.length} ${returnView==='all'?'model lines':'series'} visible. Click legend entries to hide or restore lines; at least one stays visible. The axis stays fixed when hiding lines.`);
  $('modelLegend').innerHTML=candidates.map(k=>{
   const visible=!hiddenReturns.has(k),dash=linePatterns[k],end=state.window.results[k].portfolio;
   const label=returnUnits==='dollars'?`$${end.end_value.toFixed(2)}`:pct(end.cumulative_return);
   return `<button type="button" data-return-model="${k}" aria-pressed="${visible}" ${visible&&keys.length===1?'disabled':''} class="return-legend-item${visible?'':' is-hidden'}${k===state.model?' is-inspected':''}"><i class="${dash?'legend-dashed':'legend-solid'}" style="border-color:${state.data.models[k].color}"></i><span>${shortName(k)}</span><b>${label}</b></button>`;
  }).join('');
  put('performanceReadout',`${state.data.models[state.model].name}${hiddenReturns.has(state.model)?' (currently hidden in the chart)':''}: cumulative net return ${pct(result().portfolio.cumulative_return)}; maximum daily drawdown ${pct(result().portfolio.maximum_drawdown)}. ${hiddenReturns.has(state.model)?'':'The inspected model has the bold line. '}These are whole-portfolio returns, independent of the asset selected for forecast inspection.`);
 }
 function allocations(){
  const rows=result().decisions,w=width('allocationChart'),h=230,p={l:52,r:18,t:18,b:42},plotH=h-p.t-p.b,step=(w-p.l-p.r)/rows.length;
  const parts=[];
  for(const tick of [0,.5,1])parts.push(`<text x="${p.l-10}" y="${h-p.b-tick*plotH+4}" text-anchor="end" class="viz-tick">${pct(tick,0)}</text>`);
  rows.forEach((r,i)=>{let total=0;const x=p.l+i*step;
   assets.forEach((a,j)=>{const n=r.weights[j];parts.push(`<rect data-date="${r.date}" x="${x}" y="${h-p.b-(total+n)*plotH}" width="${Math.max(1,step-1.5)}" height="${n*plotH}" fill="${colors[a]}"><title>${fmtMonth(r.holding_month)}: ${assets.map((a,k)=>`${names[a]} ${pct(r.weights[k],0)}`).join(', ')}</title></rect>`);total+=n;});
   if(r.date===selectedDate)parts.push(`<rect x="${x-.5}" y="${p.t-3}" width="${Math.max(1,step-.5)}" height="${plotH+6}" class="allocation-selection"/>`);
  });
  dateTicks(parts,rows,r=>p.l+(rows.indexOf(r)+.5)*step,h,w);
  svg('allocationChart',w,h,parts,'Monthly portfolio weights','Stacked bars show equity, Treasury and credit weights. The outline marks the selected month.');
  $('allocationLegend').innerHTML=`<span>${fmtMonth(decision().holding_month)}</span>`+assets.map((a,i)=>`<span><i class="asset-swatch" style="background:${colors[a]}"></i>${names[a]} <b>${pct(decision().weights[i],0)}</b></span>`).join('');
 }
 function redraw(){if(!state)return;explainDecision();forecastChart();accuracy();portfolioCharts();allocations();}
 function render(next,callback){if(state&&next.model!==state.model)hiddenReturns.delete(next.model);state=next;choose=callback;if(!result().decisions.some(r=>r.date===selectedDate))selectedDate=worstDate();redraw();}
 function selectDate(value){if(state&&result().decisions.some(r=>r.date===value)){selectedDate=value;redraw();}}
 $('decisionSelect').addEventListener('change',e=>selectDate(e.target.value));
 $('decisionPrev').addEventListener('click',()=>{if(!state)return;const rows=result().decisions,i=rows.findIndex(d=>d.date===selectedDate);if(i>0)selectDate(rows[i-1].date);});
 $('decisionNext').addEventListener('click',()=>{if(!state)return;const rows=result().decisions,i=rows.findIndex(d=>d.date===selectedDate);if(i<rows.length-1)selectDate(rows[i+1].date);});
 $('largestMiss').addEventListener('click',()=>{if(state)selectDate(worstDate());});
 for(const id of ['forecastChart','allocationChart'])$(id).addEventListener('click',e=>{const target=e.target.closest('[data-date]');if(target)selectDate(target.dataset.date);});
 for(const id of ['accuracyBars','skillGrid'])$(id).addEventListener('click',e=>{const target=e.target.closest('[data-model]');if(target&&choose)choose({model:target.dataset.model,asset:target.dataset.asset});});
 $('returnView').addEventListener('change',e=>{returnView=e.target.value;hiddenReturns.clear();if(state)portfolioCharts();});
 $('returnUnits').addEventListener('change',e=>{returnUnits=e.target.value;if(state)portfolioCharts();});
 $('showAllReturns').addEventListener('click',()=>{hiddenReturns.clear();if(state)portfolioCharts();});
 $('modelLegend').addEventListener('click',e=>{
  if(!state)return;
  const target=e.target.closest('[data-return-model]');if(!target)return;
  const key=target.dataset.returnModel,candidates=returnCandidates();
  if(!candidates.includes(key))return;
  if(hiddenReturns.has(key))hiddenReturns.delete(key);
  else if(candidates.filter(k=>!hiddenReturns.has(k)).length>1)hiddenReturns.add(key);
  portfolioCharts();
 });
 let resizeTimer;
 if(typeof window.addEventListener==='function')window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(redraw,120);});
 return {render,selectDate,getSelectedDate:()=>selectedDate};
})();
