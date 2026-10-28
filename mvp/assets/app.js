/* Protofin Backtest dashboard. Reads data/dashboard.json (built by mvp/build_dashboard_data.py). */
(function () {
  'use strict';

  const GLOSSARY = {
    cer: 'Net CER (certainty-equivalent return): the safe yearly return a cautious investor would accept instead of this strategy. It rewards return and penalises risk. Higher is better.',
    sharpe: 'Sharpe ratio: return earned above cash for each unit of risk taken. Higher is better.',
    drawdown: 'Maximum drawdown (worst fall): the largest drop from a peak to a later low. Closer to zero is better.',
    excess: 'Annual return above cash: yearly return after trading costs, minus what Treasury bills paid.',
    volatility: 'Volatility: how much returns swing, expressed per year. Lower means a smoother ride.',
    turnover: 'Turnover: share of the portfolio traded per year. More trading means more cost.',
    growth: 'What $1 invested at the start would be worth each month, after trading costs.',
    gap: 'How much more (or less) $1 in the approach was worth than $1 in its own benchmark, in percent. Above zero means ahead.',
    benchmark: 'Own benchmark: the approach\'s starting mix (for example 60% stocks, 40% bonds), held fixed and rebalanced monthly. The gap shows what the approach\'s forecasts added.',
    significance: 'Statistically significant: the gap is too large to be explained by chance alone (5% level, corrected for making several comparisons).',
    ci: 'Likely range: where the true difference most likely lies (95% confidence). If it includes zero, the gap could be chance.',
    bl: 'Black–Litterman: a standard method that starts from a neutral portfolio and tilts it toward forecasts in proportion to how confident they are.',
    walkforward: 'Walk-forward validation: each month the model is rebuilt using only data available at that time, then judged on the following month.',
    causalrag: 'Causal RAG: AI retrieval guided by a map of cause-and-effect findings from economics research, rather than by keyword similarity alone.',
    kg: 'Knowledge graph: a network of cause-and-effect claims extracted from published economics papers. Each year only uses papers published before it.',
    hypothesis: 'Hypothesis Agent: proposes how this month\'s events could move markets, citing pathways in the research graph.',
    testing: 'Testing Agent: tries to disprove each hypothesis against dated documents, market data and a rival explanation. "Supported" means consistent with evidence, not proven.',
    calibration: 'Calibration model: a statistical model that learns, from past months only, how much tested hypotheses moved returns.',
    development: 'Development period: months used to build and check the approaches. Results are diagnostics, not proof.',
    test: 'Historical test: months held back and scored once, after everything is frozen. Still sealed.',
    prospective: 'Live tracking: months after the freeze. The strongest evidence, because no one could have seen them in advance.',
    reproduction: 'Reproduction check: re-running each approach\'s own code to confirm it gives exactly the results its authors saved.',
    common: 'Shared rules: scoring every approach with the same trade timing, trading costs and cash rate.',
    mock: 'Demo: example output generated without an AI model to show how this screen works. It is not a result.',
    ridge: 'Ridge regression: a linear model that shrinks weak signals toward zero to avoid overfitting.',
    jev: 'JEV: an AI decision model that answers one question each month: will stocks beat bonds over the next 12 months?',
    confidence: 'How sure the approach said it was. Higher confidence moves the portfolio further from its starting mix.',
    regime: 'When policy or geopolitical uncertainty is very high, the Committee automatically lowers its confidence by one level.',
    extended: 'Longer history: this approach\'s saved decisions back to 2011. It includes years before the development period, is context only, and is not compared with the other approaches.',
    inventory: 'Research inventory: how much published research the approach can draw on. It describes inputs, not performance.',
    signals: 'For each asset, the predicted directions (up = +1, down = −1) of the hypotheses that reached each verdict, added up. The forecast model learns how much each kind is worth.',
  };
  const ROUTES = { deterministic: 'det', committee: 'com', jev: 'jev', 'causal-rag': 'rag' };
  const SLUG = { det: 'deterministic', com: 'committee', jev: 'jev', rag: 'causal-rag' };
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
  const sys = key => D.systems.find(s => s.key === key);
  const color = key => css(VAR[key]) || '#888';
  const assetColor = a => css(ASSET_VAR[a]) || '#888';
  const swatch = key => `<span class="swatch" style="background:${color(key)}"></span>`;
  const withResults = () => D.systems.filter(s => s.has_results && D.dev.series[s.key]);
  const S = key => D.dev.series[key];
  const killCharts = () => { charts.forEach(c => c.destroy()); charts = []; };
  const killChart = id => charts.filter(c => c.canvas.id === id).forEach(c => { c.destroy(); charts = charts.filter(x => x !== c); });

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
    const rag = sys('rag');
    return `<div class="pills">
      <span class="pill ok"><span class="dot"></span>Development results, ${monthLabel(D.windows.development[0])} – ${monthLabel(D.windows.development[1])} ${tip('development')}</span>
      <span class="pill lock"><span class="dot"></span>Historical test ${D.windows.historical_test[0].slice(0, 4)}–${D.windows.historical_test[1].slice(0, 4)}: sealed ${tip('test')}</span>
      <span class="pill wait"><span class="dot"></span>Live tracking: not started ${tip('prospective')}</span>
      ${rag && !rag.has_results ? `<span class="pill wait"><span class="dot"></span>${esc(rag.name)}: waiting for model approval</span>` : ''}
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
      : `<div class="pending">Built and tested; results appear once the AI model is approved to run.</div>
         <div class="foot"><span>How it works, with a labelled demo</span><span class="more">Details →</span></div>`;
    return `<article class="card">
      <div class="name">${swatch(s.key)}<a class="stretch" href="#${SLUG[s.key]}">${esc(s.name)}</a></div>
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

  // One shared, symmetric axis for every approach, so the bars can be compared across pages.
  function ciAxis() {
    const all = withResults().flatMap(s => S(s.key).vs_neutral.ci95.map(Math.abs));
    return Math.max(0.01, Math.ceil(Math.max(...all) * 100) / 100);
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

  // ---------------------------------------------------------------- overview
  function viewOverview() {
    const res = withResults();
    const months = D.dev.months;
    const anySig = Object.values(D.dev.pairwise).some(p => p.significant) || res.some(s => S(s.key).vs_neutral.p < 0.05);
    const bkeys = Object.keys(D.dev.benchmarks);
    const users = bk => res.filter(s => S(s.key).neutral === bk).map(s => s.short).join(' & ');
    const metrics = [
      ['cer', 'Net CER', s => S(s).metrics.cer, pct, true, 'per year'],
      ['benchmark', 'Net CER vs own benchmark', s => S(s).vs_neutral.cer_difference, pts, true, 'per year'],
      ['sharpe', 'Sharpe ratio', s => S(s).metrics.sharpe, v => num(v), true, ''],
      ['excess', 'Annual return above cash', s => S(s).metrics.ann_excess_return, pct, true, 'after costs'],
      ['volatility', 'Volatility', s => S(s).metrics.volatility, pct, false, 'per year'],
      ['drawdown', 'Worst fall', s => S(s).metrics.max_drawdown, pct, true, ''],
      ['turnover', 'Turnover', s => S(s).metrics.turnover, v => pct(v, 0), false, 'per year'],
    ];
    const rows = metrics.map(([k, label, get, fmt, higher, unit]) => {
      const vals = res.map(s => get(s.key));
      const lead = higher ? Math.max(...vals) : Math.min(...vals);
      return `<tr><td><span class="metricname">${label}${tip(k)}${unit ? `<small>${unit}</small>` : ''}</span></td>` +
        res.map((s, i) => `<td class="num${vals[i] === lead ? ' lead' : ''}" data-label="${esc(s.short)}">${fmt(vals[i])}</td>`).join('') +
        `<td class="num na" data-label="Causal RAG">—</td></tr>`;
    }).join('');
    const growthLines = mode => mode === 'gap'
      ? res.map(s => { const b = D.dev.benchmarks[S(s.key).neutral].wealth; return { label: s.short, data: S(s.key).wealth.map((w, i) => (w / b[i] - 1) * 100), color: color(s.key) }; })
          .concat([{ label: 'Own benchmark', data: months.map(() => 0), color: css('--c-bench'), dash: BENCH_DASH[0] }])
      : res.map(s => ({ label: s.short, data: S(s.key).wealth, color: color(s.key) }))
          .concat(bkeys.map((bk, i) => ({ label: `Benchmark: ${users(bk)}`, data: D.dev.benchmarks[bk].wealth, color: css('--c-bench'), dash: BENCH_DASH[i % 2] })));
    const growthNote = {
      abs: `Dashed lines are the benchmarks, each a fixed mix: ${bkeys.map(bk => `${esc(D.dev.benchmarks[bk].label)} for ${esc(users(bk))}`).join('; ')}. The two groups hold different assets.`,
      gap: 'Each line shows how much more (or less) $1 in the approach was worth than $1 in its own benchmark. Above zero means ahead.',
    };
    const range = w => { const v = w.SPY; const avg = v.reduce((a, b) => a + b, 0) / v.length; return `Stocks ${pct(Math.min(...v), 0)}–${pct(Math.max(...v), 0)}, average ${pct(avg, 0)}`; };
    app.innerHTML = `<div class="wrap">
      <section>
        <h1>How do four ways of building a portfolio compare?</h1>
        <p class="lede">From a classic statistical model to AI agents reasoning over economic research. Each approach keeps its own design; all are scored by the same rules: same months, same trading costs, same cash rate.</p>
        ${statusPills()}
        <div class="finding"><b>So far</b><span>${esc(D.notes.headline)}</span></div>
      </section>
      <section aria-label="Approaches"><div class="cards">${D.systems.map(s => card(s)).join('')}</div></section>
      <section class="two">
        <div class="panel"><h2>What the results show</h2><ul class="list">${D.notes.can.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>
        <div class="panel"><h2>What they can't show yet</h2><ul class="list no">${D.notes.cannot.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>
      </section>
      <section class="panel">
        <div class="row between"><h2 id="g-title">Growth of $1, after costs ${tip('growth')}</h2>
          <div class="seg" role="group" aria-label="Chart view"><button type="button" data-g="abs" aria-pressed="true">Growth of $1</button><button type="button" data-g="gap" aria-pressed="false">Versus own benchmark</button></div></div>
        <div class="legend" id="lg-growth"></div>
        <div class="chartbox"><canvas id="c-growth" aria-label="Growth of one dollar for each approach"></canvas></div>
        <p class="sub" id="g-note"></p>
      </section>
      <section class="panel">
        <div class="row between"><h2>How they compare</h2>
          <span class="pill ${anySig ? 'ok' : 'wait'}"><span class="dot"></span>${anySig ? 'Some differences are statistically significant' : 'No difference is statistically significant'} ${tip('significance')}</span></div>
        <div class="scroll"><table class="score stack"><thead><tr><th>${monthLabel(months[0])} – ${monthLabel(months.at(-1))}</th>${res.map(s => `<th>${swatch(s.key)}${esc(s.short)}</th>`).join('')}<th>${swatch('rag')}Causal RAG</th></tr></thead>
          <tbody>${rows}</tbody></table></div>
        <p class="sub"><span class="leadmark" aria-hidden="true"></span> marks the strongest value in each row for this period only.${anySig ? '' : ' None of the gaps is statistically significant.'} Causal RAG shows no values until its model run is approved.</p>
      </section>
      <section class="panel">
        <h2>How allocations changed</h2><p class="sub">Share of the portfolio in each asset, month by month. Each approach moves within its own limits.</p>
        <div class="minis">${res.map(s => `<div class="mini"><h3>${swatch(s.key)}${esc(s.short)}</h3>
          <div class="chartbox xs"><canvas id="c-alloc-${s.key}" aria-label="${esc(s.short)} portfolio weights over time"></canvas></div>
          <p class="sub num">${range(S(s.key).weights)}</p></div>`).join('')}</div>
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
    ];
    app.innerHTML = `<div class="wrap">
      <section><h1>The four approaches</h1>
        <p class="lede">Each approach keeps its own design, data and allocation rules. Only the scoring is shared.</p></section>
      <section><div class="cards">${D.systems.map(s => card(s, true)).join('')}</div></section>
      <section class="panel"><h2>At a glance</h2>
        <div class="scroll"><table class="score stack one glance"><thead><tr><th>Approach</th>${cols.map(([l], i) => `<th>${l}${i === 3 ? ' ' + tip('bl') : ''}</th>`).join('')}</tr></thead>
        <tbody>${D.systems.map(s => `<tr><td><a href="#${SLUG[s.key]}" class="rowname">${swatch(s.key)}${esc(s.name)}</a></td>${cols.map(([l, f]) => `<td data-label="${esc(l)}">${esc(f(s))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
        <p class="sub">Because the approaches hold different assets and use different horizons and information, comparing them is a comparison of complete strategies, not a controlled experiment.</p>
      </section></div>`;
  }

  // ---------------------------------------------------------------- one approach
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
    const r = S(key);
    const months = D.dev.months;
    const bench = D.dev.benchmarks[r.neutral];
    const sig = signalsBlock(s, r);
    const rep = D.reproduction[key];
    const steps = D.native_vs_common[key];
    const ext = D.extended.series[key];
    const ex = r.example;
    const vs = r.vs_neutral;
    const zeroIn = vs.ci95[0] <= 0 && vs.ci95[1] >= 0;
    const repLabel = { reproduced: 'matched saved results', replayed: 'matched saved results (replay only)' }[rep.status] || 'did not match';
    app.innerHTML = `<div class="wrap">
      <section class="hero"><a class="back" href="#overview">← Overview</a>
        <h1 class="withswatch">${swatch(key)}${esc(s.name)}</h1>
        <p class="lede">${esc(s.tagline)}</p>
        <div class="chips"><span class="chip">${esc(s.assets_label)}</span><span class="chip">${esc(s.horizon)}</span><span class="chip">${esc(s.model)}</span></div>
      </section>
      <section><h2>How it works</h2><ol class="steps">${s.steps.map(t => `<li>${esc(t)}</li>`).join('')}</ol></section>
      <section class="grid2">
        <div class="panel"><h2>Development results ${tip('development')}</h2>
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
          <div class="row between"><h2>Growth of $1 ${tip('growth')}</h2>
            ${ext ? `<div class="seg" role="group" aria-label="Period"><button type="button" data-p="dev" aria-pressed="true">2019–2022</button><button type="button" data-p="ext" aria-pressed="false">Longer history</button></div>` : ''}</div>
          <div class="legend" id="lg-one"></div>
          <div class="chartbox sm"><canvas id="c-one"></canvas></div>
          ${ext ? `<p class="sub note" id="ext-note" hidden>Longer history, ${monthLabel(D.extended.months[0])} – ${tipw(monthLabel(D.extended.months.at(-1)), 'extended')}: includes years before the development period. Context for this approach only; not a test and not compared with the others.</p>` : ''}
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
        ${steps ? `<h3>From its own scoring to the shared rules ${tip('common')}</h3><p class="sub" style="margin:0">Net CER after each adjustment, applied one at a time (2019–2022). The approach's decisions never change; only the scoring rules do.</p>
          <div class="chartbox sm"><canvas id="c-steps"></canvas></div>` : '<p class="sub" style="margin:0">This approach already uses the shared trading and cost rules, so its own and shared results are identical.</p>'}
      </div></details>
      <details class="more"><summary>Limitations</summary><div><ul class="list no">${limitations(key).map(t => `<li>${esc(t)}</li>`).join('')}</ul></div></details>
    </div>`;
    const drawOne = which => {
      const src = which === 'ext' ? { m: D.extended.months, a: ext.wealth, b: Object.values(D.extended.benchmarks)[0].wealth } : { m: months, a: r.wealth, b: bench.wealth };
      lineChart('c-one', 'lg-one', src.m, [{ label: s.short, data: src.a, color: color(key) }, { label: 'Own benchmark', data: src.b, color: css('--c-bench'), dash: BENCH_DASH[0] }], FMT_WEALTH);
      const note = document.getElementById('ext-note'); if (note) note.hidden = which !== 'ext';
    };
    drawOne('dev');
    document.querySelectorAll('[data-p]').forEach(b => b.addEventListener('click', () => {
      document.querySelectorAll('[data-p]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); drawOne(b.dataset.p); }));
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
    const common = 'Development months were used to build and check the approaches, so these results are diagnostics, not proof.';
    if (key === 'det') return [common, 'Forecasts use economic-data surprises only; it ignores prices, news and research.', 'Its model learned from 2015 onward, a short history.'];
    if (key === 'com') return [common, 'GPT-4o was trained on data up to October 2023, so it may know how 2019–2022 turned out.',
      'The saved runs show the asset names and the cash-yield level, which can hint at the period.', 'The uncertainty indexes are today\'s revised values, not those available at the time.'];
    if (key === 'jev') return [common, 'JEV\'s model version, training cutoff, prompt and raw replies were not saved, so its answers can be replayed but not re-created.',
      'Its tilt sizes (±1.5 and ±3 points) were set by hand and not calibrated.', 'It sees the same snapshot as the Committee, with the same hints about the period.'];
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
      <section class="hero"><a class="back" href="#overview">← Overview</a>
        <h1 class="withswatch">${swatch('rag')}${esc(s.name)} ${tip('causalrag')}</h1>
        <p class="lede">${esc(s.tagline)}</p>
        <div class="chips"><span class="chip">${esc(s.assets_label)}</span><span class="chip">${esc(s.horizon)}</span><span class="chip">${esc(s.model)}</span></div>
      </section>
      <section class="panel"><div class="row between"><h2>Status</h2><span class="pill wait"><span class="dot"></span>Waiting for model approval</span></div>
        <p style="margin:0;color:var(--text-2)">Every part is built and tested without an AI model. Real results appear once the model run is approved. There are no performance numbers yet, so none are shown.</p></section>
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

  // ---------------------------------------------------------------- timeline
  function viewTimeline() {
    const w = D.windows;
    const phases = [
      { cls: 'train', name: 'Training & earlier history', tipk: null, when: `Before ${monthLabel(w.development[0])}`, what: 'Models learn from past data only' },
      { cls: 'dev', name: 'Development', tipk: 'development', when: `${monthLabel(w.development[0])} – ${monthLabel(w.development[1])}`, what: 'Shown on this dashboard' },
      { cls: 'test', name: 'Historical test', tipk: 'test', when: `${monthLabel(w.historical_test[0])} – ${monthLabel(w.historical_test[1])}`, what: 'Sealed until the freeze' },
      { cls: 'pro', name: 'Live tracking', tipk: 'prospective', when: 'After the freeze', what: 'Not started' },
    ];
    const STATE = { scored: 'Scored on this dashboard', learn: 'Model learns from these months', history: 'Saved decisions; longer history shown as context',
      sealed: 'Saved decisions, sealed and not scored', later: 'Runs once frozen', none: 'Not yet run' };
    const rows = [
      ['det', 'Deterministic', ['learn', 'scored', 'later', 'none']],
      ['com', 'Agent Committee', ['history', 'scored', 'sealed', 'none']],
      ['jev', 'JEV', ['history', 'scored', 'sealed', 'none']],
      ['rag', 'Causal RAG', ['none', 'none', 'none', 'none']],
    ];
    const bar = (c, st) => `<span class="bar ${st}" style="--c:${c}" title="${esc(STATE[st])}"></span>`;
    const legend = [['scored', 'Scored on this dashboard'], ['learn', 'Used for learning, or saved decisions shown as longer history'], ['sealed', 'Saved decisions, sealed and not scored'], ['none', 'Not yet run']];
    app.innerHTML = `<div class="wrap">
      <section><h1>Timeline</h1><p class="lede">Approaches are built on training and development months, then frozen. Only then is the held-back test scored, once, followed by live tracking.</p></section>
      <section class="panel tlpanel">
        <div class="tlgrid" role="table" aria-label="Which months each approach has run">
          <div role="row" class="tlhead"><span role="columnheader"></span>${phases.map(p => `<div role="columnheader" class="tlseg ${p.cls}"><b>${p.name} ${p.tipk ? tip(p.tipk) : ''}</b><small>${p.when}</small><small>${p.what}</small></div>`).join('')}</div>
          ${rows.map(([k, label, st]) => `<div role="row" class="tlrow"><span role="rowheader">${swatch(k)} ${label}</span>${st.map((x, i) => `<span role="cell" aria-label="${esc(phases[i].name)}: ${esc(STATE[x])}">${bar(color(k), x)}</span>`).join('')}</div>`).join('')}
        </div>
        <div class="tlv">${phases.map((p, i) => `<div class="tlseg ${p.cls}"><b>${p.name} ${p.tipk ? tip(p.tipk) : ''}</b><small>${p.when} · ${p.what}</small>
          <ul>${rows.map(([k, label, st]) => `<li>${bar(color(k), st[i])}<span>${label}: ${esc(STATE[st[i]])}</span></li>`).join('')}</ul></div>`).join('')}</div>
        <div class="tllegend">${legend.map(([st, t]) => `<span>${bar(css('--text-2'), st)}${t}</span>`).join('')}</div>
        <p class="sub" style="margin:0">Causal RAG will run every month from 2015 once its model is approved. The Deterministic model's historical-test decisions are generated only after the freeze.</p>
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
    app.innerHTML = `<div class="wrap">
      <section><h1>How it's scored</h1><p class="lede">Shared rules decide how results are measured. Everything that forms views or sets weights stays each approach's own.</p></section>
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
        <li>Two approaches hold stocks with 20+ year Treasuries; the other two hold stocks, 7–10 year Treasuries and corporate bonds.</li>
        <li>Horizons differ: two use 12-month views, two use 1-month forecasts.</li>
        <li>Each reads different information, from data surprises alone to research papers and documents.</li>
        <li>Comparing each approach with its own benchmark helps, but it does not remove these differences.</li></ul></div></details>
      <details class="more"><summary>Keeping the test honest</summary><div><ul class="list">
        <li>The historical test (2023–2026) stays sealed until every check passes and the team approves; the scoring software refuses to open it otherwise.</li>
        <li>Every input is used only after its publication time.</li>
        <li>Saved AI outputs are replayed exactly as recorded; nothing missing is filled in or invented.</li>
        <li>Demo screens are labelled and can never enter results.</li>
        <li>AI models may have seen past market history during training. This is disclosed; only live months are free of it.</li></ul></div></details>
      <details class="more"><summary>Statistics</summary><div><ul class="list">
        <li>Differences are measured on the same months for both approaches being compared.</li>
        <li>Uncertainty comes from resampling 6-month blocks of returns 5,000 ${tipw('times', 'ci')}</li>
        <li>When several comparisons are made, significance is corrected for ${tipw('that', 'significance')}</li>
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
    const view = key ? 'approaches' : (['overview', 'approaches', 'timeline', 'method'].includes(h) ? h : 'overview');
    document.querySelectorAll('nav a').forEach(a => { if (a.dataset.route === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    try {
      if (key) viewApproach(key);
      else if (view === 'approaches') viewApproaches();
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
      document.getElementById('foot-right').textContent = `Results built ${j.generated_at_utc.slice(0, 10)} · development phase`;
      route();
    })
    .catch(e => { app.innerHTML = `<div class="wrap"><p class="err">Results could not be loaded: ${esc(e.message)}. Start the dashboard with the local server described in the README.</p></div>`; });
})();
