/* Protofin Backtest dashboard. Reads data/dashboard.json (built by mvp/build_dashboard_data.py).
   Three primary approaches: Deterministic Quantitative Model, Agentic Workflow (represented by JEV),
   Agentic Causal RAG. The Agent Committee is a within-approach variant shown under Experiments. */
(function () {
  'use strict';

  const GLOSSARY = {
    cer: 'Net CER = Certainty-Equivalent Return: the guaranteed yearly return above cash that a risk-averse investor would accept instead of the strategy. Computed as 12 × (average monthly net excess return − ½ × 2.5 × its variance). Higher is better. It is not a compound annual return.',
    sharpe: 'Sharpe ratio: return earned above cash for each unit of risk taken. Higher is better.',
    drawdown: 'Maximum drawdown (worst fall): the largest drop from a peak to a later low. Closer to zero is better.',
    excess: 'Annual return above cash: yearly return after trading costs, minus what Treasury bills paid.',
    volatility: 'Volatility: how much returns swing, expressed per year. Lower means a smoother ride.',
    turnover: 'Turnover: share of the portfolio traded per year. More trading means more cost.',
    growth: 'What $1 invested at the start would be worth each month, after trading costs.',
    gap: 'How much more (or less) $1 in the approach was worth than $1 in its own benchmark, in percent. Above zero means ahead.',
    benchmark: 'Own benchmark: the approach\'s starting mix (for example 60% stocks, 40% bonds), held fixed and rebalanced monthly. The gap shows what the approach\'s forecasts added.',
    significance: 'Statistically significant: the gap is too large to be explained by chance alone (5% level, corrected for the three primary comparisons).',
    ci: 'Likely range: where the true difference most likely lies (95% confidence). If it includes zero, the gap could be chance.',
    bl: 'Black–Litterman: a standard method that starts from a neutral portfolio and tilts it toward forecasts in proportion to how confident they are.',
    walkforward: 'Walk-forward validation: each month the model is rebuilt using only data available at that time, then judged on the following month.',
    causalrag: 'Causal RAG: AI retrieval guided by a map of cause-and-effect findings from economics research, rather than by keyword similarity alone.',
    kg: 'Knowledge graph: a network of cause-and-effect claims extracted from published economics papers. Each year only uses papers published before it.',
    hypothesis: 'Hypothesis Agent: proposes how this month\'s events could move markets, citing pathways in the research graph.',
    testing: 'Testing Agent: tries to disprove each hypothesis against dated documents, market data and a rival explanation. "Supported" means consistent with evidence, not proven.',
    calibration: 'Calibration model: a statistical model that learns, from past months only, how much tested hypotheses moved returns.',
    training: 'Training period: from February 2015, the macro data the models learn from. The primary research timeline starts here.',
    development: 'Development diagnostics: months used to build and check the approaches. Useful for spotting problems, but not evidence of which approach is better.',
    test: 'Protected historical test: months held back and scored once, after everything is frozen. Still sealed, so no protected historical results exist yet.',
    prospective: 'Live tracking: months after the freeze. The strongest evidence, because no one could have seen them in advance.',
    reproduction: 'Reproduction check: re-running each approach\'s own code to confirm it gives exactly the results its authors saved.',
    common: 'Shared rules: scoring every approach with the same trade timing, trading costs and cash rate.',
    mock: 'Demo: example output generated without an AI model to show how this screen works. It is not a result.',
    ridge: 'Ridge regression: a linear model that shrinks weak signals toward zero to avoid overfitting.',
    jev: 'JEV: an AI decision model that answers one question each month: will stocks beat bonds over the next 12 months?',
    confidence: 'How sure the approach said it was. Higher confidence moves the portfolio further from its starting mix.',
    regime: 'When policy or geopolitical uncertainty is very high, the Committee automatically lowers its confidence by one level.',
    inventory: 'Research inventory: how much published research the approach can draw on. It describes inputs, not performance.',
    signals: 'For each asset, the predicted directions (up = +1, down = −1) of the hypotheses that reached each verdict, added up. The forecast model learns how much each kind is worth.',
    variant: 'Within-approach experiment: a different version of the same approach. It is compared with that approach\'s primary system, never with the other approaches.',
    awaiting: 'Awaiting validation: every part is built and tested without an AI model. Results stay unavailable until the model run is approved and its validation gates pass.',
  };
  const ROUTES = { deterministic: 'det', jev: 'jev', 'causal-rag': 'rag', committee: 'com' };
  const SLUG = { det: 'deterministic', jev: 'jev', rag: 'causal-rag', com: 'committee' };
  const VAR = { det: '--c-det', com: '--c-com', jev: '--c-jev', rag: '--c-rag' };
  // Assets get their own neutral palette (never an approach colour) and a line style, used in every chart.
  const ASSET_VAR = { SPY: '--a-eq', IEF: '--a-gov', TLT: '--a-gov', LQD: '--a-credit' };
  const ASSET_DASH = { SPY: [], IEF: [6, 4], TLT: [6, 4], LQD: [2, 3] };
  const PLAIN = { SPY: 'Stocks', IEF: 'Treasuries', TLT: 'Long Treasuries', LQD: 'Corporate bonds' };
  const BENCH_DASH = [[6, 4], [2, 3]];

  let D = null;
  let charts = [];
  const app = document.getElementById('app');

  // ---------------------------------------------------------------- helpers
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const sgn = (x, s) => (x > 0 ? '+' : x < 0 ? '−' : '') + s;
  const pct = (x, d = 1) => x == null ? '—' : sgn(x < 0 ? -1 : 0, Math.abs(x * 100).toFixed(d) + '%');
  const pts = (x, d = 1) => x == null ? '—' : sgn(+(x * 100).toFixed(d), Math.abs(x * 100).toFixed(d) + ' pts');
  const num = (x, d = 2) => x == null ? '—' : x.toFixed(d);
  const monthLabel = m => { const [y, mo] = m.split('-'); return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][+mo - 1]} ${y}`; };
  const tip = (key, label) => `<span class="tip"><button type="button" aria-label="${esc(label || 'What does this mean?')}">i</button><span role="tooltip">${esc(GLOSSARY[key])}</span></span>`;
  // Keeps an info icon on the same line as the word before it.
  const tipw = (word, key) => `<span class="nw">${word}&nbsp;${tip(key)}</span>`;
  const all = () => D.systems.concat(D.variants);
  const sys = key => all().find(s => s.key === key);
  const color = key => css(VAR[key]) || '#888';
  const assetColor = a => css(ASSET_VAR[a]) || '#888';
  const swatch = key => `<span class="swatch" style="background:${color(key)}"></span>`;
  const primaryWithResults = () => D.systems.filter(s => s.has_results && D.dev.series[s.key]);
  const S = key => D.dev.series[key];
  const devSpan = () => `${monthLabel(D.windows.development[0])} – ${monthLabel(D.windows.development[1])}`;
  const testSpan = () => `${D.windows.historical_test[0].slice(0, 4)}–${D.windows.historical_test[1].slice(0, 4)}`;
  const killCharts = () => { charts.forEach(c => c.destroy()); charts = []; };
  const killChart = id => charts.filter(c => c.canvas.id === id).forEach(c => { c.destroy(); charts = charts.filter(x => x !== c); });
  const statusChip = st => st === 'implemented' ? '<span class="chip-st ok">Implemented</span>'
    : st === 'proposed' ? '<span class="chip-st prop">Proposed · not run</span>' : `<span class="chip-st wait">${esc(st)}</span>`;
  const ragBadge = () => `<span class="pill await"><span class="dot"></span>${esc(D.ap3.status_label)} ${tip('awaiting')}</span>`;

  function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.font.family = css('--font') || 'system-ui';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css('--muted');
    Chart.defaults.borderColor = css('--border');
    Chart.defaults.animation = false;
    Chart.defaults.plugins.tooltip.backgroundColor = css('--surface-3');
    Chart.defaults.plugins.tooltip.titleColor = css('--text');
    Chart.defaults.plugins.tooltip.bodyColor = css('--text-2');
    Chart.defaults.plugins.tooltip.borderColor = css('--border-strong');
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.maintainAspectRatio = false;
  }
  function chart(canvas, cfg) {
    if (!window.Chart) { canvas.parentElement.innerHTML = '<p class="sub">Charts could not load.</p>'; return null; }
    const c = new Chart(canvas, cfg);
    charts.push(c);
    return c;
  }
  const xTicks = (months, n) => ({ ticks: { maxTicksLimit: n || (window.innerWidth < 560 ? 4 : 8), maxRotation: 0, autoSkip: true, callback: (v, i) => monthLabel(months[i]) }, grid: { display: false } });
  const bottomLegend = { position: 'bottom', labels: { boxWidth: 18, boxHeight: 2, usePointStyle: false } };

  // ---------------------------------------------------------------- shared pieces
  function statusPills() {
    return `<div class="pills">
      <span class="pill ok"><span class="dot"></span>Development diagnostics, ${devSpan()} ${tip('development')}</span>
      <span class="pill lock"><span class="dot"></span>Protected historical results ${testSpan()}: sealed ${tip('test')}</span>
      <span class="pill wait"><span class="dot"></span>Live tracking: not started ${tip('prospective')}</span>
    </div>`;
  }

  function card(s, compact) {
    const r = S(s.key);
    const body = compact ? '<div class="foot"><span></span><span class="more">Details →</span></div>' : r ? `
      <dl class="kv">
        <div><dt>Net CER ${tip('cer')}</dt><dd class="num">${pct(r.metrics.cer)}</dd></div>
        <div><dt>Sharpe ratio ${tip('sharpe')}</dt><dd class="num">${num(r.metrics.sharpe)}</dd></div>
        <div><dt>Worst fall ${tip('drawdown')}</dt><dd class="num">${pct(r.metrics.max_drawdown)}</dd></div>
      </dl>
      <div class="foot"><span>vs own benchmark: <b class="num">${pts(r.vs_neutral.cer_difference)}</b>${r.vs_neutral.p >= 0.05 ? ' (could be chance)' : ''}</span><span class="more">Details →</span></div>`
      : `<div class="pending">Built and tested without an AI model. Results stay unavailable until the model run is approved and validated.</div>
         <div class="foot"><span>How it works, with a labelled demo</span><span class="more">Details →</span></div>`;
    return `<article class="card">
      <div class="name">${swatch(s.key)}<a class="stretch" href="#${SLUG[s.key]}">${esc(s.name)}</a></div>
      ${s.key === 'rag' ? `<div>${ragBadge()}</div>` : ''}
      <p>${esc(s.tagline)}</p>
      ${body}
    </article>`;
  }

  function legendButtons(id, items) {
    return `<div class="legend" id="${id}">` + items.map((it, i) => {
      const cls = it.dash ? (it.dash[0] <= 2 ? ' dot' : ' dash') : '';
      return `<button type="button" data-i="${i}" aria-pressed="true"><span class="ln${cls}" style="border-top-color:${it.color}"></span>${esc(it.label)}</button>`;
    }).join('') + '</div>';
  }
  function wireLegend(id, ch) {
    document.querySelectorAll(`#${id} button`).forEach(b => b.addEventListener('click', () => {
      const i = +b.dataset.i, vis = ch.isDatasetVisible(i);
      ch.setDatasetVisibility(i, !vis); ch.update(); b.setAttribute('aria-pressed', String(!vis));
    }));
  }

  const FMT_WEALTH = { y: v => '$' + v.toFixed(2), tip: v => '$' + v.toFixed(3) };
  const FMT_GAP = { y: v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(0) + '%', tip: v => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}% vs own benchmark` };

  // Draws a line chart plus its clickable legend; replaces any previous chart and legend with the same ids.
  function lineChart(canvasId, legendId, months, lines, fmt) {
    killChart(canvasId);
    const lg = document.getElementById(legendId);
    if (lg) lg.outerHTML = legendButtons(legendId, lines);
    const ch = chart(document.getElementById(canvasId), {
      type: 'line',
      data: { labels: months, datasets: lines.map(l => ({ label: l.label, data: l.data, borderColor: l.color, backgroundColor: l.color,
        borderWidth: l.dash ? 1.5 : 2.5, borderDash: l.dash || [], pointRadius: 0, pointHoverRadius: 4, tension: 0.15 })) },
      options: { interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]), label: it => ` ${it.dataset.label}: ${fmt.tip(it.parsed.y)}` } } },
        scales: { x: xTicks(months), y: { ticks: { callback: fmt.y }, grid: { color: css('--border') } } } } });
    if (ch) wireLegend(legendId, ch);
  }

  function weightsChart(canvas, months, weights, ticks) {
    const assets = Object.keys(weights);
    chart(canvas, { type: 'line',
      data: { labels: months, datasets: assets.map((a, i) => ({ label: PLAIN[a] || a, data: weights[a].map(v => v * 100), fill: i === 0 ? 'origin' : '-1',
        borderColor: assetColor(a), backgroundColor: assetColor(a) + 'cc', borderWidth: 1.5, pointRadius: 0, tension: 0.1 })) },
      options: { interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12 } },
          tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]), label: it => ` ${it.dataset.label}: ${(weights[assets[it.datasetIndex]][it.dataIndex] * 100).toFixed(0)}%` } } },
        scales: { x: xTicks(months, ticks), y: { stacked: true, min: 0, max: 100, ticks: { stepSize: 25, callback: v => v + '%' }, grid: { color: css('--border') } } } } });
  }

  // One shared, symmetric axis for every approach and variant, so the bars can be compared across pages.
  function ciAxis() {
    const vals = Object.values(D.dev.series).flatMap(s => s.vs_neutral.ci95.map(Math.abs));
    return Math.max(0.01, Math.ceil(Math.max(...vals) * 100) / 100);
  }
  function ciBar(vs, key) {
    const A = ciAxis(), x = v => ((v + A) / (2 * A) * 100).toFixed(2) + '%';
    return `<div class="ci" role="img" aria-label="Difference ${pts(vs.cer_difference)}, likely range ${pts(vs.ci95[0])} to ${pts(vs.ci95[1])}">
      <div class="cibar"><span class="zero" style="left:${x(0)}"></span>
        <span class="range" style="left:${x(vs.ci95[0])};width:calc(${x(vs.ci95[1])} - ${x(vs.ci95[0])});background:${color(key)}"></span>
        <span class="pt" style="left:${x(vs.cer_difference)};background:${color(key)}"></span></div>
      <div class="cilabels num"><span>${pts(-A, 0)} behind</span><span>0 = same as benchmark</span><span>${pts(A, 0)} ahead</span></div>
    </div>`;
  }

  const name = k => esc(sys(k).short);
  function contrastSentence(c) {
    const verdict = c.significant === true ? 'statistically significant' : c.significant === false ? 'not statistically significant' : 'undecided until all comparisons exist';
    return `<b>${name(c.a)}</b> minus <b>${name(c.b)}</b>: <b class="num">${pts(c.cer_difference)}</b> net CER per year, likely range ${pts(c.ci95[0])} to ${tipw(pts(c.ci95[1]), 'ci')}; ${verdict}.`;
  }

  // ---------------------------------------------------------------- overview
  function viewOverview() {
    const res = primaryWithResults();
    const months = D.dev.months;
    const pc = D.dev.primary_contrasts.items;
    const anySig = pc.some(c => c.computed && c.significant) || res.some(s => S(s.key).vs_neutral.p < 0.05);
    const bkeys = [...new Set(res.map(s => S(s.key).neutral))];
    const users = bk => res.filter(s => S(s.key).neutral === bk).map(s => s.short).join(' & ');
    const metrics = [
      ['cer', 'Net CER (Certainty-Equivalent Return)', s => S(s).metrics.cer, pct, true, 'per year'],
      ['benchmark', 'Net CER vs own benchmark', s => S(s).vs_neutral.cer_difference, pts, true, 'per year'],
      ['sharpe', 'Sharpe ratio', s => S(s).metrics.sharpe, v => num(v), true, ''],
      ['excess', 'Annual return above cash', s => S(s).metrics.ann_excess_return, pct, true, 'after costs'],
      ['volatility', 'Volatility', s => S(s).metrics.volatility, pct, false, 'per year'],
      ['drawdown', 'Worst fall', s => S(s).metrics.max_drawdown, pct, true, ''],
      ['turnover', 'Turnover', s => S(s).metrics.turnover, v => pct(v, 0), false, 'per year'],
    ];
    const ragCell = '<td class="num na" data-label="Causal RAG">Unavailable</td>';
    const rows = metrics.map(([k, label, get, fmt, higher, unit]) => {
      const vals = res.map(s => get(s.key));
      const lead = higher ? Math.max(...vals) : Math.min(...vals);
      return `<tr><td><span class="metricname">${label}${tip(k)}${unit ? `<small>${unit}</small>` : ''}</span></td>` +
        res.map((s, i) => `<td class="num${vals[i] === lead ? ' lead' : ''}" data-label="${esc(s.short)}">${fmt(vals[i])}</td>`).join('') + ragCell + '</tr>';
    }).join('');
    const sealedRow = `<tr class="sealed-row"><td><span class="metricname">Protected historical results, ${testSpan()}${tip('test')}</span></td>` +
      res.map(s => `<td class="num na" data-label="${esc(s.short)}">Sealed</td>`).join('') + '<td class="num na" data-label="Causal RAG">Sealed</td></tr>';
    const growthLines = mode => mode === 'gap'
      ? res.map(s => { const b = D.dev.benchmarks[S(s.key).neutral].wealth; return { label: s.short, data: S(s.key).wealth.map((w, i) => (w / b[i] - 1) * 100), color: color(s.key) }; })
          .concat([{ label: 'Own benchmark', data: months.map(() => 0), color: css('--c-bench'), dash: BENCH_DASH[0] }])
      : res.map(s => ({ label: s.short, data: S(s.key).wealth, color: color(s.key) }))
          .concat(bkeys.map((bk, i) => ({ label: `Benchmark: ${users(bk)}`, data: D.dev.benchmarks[bk].wealth, color: css('--c-bench'), dash: BENCH_DASH[i % 2] })));
    const growthNote = {
      abs: `Dashed lines are the benchmarks, each a fixed mix: ${bkeys.map(bk => `${esc(D.dev.benchmarks[bk].label)} for ${esc(users(bk))}`).join('; ')}. The two hold different assets. Causal RAG is not shown: its results are unavailable.`,
      gap: 'Each line shows how much more (or less) $1 in the approach was worth than $1 in its own benchmark. Above zero means ahead.',
    };
    const range = w => { const v = w.SPY; const avg = v.reduce((a, b) => a + b, 0) / v.length; return `Stocks ${pct(Math.min(...v), 0)}–${pct(Math.max(...v), 0)}, average ${pct(avg, 0)}`; };
    app.innerHTML = `<div class="wrap">
      <section>
        <h1>How do three ways of building a portfolio compare?</h1>
        <p class="lede">A classic statistical model, an AI agentic workflow, and AI agents reasoning over economic research. Each approach keeps its own design; all are scored by the same rules: same months, same trading costs, same cash rate.</p>
        ${statusPills()}
        <div class="finding"><b>So far</b><span>${esc(D.notes.headline)}</span></div>
      </section>
      <section aria-label="The three approaches"><div class="cards three">${D.systems.map(s => card(s)).join('')}</div>
        <p class="sub aside">The Agent Committee is a variant within the Agentic Workflow ${tip('variant')}. It is compared with JEV under <a href="#experiments">Experiments</a>, not with the other approaches.</p></section>
      <section class="two">
        <div class="panel"><h2>What the development diagnostics show</h2><ul class="list">${D.notes.can.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>
        <div class="panel"><h2>What they can't show yet</h2><ul class="list no">${D.notes.cannot.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>
      </section>
      <section class="panel">
        <div class="row between"><h2 id="g-title">Growth of $1, after costs ${tip('growth')}</h2>
          <div class="seg" role="group" aria-label="Chart view"><button type="button" data-g="abs" aria-pressed="true">Growth of $1</button><button type="button" data-g="gap" aria-pressed="false">Versus own benchmark</button></div></div>
        <p class="sub">Development diagnostics, ${devSpan()}</p>
        <div class="legend" id="lg-growth"></div>
        <div class="chartbox"><canvas id="c-growth" aria-label="Growth of one dollar for each approach"></canvas></div>
        <p class="sub" id="g-note"></p>
      </section>
      <section class="panel">
        <div class="row between"><h2>How they compare</h2>
          <span class="pill ${anySig ? 'ok' : 'wait'}"><span class="dot"></span>${anySig ? 'Some differences are statistically significant' : 'No difference is statistically significant'} ${tip('significance')}</span></div>
        <div class="scroll"><table class="score stack"><thead><tr><th>Development diagnostics, ${devSpan()}</th>${res.map(s => `<th>${swatch(s.key)}${esc(s.short)}</th>`).join('')}<th>${swatch('rag')}Causal RAG</th></tr></thead>
          <tbody>${rows}${sealedRow}</tbody></table></div>
        <p class="sub"><span class="leadmark" aria-hidden="true"></span> marks the stronger value in each row, for development months only. Causal RAG shows no values: ${esc(D.ap3.status_label.toLowerCase())}.</p>
        <div class="contrast"><h3>Primary comparisons ${tip('significance')}</h3><ul class="list">
          ${pc.map(c => c.computed ? `<li>${contrastSentence(c)}</li>` : `<li><b>${name(c.a)}</b> vs <b>${name(c.b)}</b>: pending, Causal RAG results unavailable.</li>`).join('')}</ul>
          <p class="sub">The three comparisons form one family, corrected together once all exist.</p></div>
      </section>
      <section class="panel">
        <h2>How allocations changed</h2><p class="sub">Share of the portfolio in each asset, month by month. Each approach moves within its own limits.</p>
        <div class="minis">${res.map(s => `<div class="mini"><h3>${swatch(s.key)}${esc(s.short)}</h3>
          <div class="chartbox xs"><canvas id="c-alloc-${s.key}" aria-label="${esc(s.short)} portfolio weights over time"></canvas></div>
          <p class="sub num">${range(S(s.key).weights)}</p></div>`).join('')}
          <div class="mini"><h3>${swatch('rag')}Causal RAG</h3><div class="pending tall">${esc(D.ap3.status_label)}</div></div></div>
      </section>
    </div>`;
    const drawGrowth = mode => {
      lineChart('c-growth', 'lg-growth', months, growthLines(mode), mode === 'gap' ? FMT_GAP : FMT_WEALTH);
      document.getElementById('g-note').innerHTML = growthNote[mode];
      document.getElementById('g-title').firstChild.textContent = mode === 'gap' ? 'Ahead of or behind own benchmark ' : 'Growth of $1, after costs ';
      document.querySelector('#g-title .tip span[role=tooltip]').textContent = GLOSSARY[mode === 'gap' ? 'gap' : 'growth'];
    };
    drawGrowth('abs');
    document.querySelectorAll('[data-g]').forEach(b => b.addEventListener('click', () => {
      document.querySelectorAll('[data-g]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); drawGrowth(b.dataset.g); }));
    res.forEach(s => weightsChart(document.getElementById(`c-alloc-${s.key}`), months, S(s.key).weights, 4));
  }

  // ---------------------------------------------------------------- approaches list
  function viewApproaches() {
    const cols = [
      ['What it holds', s => s.assets_label],
      ['Forecast horizon', s => s.horizon],
      ['Engine', s => s.model],
      ['Turns views into weights with', s => s.key === 'jev' ? 'A capped tilt around 60/40' : 'Black–Litterman'],
      ['Results', s => s.has_results ? `Development diagnostics, ${devSpan()}` : D.ap3.status_label],
    ];
    app.innerHTML = `<div class="wrap">
      <section><h1>The three approaches</h1>
        <p class="lede">Each approach keeps its own design, data and allocation rules. Only the scoring is shared.</p></section>
      <section><div class="cards three">${D.systems.map(s => card(s, true)).join('')}</div></section>
      <section class="panel"><h2>At a glance</h2>
        <div class="scroll"><table class="score stack one glance"><thead><tr><th>Approach</th>${cols.map(([l], i) => `<th>${l}${i === 3 ? ' ' + tip('bl') : ''}</th>`).join('')}</tr></thead>
        <tbody>${D.systems.map(s => `<tr><td><a href="#${SLUG[s.key]}" class="rowname">${swatch(s.key)}${esc(s.name)}</a></td>${cols.map(([l, f]) => `<td data-label="${esc(l)}">${esc(f(s))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
        <p class="sub">Because the approaches hold different assets and use different horizons and information, comparing them is a comparison of complete strategies, not a controlled experiment.</p>
      </section>
      <section class="panel aside-panel"><h2>Within-approach variant ${tip('variant')}</h2>
        <p style="margin:0;color:var(--text-2)">The Agentic Workflow has a second implemented version, the <a href="#committee">Agent Committee</a>. It is compared only with JEV, under <a href="#experiments">Experiments</a>.</p></section>
    </div>`;
  }

  // ---------------------------------------------------------------- one approach (or the Committee variant)
  function signalsBlock(s, r) {
    const months = D.dev.months, fc = r.forecasts;
    const yPct = d => ({ ticks: { callback: v => v.toFixed(d) + '%' }, grid: { color: css('--border') } });
    if (s.key === 'det') {
      return { html: `<h3>Monthly return forecasts ${tip('ridge')}</h3><p class="sub">Expected return above cash for the coming month, by asset.</p><div class="chartbox sm"><canvas id="c-sig"></canvas></div>`,
        draw: () => chart(document.getElementById('c-sig'), { type: 'line', data: { labels: months, datasets: s.universe.map(a => ({ label: PLAIN[a], data: fc.map(f => f[a] * 100),
          borderColor: assetColor(a), borderDash: ASSET_DASH[a], borderWidth: 2, pointRadius: 0 })) },
          options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: bottomLegend, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]), label: it => ` ${it.dataset.label}: ${it.parsed.y.toFixed(2)}%` } } },
            scales: { x: xTicks(months), y: yPct(1) } } }) };
    }
    if (s.key === 'com') {
      return { html: `<h3>The CIO's 12-month views ${tip('confidence')}</h3><p class="sub">Expected total return over the next 12 months. Dots mark months when high uncertainty lowered the CIO's “Medium” confidence to “Low” ${tip('regime')}.</p><div class="chartbox sm"><canvas id="c-sig"></canvas></div>`,
        draw: () => chart(document.getElementById('c-sig'), { type: 'line', data: { labels: months, datasets: [
          { label: 'Stocks', data: fc.map(f => f.SPY), borderColor: assetColor('SPY'), borderWidth: 2, pointRadius: fc.map(f => f.confidence === 'Low' ? 3.5 : 0), pointBackgroundColor: css('--warn'), pointBorderColor: css('--warn') },
          { label: 'Long Treasuries', data: fc.map(f => f.TLT), borderColor: assetColor('TLT'), borderDash: ASSET_DASH.TLT, borderWidth: 2, pointRadius: 0 }] },
          options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: bottomLegend, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]),
            label: it => ` ${it.dataset.label}: ${it.parsed.y.toFixed(1)}%`, afterBody: it => `Confidence used: ${fc[it[0].dataIndex].confidence}` } } },
            scales: { x: xTicks(months), y: yPct(0) } } }) };
    }
    if (s.key === 'jev') {
      return { html: `<h3>JEV's answer each month ${tip('jev')}</h3><p class="sub">Chance that stocks beat bonds over the next 12 months, and how confident JEV was.</p><div class="chartbox sm"><canvas id="c-sig"></canvas></div>`,
        draw: () => chart(document.getElementById('c-sig'), { type: 'line', data: { labels: months, datasets: [
          { label: 'Chance stocks beat bonds', data: fc.map(f => f.p * 100), borderColor: color('jev'), borderWidth: 2, pointRadius: 0 },
          { label: 'Confidence', data: fc.map(f => f.confidence * 100), borderColor: css('--c-bench'), borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0 }] },
          options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: bottomLegend, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]),
            label: it => ` ${it.dataset.label}: ${it.parsed.y.toFixed(0)}%`, afterBody: it => `Answer: ${String(fc[it[0].dataIndex].tilt || '').replace(/_/g, ' ')}` } } },
            scales: { x: xTicks(months), y: { min: 0, max: 100, ticks: { callback: v => v + '%' }, grid: { color: css('--border') } } } } }) };
    }
    return { html: '', draw: () => {} };
  }

  function viewApproach(key) {
    const s = sys(key);
    if (key === 'rag') return viewCausalRag(s);
    const variant = s.role === 'variant';
    const r = S(key);
    const months = D.dev.months;
    const bench = D.dev.benchmarks[r.neutral];
    const sig = signalsBlock(s, r);
    const rep = D.reproduction[key];
    const steps = D.native_vs_common[key];
    const ex = r.example;
    const vs = r.vs_neutral;
    const zeroIn = vs.ci95[0] <= 0 && vs.ci95[1] >= 0;
    const repLabel = { reproduced: 'matched saved results', replayed: 'matched saved results (replay only)' }[rep.status] || 'did not match';
    app.innerHTML = `<div class="wrap">
      <section class="hero"><a class="back" href="${variant ? '#experiments' : '#approaches'}">← ${variant ? 'Experiments' : 'Approaches'}</a>
        ${variant ? `<div><span class="pill variant"><span class="dot"></span>Within-approach variant of the Agentic Workflow ${tip('variant')}</span></div>` : ''}
        <h1 class="withswatch">${swatch(key)}${esc(s.name)}</h1>
        <p class="lede">${esc(s.tagline)}</p>
        <div class="chips"><span class="chip">${esc(s.assets_label)}</span><span class="chip">${esc(s.horizon)}</span><span class="chip">${esc(s.model)}</span></div>
      </section>
      ${key === 'jev' ? `<section class="panel aside-panel"><p style="margin:0;color:var(--text-2)">JEV represents the Agentic Workflow in the primary comparison. The approach's other version, the <a href="#committee">Agent Committee</a>, is compared with JEV under <a href="#experiments">Experiments</a>.</p></section>` : ''}
      <section><h2>How it works</h2><ol class="steps">${s.steps.map(t => `<li>${esc(t)}</li>`).join('')}</ol></section>
      <section class="grid2">
        <div class="panel"><h2>Development diagnostics ${tip('development')}</h2><p class="sub">${devSpan()}. Protected historical results (${testSpan()}) are sealed.</p>
          <div class="kpis six">
            <div class="kpi"><div class="v num">${pct(r.metrics.cer)}</div><div class="l">Net CER ${tip('cer')}</div></div>
            <div class="kpi"><div class="v num">${num(r.metrics.sharpe)}</div><div class="l">Sharpe ${tip('sharpe')}</div></div>
            <div class="kpi"><div class="v num">${pct(r.metrics.max_drawdown)}</div><div class="l">Worst fall ${tip('drawdown')}</div></div>
            <div class="kpi"><div class="v num">${pct(r.metrics.ann_excess_return)}</div><div class="l">Above cash ${tip('excess')}</div></div>
            <div class="kpi"><div class="v num">${pct(r.metrics.volatility)}</div><div class="l">Volatility ${tip('volatility')}</div></div>
            <div class="kpi"><div class="v num">${pct(r.metrics.turnover, 0)}</div><div class="l">Turnover ${tip('turnover')}</div></div>
          </div>
          <h3 class="gapttl">Net CER vs own benchmark ${tip('benchmark')}</h3>
          <p class="sub"><b class="num">${pts(vs.cer_difference)}</b> per year against holding ${esc(bench.label)}. Likely range ${pts(vs.ci95[0])} to ${tipw(pts(vs.ci95[1]), 'ci')}${zeroIn ? '; it includes zero, so the gap could be chance.' : '.'}</p>
          ${ciBar(vs, key)}
        </div>
        <div class="panel">
          <h2>Growth of $1 ${tip('growth')}</h2>
          <div class="legend" id="lg-one"></div>
          <div class="chartbox sm"><canvas id="c-one"></canvas></div>
        </div>
      </section>
      <section class="grid2">
        <div class="panel">${sig.html}</div>
        <div class="panel"><h3>Portfolio weights</h3><p class="sub">Share of the portfolio in each asset, month by month.</p><div class="chartbox sm"><canvas id="c-w"></canvas></div></div>
      </section>
      ${ex && ex.cio_rationale ? `<details class="more"><summary>Sample reasoning (${monthLabel(ex.month)})</summary><div>
        <div class="quote"><b>Economist</b>${esc(ex.economist?.text)}</div>
        <div class="quote"><b>Risk Manager</b>${esc(ex.risk_manager?.text)}</div>
        <div class="quote"><b>CIO decision</b>${esc(ex.cio_rationale)}</div></div></details>` : ''}
      <details class="more"><summary>Reproduction check: ${repLabel}</summary><div>
        <p style="margin:0">Before any comparison, the approach's own code was re-run to confirm it reproduces its saved ${tipw('results', 'reproduction')}. This confirms the decisions are faithful; it says nothing about whether they were good.</p>
        ${rep.checks.map(t => { const w = /re-run|not saved/i.test(t); return `<div class="check${w ? ' warn' : ''}"><i>${w ? '!' : '✓'}</i><span>${esc(t)}</span></div>`; }).join('')}
        ${steps ? `<h3>From its own scoring to the shared rules ${tip('common')}</h3><p class="sub" style="margin:0">Net CER after each adjustment, applied one at a time (${devSpan()}). The approach's decisions never change; only the scoring rules do.</p>
          <div class="chartbox sm"><canvas id="c-steps"></canvas></div>` : '<p class="sub" style="margin:0">This approach already uses the shared trading and cost rules, so its own and shared results are identical.</p>'}
      </div></details>
      <details class="more"><summary>Limitations</summary><div><ul class="list no">${limitations(key).map(t => `<li>${esc(t)}</li>`).join('')}</ul></div></details>
    </div>`;
    lineChart('c-one', 'lg-one', months, [{ label: s.short, data: r.wealth, color: color(key) }, { label: 'Own benchmark', data: bench.wealth, color: css('--c-bench'), dash: BENCH_DASH[0] }], FMT_WEALTH);
    sig.draw();
    weightsChart(document.getElementById('c-w'), months, r.weights);
    const drawSteps = () => { const c = document.getElementById('c-steps'); if (!steps || !c || c.dataset.drawn) return; c.dataset.drawn = '1';
      chart(c, { type: 'bar', data: { labels: steps.map(x => x.step), datasets: [{ data: steps.map(x => x.cer * 100), backgroundColor: steps.map((x, i) => i === steps.length - 1 ? color(key) : css('--c-bench')), borderRadius: 6 }] },
        options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` Net CER: ${it.parsed.y.toFixed(2)}% per year` } } },
          scales: { x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 0, callback: function (v) { const w = this.getLabelForValue(v).split(' '), h = Math.ceil(w.length / 2); return [w.slice(0, h).join(' '), w.slice(h).join(' ')]; } } },
            y: { ticks: { callback: v => v + '%' }, grid: { color: css('--border') } } } } }); };
    document.querySelectorAll('details.more').forEach(d => d.addEventListener('toggle', () => { if (d.open && d.querySelector('#c-steps')) drawSteps(); }));
  }

  function limitations(key) {
    const common = 'Development months were used to build and check the approaches, so these are diagnostics, not protected historical results.';
    if (key === 'det') return [common, 'Forecasts use economic-data surprises only; it ignores prices, news and research.', 'Its model learned from 2015 onward, a short history.'];
    if (key === 'com') return [common, 'GPT-4o was trained on data up to October 2023, so it may know how 2019–2022 turned out.',
      'The saved runs show the asset names and the cash-yield level, which can hint at the period.', 'The uncertainty indexes are today\'s revised values, not those available at the time.'];
    if (key === 'jev') return [common, 'JEV\'s model version, training cutoff, prompt and raw replies were not saved, so its answers can be replayed but not re-created.',
      'Its tilt sizes (±1.5 and ±3 points) were set by hand and not calibrated.', 'Its market snapshot names the assets and shows the cash-yield level, which can hint at the period.'];
    return [common];
  }

  // ---------------------------------------------------------------- Causal RAG
  function viewCausalRag(s) {
    const a = D.ap3, demo = a.demo;
    const flow = [
      ['Knowledge graph', 'kg', 'Cause-and-effect findings from economics papers, limited to papers published before each year.'],
      ['Hypothesis Agent', 'hypothesis', 'Proposes up to ' + a.limits.hypotheses_per_month + ' testable hypotheses a month, each citing research pathways.'],
      ['Causal RAG', 'causalrag', 'Pulls the research behind each pathway: papers, methods and how strong the evidence is.'],
      ['Testing Agent', 'testing', 'Tests each hypothesis ' + a.limits.testing_runs + ' times against dated documents, market moves and a rival explanation.'],
      ['Forecast', 'calibration', 'Turns Supported, Contradicted and Insufficient results into 1-month return forecasts.'],
      ['Allocation', 'bl', 'Black–Litterman sets weights for stocks, Treasuries and corporate bonds.'],
    ];
    const g = a.graph;
    app.innerHTML = `<div class="wrap">
      <section class="hero"><a class="back" href="#approaches">← Approaches</a>
        <h1 class="withswatch">${swatch('rag')}${esc(s.name)} ${tip('causalrag')}</h1>
        <div>${ragBadge()}</div>
        <p class="lede">${esc(s.tagline)}</p>
        <div class="chips"><span class="chip">${esc(s.assets_label)}</span><span class="chip">${esc(s.horizon)}</span><span class="chip">${esc(s.model)}</span></div>
      </section>
      <section class="panel"><h2>Status: ${esc(a.status_label)}</h2>
        <p style="margin:0;color:var(--text-2)">Every part is built and tested without an AI model. No development diagnostics or protected historical results exist yet, so none are shown. Results become available only after the model run is approved and the validation gates pass: a smoke run, Testing Agent fixtures, a development replay, a human audit and calibration checks.</p></section>
      <section><h2>How it works</h2><div class="flow">${flow.map(([t, k, d]) => `<div><b>${t} ${tip(k)}</b>${esc(d)}</div>`).join('')}</div></section>
      <section>
        <div class="row between"><h2>What it will draw on</h2><span class="pill inv"><span class="dot"></span>Research inventory · not a result ${tip('inventory')}</span></div>
        <div class="grid2">
          <div class="panel"><h3>Research papers available each year ${tip('kg')}</h3><p class="sub">Each decision year sees only research published before it.</p>
            <div class="chartbox sm"><canvas id="c-kg"></canvas></div></div>
          <div class="panel"><h3>Research pathways by economic channel</h3><p class="sub">Pathways linking the tracked economic events to the three assets, for ${g.at(-1).decision_year} decisions. A count of available research, not a result.</p>
            <div class="chartbox sm"><canvas id="c-ch"></canvas></div></div>
        </div>
      </section>
      ${demo ? demoBlock(demo) : ''}
      <details class="more"><summary>Safeguards</summary><div><ul class="list">
        <li>Each year's graph only contains papers published before that year, and claims mentioning later events are removed.</li>
        <li>Documents and market data are filtered to what was public before each decision, at 8 p.m. New York time.</li>
        <li>Quotes the Testing Agent cites must appear word for word in the documents it was given; anything else is rejected.</li>
        <li>Each hypothesis is tested three times independently; a split decision counts as Insufficient.</li>
        <li>“Supported” means consistent with the evidence available at the time. It is never treated as proof of cause.</li>
        <li>The graph rebuilds identically from the same data: ${a.graph_rebuild_identical ? 'checked' : 'not yet checked'}.</li></ul></div></details>
    </div>`;
    chart(document.getElementById('c-kg'), { type: 'bar', data: { labels: g.map(x => x.decision_year), datasets: [{ label: 'Papers', data: g.map(x => x.papers), backgroundColor: color('rag'), borderRadius: 4 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.parsed.y.toLocaleString()} papers · ${g[it.dataIndex].claims.toLocaleString()} claims` } } },
        scales: { x: { grid: { display: false } }, y: { ticks: { callback: v => v === 0 ? '0' : (v / 1000) + 'k' }, grid: { color: css('--border') } } } } });
    const last = g.at(-1).pathways_by_channel;
    const names = { growth: 'Growth', inflation: 'Inflation', policy_rates: 'Policy & rates', risk_credit: 'Risk & credit', other: 'Other', direct: 'Direct' };
    const order = Object.keys(names).filter(k => k in last);
    chart(document.getElementById('c-ch'), { type: 'bar', data: { labels: order.map(k => names[k]), datasets: [{ data: order.map(k => last[k]), backgroundColor: color('rag'), borderRadius: 4 }] },
      options: { indexAxis: 'y', plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.parsed.x} pathways` } } }, scales: { x: { grid: { color: css('--border') } }, y: { grid: { display: false } } } } });
  }

  function demoBlock(d) {
    const arrow = v => v > 0 ? '▲ up' : v < 0 ? '▼ down' : '— no view';
    const n = v => v > 0 ? `+${v}` : v < 0 ? `−${-v}` : '0';
    return `<section class="panel demo-panel">
      <div class="row between"><h2>One month, step by step</h2><span class="pill demo"><span class="dot"></span>Demo ${tip('mock')}</span></div>
      <div class="demo-banner"><b>Demo only.</b><span>This walk-through uses canned responses and synthetic documents to show the screens. Nothing in this box is a result.</span></div>
      <div class="flow">
        <div><b>1 · Event</b>${d.triggers.map(t => `${esc(t.event)}${t.surprise_z != null ? ` (surprise ${n(t.surprise_z)} std)` : ''}`).join('<br>')}</div>
        ${d.hypotheses.map(h => `
        <div><b>2 · Hypothesis</b>Channel: ${esc(h.channel)}<br>Predicted: stocks ${arrow(h.predicted.SPY)}, Treasuries ${arrow(h.predicted.IEF)}, corporate bonds ${arrow(h.predicted.LQD)}</div>
        <div><b>3 · Research</b>${h.research_records} papers behind ${h.graph_paths_cited} pathway${h.graph_paths_cited === 1 ? '' : 's'} (${h.research_years[0]}–${h.research_years.at(-1)})</div>
        <div><b>4 · Testing</b><div class="runs">${h.testing_runs.map((r, i) => `<span>Run ${i + 1}: <span class="status ${r.status}">${r.status}</span>${r.rejected_citations ? `<br><small class="sub">${r.rejected_citations} invalid quote rejected</small>` : ''}</span>`).join('')}</div></div>
        <div><b>5 · Verdict</b><span class="status ${h.final_status}">${h.final_status}</span><span>${Math.round(h.run_agreement * 100)}% of runs agree</span><span class="sub">Causal proof: not established</span></div>`).join('')}
        <div><b>6 · Signals ${tip('signals')}</b>${['SPY', 'IEF', 'LQD'].map(x => `<span><b class="asset">${PLAIN[x]}</b>Supported ${n(d.signals[x].F_S)} · Contradicted ${n(d.signals[x].F_C)} · Insufficient ${n(d.signals[x].F_I)}</span>`).join('')}</div>
      </div>
    </section>`;
  }

  // ---------------------------------------------------------------- experiments
  function viewExperiments() {
    const E = D.experiments, months = D.dev.months;
    const w = D.dev.within_contrasts[0];
    const keys = ['com', 'jev'];
    const bk = S('jev').neutral;
    const rowsDef = [
      ['cer', 'Net CER', m => m.cer, pct], ['sharpe', 'Sharpe ratio', m => m.sharpe, v => num(v)], ['excess', 'Annual return above cash', m => m.ann_excess_return, pct],
      ['volatility', 'Volatility', m => m.volatility, pct], ['drawdown', 'Worst fall', m => m.max_drawdown, pct], ['turnover', 'Turnover', m => m.turnover, v => pct(v, 0)],
    ];
    const expCard = e => `<article class="card exp${e.status === 'proposed' ? ' proposed' : ''}">
      <div class="row between"><div class="name">${e.key ? swatch(e.key) : '<span class="swatch hollow"></span>'}${e.key ? `<a class="stretch" href="#${SLUG[e.key]}">${esc(e.name)}</a>` : esc(e.name)}</div>${statusChip(e.status)}</div>
      <p>${esc(e.detail)}</p></article>`;
    app.innerHTML = `<div class="wrap">
      <section><h1>Experiments</h1>
        <p class="lede">The primary comparison is between the three approaches. These experiments are reported separately and never enter it.</p></section>
      <section><h2>Within the Agentic Workflow ${tip('variant')}</h2>
        <div class="cards three">${E.within.map(expCard).join('')}</div></section>
      <section class="panel">
        <div class="row between"><h2>Committee only vs JEV only</h2><span class="pill ok"><span class="dot"></span>Development diagnostics, ${devSpan()}</span></div>
        <p class="sub">Both hold US stocks and 20+ year Treasuries, read the same market snapshot and share the same 60/40 benchmark, so this comparison isolates how the views are formed.</p>
        <div class="legend" id="lg-exp"></div>
        <div class="chartbox sm"><canvas id="c-exp"></canvas></div>
        <div class="scroll"><table class="score stack"><thead><tr><th>Development diagnostics</th>${keys.map(k => `<th>${swatch(k)}${name(k)}</th>`).join('')}</tr></thead>
          <tbody>${rowsDef.map(([k, l, get, fmt]) => `<tr><td><span class="metricname">${l}${tip(k)}</span></td>${keys.map(x => `<td class="num" data-label="${name(x)}">${fmt(get(S(x).metrics))}</td>`).join('')}</tr>`).join('')}
          <tr><td><span class="metricname">Net CER vs 60/40 benchmark${tip('benchmark')}</span></td>${keys.map(x => `<td class="num" data-label="${name(x)}">${pts(S(x).vs_neutral.cer_difference)}</td>`).join('')}</tr></tbody></table></div>
        <div class="contrast"><ul class="list"><li>${contrastSentence(w)}</li></ul>
          <p class="sub">A within-approach result. It does not change the primary comparison, where JEV represents the Agentic Workflow.</p></div>
      </section>
      <section><h2>Secondary experiments</h2>
        <div class="cards three">${E.secondary.map(e => expCard({ ...e, key: null })).join('')}</div>
        <p class="sub">Proposed experiments are specified before they run and are reported apart from the primary comparison.</p></section>
    </div>`;
    lineChart('c-exp', 'lg-exp', months, keys.map(k => ({ label: sys(k).short, data: S(k).wealth, color: color(k) }))
      .concat([{ label: `Benchmark: ${D.dev.benchmarks[bk].label}`, data: D.dev.benchmarks[bk].wealth, color: css('--c-bench'), dash: BENCH_DASH[0] }]), FMT_WEALTH);
  }

  // ---------------------------------------------------------------- timeline
  function viewTimeline() {
    const w = D.windows;
    const phases = [
      { cls: 'train', name: 'Training', tipk: 'training', when: `${monthLabel(w.training[0])} – ${monthLabel(w.training[1])}`, what: 'Macro data the models learn from' },
      { cls: 'dev', name: 'Development diagnostics', tipk: 'development', when: `${monthLabel(w.development[0])} – ${monthLabel(w.development[1])}`, what: 'Shown on this dashboard' },
      { cls: 'test', name: 'Protected historical test', tipk: 'test', when: `${monthLabel(w.historical_test[0])} – ${monthLabel(w.historical_test[1])}`, what: 'Sealed until the freeze' },
      { cls: 'pro', name: 'Live tracking', tipk: 'prospective', when: 'After the freeze', what: 'Not started' },
    ];
    const STATE = { scored: 'Development diagnostics shown', learn: 'Model learns from these months', saved: 'Saved decisions exist; not scored',
      sealed: 'Saved decisions, sealed', later: 'Generated after the freeze', none: 'Not yet run', awaiting: 'Awaiting validation' };
    const rows = [
      ['det', 'Deterministic', ['learn', 'scored', 'later', 'none']],
      ['jev', 'Agentic Workflow (JEV)', ['saved', 'scored', 'sealed', 'none']],
      ['rag', 'Causal RAG', ['awaiting', 'awaiting', 'awaiting', 'none']],
    ];
    const variantRow = ['com', 'Agent Committee', ['saved', 'scored', 'sealed', 'none']];
    const bar = (c, st) => `<span class="bar ${st}" style="--c:${c}" title="${esc(STATE[st])}"></span>`;
    const legend = [['scored', 'Development diagnostics shown'], ['learn', 'Model learning, or saved decisions not scored'], ['sealed', 'Saved decisions, sealed'], ['awaiting', 'Awaiting validation'], ['none', 'Not yet run']];
    const gridRow = ([k, label, st], cls) => `<div role="row" class="tlrow${cls ? ' ' + cls : ''}"><span role="rowheader">${swatch(k)} ${label}</span>${st.map((x, i) => `<span role="cell" aria-label="${esc(phases[i].name)}: ${esc(STATE[x])}">${bar(color(k), x)}</span>`).join('')}</div>`;
    app.innerHTML = `<div class="wrap">
      <section><h1>Timeline</h1><p class="lede">The primary research timeline starts with the February 2015 macro-data training period. Approaches are built on training and development months, then frozen. Only then is the protected historical test scored, once, followed by live tracking.</p></section>
      <section class="panel tlpanel">
        <div class="tlgrid" role="table" aria-label="Which months each approach has run">
          <div role="row" class="tlhead"><span role="columnheader"></span>${phases.map(p => `<div role="columnheader" class="tlseg ${p.cls}"><b>${p.name} ${tip(p.tipk)}</b><small>${p.when}</small><small>${p.what}</small></div>`).join('')}</div>
          ${rows.map(r => gridRow(r)).join('')}
          <div role="row" class="tlsub"><span role="rowheader">Within-approach variant</span></div>
          ${gridRow(variantRow, 'variant')}
        </div>
        <div class="tlv">${phases.map((p, i) => `<div class="tlseg ${p.cls}"><b>${p.name} ${tip(p.tipk)}</b><small>${p.when} · ${p.what}</small>
          <ul>${rows.concat([variantRow]).map(([k, label, st]) => `<li>${bar(color(k), st[i])}<span>${label}: ${esc(STATE[st[i]])}</span></li>`).join('')}</ul></div>`).join('')}</div>
        <div class="tllegend">${legend.map(([st, t]) => `<span>${bar(css('--text-2'), st)}${t}</span>`).join('')}</div>
        <p class="sub" style="margin:0">Development diagnostics are not protected historical results: the approaches were built and checked on those months. The Deterministic model's protected-test decisions are generated only after the freeze; Causal RAG runs from 2015 once its model is approved and validated.</p>
      </section>
      <section class="grid2">
        <div class="panel"><h2>Walk-forward validation ${tip('walkforward')}</h2><ol class="steps one">
          <li>At 8 p.m. New York time on the last trading day of each month, each approach decides using only information public by then.</li>
          <li>The portfolio is traded at the next day's closing prices and held for a month.</li>
          <li>Models with fitted parts are refit each month on past months only, then the window moves forward.</li></ol></div>
        <div class="panel"><h2>Two stages of checking</h2><ol class="steps one">
          <li><b>Reproduction check ${tip('reproduction')}</b><br>Each approach's own code reproduces its saved results exactly.</li>
          <li><b>Shared rules ${tip('common')}</b><br>The same decisions are then scored with shared timing, costs and cash rate. The effect of each adjustment is reported.</li></ol></div>
      </section></div>`;
  }

  // ---------------------------------------------------------------- method
  function viewMethod() {
    const pc = D.dev.primary_contrasts.items;
    app.innerHTML = `<div class="wrap">
      <section><h1>How it's scored</h1><p class="lede">Shared rules decide how results are measured. Everything that forms views or sets weights stays each approach's own.</p></section>
      <section class="panel cer-def"><h2>Primary metric: Net CER (Certainty-Equivalent Return)</h2>
        <p class="formula num">Net CER = 12 × ( average monthly net excess return − ½ × 2.5 × variance of monthly net excess return )</p>
        <p style="margin:0;color:var(--text-2)">The guaranteed yearly return above cash that a risk-averse investor (risk aversion 2.5) would accept instead of the strategy. It rewards return and penalises volatility, after trading costs. It is not a compound annual return (CAGR).</p></section>
      <section class="panel"><h2>Primary comparison</h2>
        <p style="margin:0;color:var(--text-2)">Three approaches: the Deterministic Quantitative Model, the Agentic Workflow (represented by JEV) and Agentic Causal RAG. Their pairwise net-CER differences form one family of three, corrected together (Holm) ${tip('significance')}</p>
        <ul class="list">${pc.map(c => `<li>${name(c.a)} vs ${name(c.b)}: ${c.computed ? 'computed on development months' : 'pending, Causal RAG results unavailable'}</li>`).join('')}</ul>
        <p class="sub">The Agent Committee (a within-approach variant) and the secondary experiments are reported separately and never enter this family.</p></section>
      <section class="grid2">
        <div class="panel"><h2>Same for every approach</h2><ul class="list">
          <li>Decisions at 8 p.m. New York time on the last trading day of each month</li>
          <li>Trades at the next trading day's close, held for one month</li>
          <li>Trading cost of 0.05% of every dollar traded</li>
          <li>Cash earns the 4-week Treasury bill rate</li>
          <li>Prices from fixed, verified copies of public data</li>
          <li>Scored by net ${tipw('CER', 'cer')} with Sharpe, worst fall and turnover alongside</li></ul></div>
        <div class="panel"><h2>Each approach's own</h2><ul class="list">
          <li>Which assets it holds and its forecast horizon</li>
          <li>Its data, prompts and AI model</li>
          <li>How it turns views into portfolio ${tipw('weights', 'bl')}</li>
          <li>Its starting mix, used as its own ${tipw('benchmark', 'benchmark')}</li></ul></div>
      </section>
      <details class="more" open><summary>Why this is not a controlled comparison</summary><div><ul class="list no">
        <li>The Agentic Workflow holds stocks with 20+ year Treasuries; the other two approaches hold stocks, 7–10 year Treasuries and corporate bonds.</li>
        <li>Horizons differ: the Agentic Workflow uses 12-month views; the other two use 1-month forecasts.</li>
        <li>Each reads different information, from data surprises alone to research papers and documents.</li>
        <li>Comparing each approach with its own benchmark helps, but it does not remove these differences.</li></ul></div></details>
      <details class="more"><summary>Development diagnostics vs protected historical results</summary><div><ul class="list">
        <li>Development diagnostics (${devSpan()}) come from months the approaches were built and checked on. They can reveal problems but cannot show which approach is better.</li>
        <li>Protected historical results (${testSpan()}) will be scored once, after the freeze. None exist yet; the scoring software refuses to open those months without a signed approval.</li>
        <li>The primary research timeline starts with the February 2015 macro-data training period.</li></ul></div></details>
      <details class="more"><summary>Keeping the test honest</summary><div><ul class="list">
        <li>Every input is used only after its publication time.</li>
        <li>Saved AI outputs are replayed exactly as recorded; nothing missing is filled in or invented.</li>
        <li>Demo screens are labelled and can never enter results.</li>
        <li>AI models may have seen past market history during training. This is disclosed; only live months are free of it.</li></ul></div></details>
      <details class="more"><summary>Statistics</summary><div><ul class="list">
        <li>Differences are measured on the same months for both approaches being compared.</li>
        <li>Uncertainty comes from resampling 6-month blocks of returns 5,000 ${tipw('times', 'ci')}</li>
        <li>The three primary comparisons are corrected together for multiple testing ${tipw('(Holm)', 'significance')}</li>
        <li>With 46 development months, only large differences can be detected; a non-significant result means “not enough evidence”, not “no difference”.</li></ul></div></details>
    </div>`;
  }

  // ---------------------------------------------------------------- router
  function route() {
    if (!D) return;
    killCharts();
    chartDefaults();
    const h = (location.hash || '#overview').slice(1);
    const key = ROUTES[h];
    const view = key ? (key === 'com' ? 'experiments' : 'approaches') : (['overview', 'approaches', 'experiments', 'timeline', 'method'].includes(h) ? h : 'overview');
    document.querySelectorAll('nav a').forEach(a => { if (a.dataset.route === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    try {
      if (key) viewApproach(key);
      else if (view === 'approaches') viewApproaches();
      else if (view === 'experiments') viewExperiments();
      else if (view === 'timeline') viewTimeline();
      else if (view === 'method') viewMethod();
      else viewOverview();
    } catch (e) {
      console.error(e);
      app.innerHTML = `<div class="wrap"><p class="err">This view could not be drawn: ${esc(e.message)}</p></div>`;
    }
    window.scrollTo(0, 0);
  }

  // Tooltips: hover or focus on desktop, tap on touch screens. The popover is fixed-positioned and
  // clamped inside the viewport, so it never widens the page.
  function place(t) {
    const s = t.querySelector(':scope > span'), r = t.getBoundingClientRect();
    t.classList.add('show');
    const w = s.offsetWidth, h = s.offsetHeight, vw = document.documentElement.clientWidth;
    const left = Math.min(Math.max(12, r.left + r.width / 2 - w / 2), vw - w - 12);
    let top = r.top - h - 8;
    if (top < 8) top = r.bottom + 8;
    s.style.left = left + 'px'; s.style.top = top + 'px';
  }
  const hide = t => { t.classList.remove('show', 'open'); };
  document.addEventListener('mouseover', e => { const t = e.target.closest('.tip'); if (t && !t.classList.contains('show')) place(t); });
  document.addEventListener('mouseout', e => { const t = e.target.closest('.tip'); if (t && !t.contains(e.relatedTarget) && !t.classList.contains('open')) hide(t); });
  document.addEventListener('focusin', e => { const t = e.target.closest('.tip'); if (t) place(t); });
  document.addEventListener('focusout', e => { const t = e.target.closest('.tip'); if (t && !t.classList.contains('open')) hide(t); });
  document.addEventListener('click', e => {
    const b = e.target.closest('.tip > button');
    document.querySelectorAll('.tip.show').forEach(t => { if (!b || t !== b.parentElement) hide(t); });
    if (b) { e.preventDefault(); e.stopPropagation(); const t = b.parentElement;
      if (t.classList.contains('open')) hide(t); else { t.classList.add('open'); place(t); } }
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.tip.show').forEach(hide); });
  window.addEventListener('scroll', () => document.querySelectorAll('.tip.show').forEach(hide), { passive: true });
  window.addEventListener('hashchange', route);
  try { window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', route); } catch (_) { /* older browsers */ }
  new MutationObserver(route).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  fetch('data/dashboard.json', { cache: 'no-store' })
    .then(r => { if (!r.ok) throw new Error(`results file not found (${r.status})`); return r.json(); })
    .then(j => {
      D = j;
      document.getElementById('foot-right').textContent = `Results built ${j.generated_at_utc.slice(0, 10)} · development diagnostics only`;
      route();
    })
    .catch(e => { app.innerHTML = `<div class="wrap"><p class="err">Results could not be loaded: ${esc(e.message)}. Start the dashboard with the local server described in the README.</p></div>`; });
})();
