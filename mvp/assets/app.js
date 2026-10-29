/* Protofin Backtest dashboard. Reads data/dashboard.json (built by mvp/build_dashboard_data.py).
   Sections: Overview (the story), Approaches (one tab per primary approach), Experiments (within-approach
   tests, grouped by approach), Methodology (timeline, frozen settings, validation status).
   Three primary approaches: Deterministic Quantitative Model, Agentic Workflow (represented by JEV),
   Agentic Causal RAG. The Agent Committee is a within-approach variant shown under Experiments.
   Presentation only: every number comes from dashboard.json unchanged. */
(function () {
  'use strict';

  // Short, plain-English definitions shown in tooltips.
  const GLOSSARY = {
    cer: 'Net CER = Certainty-Equivalent Return: the guaranteed yearly return above cash a cautious investor would accept instead of the strategy, after costs. Higher is better. It is not a compound annual return.',
    sharpe: 'Sharpe ratio: return above cash per unit of risk. Higher is better.',
    drawdown: 'Worst fall (maximum drawdown): the largest drop from a peak to a later low. Closer to zero is better.',
    excess: 'Return above cash: yearly return after trading costs, minus what Treasury bills paid.',
    volatility: 'Volatility: how much returns swing in a year. Lower is smoother.',
    turnover: 'Turnover: share of the portfolio traded in a year. More trading costs more.',
    growth: 'What $1 invested at the start would be worth each month, after trading costs.',
    gap: 'How far ahead (or behind) $1 in the approach is compared with $1 in the common benchmark.',
    commonbench: 'Common benchmark: one reference portfolio for all three approaches, 60% US equities (SPY) and 40% intermediate-term Treasuries (IEF), rebalanced monthly on the same dates, costs and accounting. A reference point, not a neutral or broad-market benchmark.',
    benchmark: "Own benchmark: each approach's own fixed starting mix, rebalanced monthly. Beating it means the approach's decisions added value. It differs by approach, so it is not used to compare approaches.",
    attribution: "The gap to the common benchmark splits exactly into two parts: the approach's decisions (versus its own starting mix) and the benchmark mix (its own starting mix versus the common benchmark), which comes from the assets it may hold, not from its decisions.",
    cumulative: 'Cumulative return: total growth over the period after trading costs, including dividends. Not adjusted for risk.',
    vscommon: 'Net CER of the approach minus net CER of the common benchmark, in percentage points per year.',
    freeze: 'Awaiting freeze approval: specified and checked. It becomes fixed only when the project lead approves it, before the historical test opens, and cannot change afterwards.',
    significance: 'Statistically clear: too large to be explained by chance (5% level), after adjusting for running three comparisons.',
    ci: 'Likely range (95%): where the true difference most likely lies. If it spans zero, the gap could be chance.',
    bl: 'Black–Litterman: starts from a neutral mix and tilts toward the forecasts, more when they are confident.',
    walkforward: 'Walk-forward: each month, models are rebuilt from past data only and judged on the month that follows.',
    causalrag: 'Causal RAG: AI retrieval guided by a map of cause-and-effect findings from economics research, not just keyword similarity.',
    training: 'Training: from February 2015 the models learn from data; nothing is scored yet.',
    development: 'Development: months used to build and check the approaches. Good for spotting problems, not for picking a winner.',
    test: 'Historical test: months held back and scored once, after the freeze. Still sealed, so no results exist.',
    live: 'Live: months after the freeze. The cleanest evidence, since nobody could have seen them in advance.',
    overlap: "2023 overlaps the AI models' training data, so those months carry a contamination caution.",
    reproduction: "Reproduction check: re-running each approach's own code to confirm it gives exactly its authors' saved results.",
    common: 'Shared rules: scoring every approach with the same trade timing, costs and cash rate.',
    mock: 'Demo: canned responses that show how the screens work. Never a result.',
    ridge: 'Ridge regression: a linear model that shrinks weak signals toward zero to avoid overfitting.',
    jev: 'JEV: an AI decision model, asked each month whether stocks will beat bonds over the next 12 months. Its saved answers are replayed exactly.',
    confidence: 'How sure the approach said it was. More confidence moves the portfolio further from its starting mix.',
    regime: 'In months of very high policy or geopolitical uncertainty, the Committee lowers its confidence one level.',
    inventory: 'Research inventory: how much published research the approach can draw on. An input, not a result.',
    signals: 'Predicted directions (+1 up, −1 down) of hypotheses with each verdict, added up per asset.',
    variant: "Within-approach experiment: another version of the same approach, compared only with that approach's primary system.",
    awaiting: 'Awaiting validation: built and tested without an AI model. Results stay unavailable until model runs are approved and pass their checks.',
    frozen: 'Frozen: fixed before any protected month is scored; cannot change without a new version and a full rerun.',
    approval: 'Needs approval: implemented and used, but awaiting final team sign-off.',
    design: 'Differs by design: each approach keeps its own version of this.',
  };
  const ROUTES = { deterministic: 'det', jev: 'jev', 'causal-rag': 'rag', committee: 'com' };
  const SLUG = { det: 'deterministic', jev: 'jev', rag: 'causal-rag', com: 'committee' };
  const VAR = { det: '--c-det', com: '--c-com', jev: '--c-jev', rag: '--c-rag' };
  const NUMBER = { det: 1, jev: 2, rag: 3 };
  const ASSET_VAR = { SPY: '--a-eq', IEF: '--a-gov', TLT: '--a-gov', LQD: '--a-credit' };
  const ASSET_DASH = { SPY: [], IEF: [6, 4], TLT: [6, 4], LQD: [2, 3] };
  const PLAIN = { SPY: 'Stocks', IEF: 'Treasuries', TLT: 'Long Treasuries', LQD: 'Corporate bonds' };
  const COMMON_DASH = [7, 4], OWN_DASH = [2, 3];

  // Line icons (24 px grid, stroked with the current colour).
  const P = {
    data: '<ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
    store: '<circle cx="6" cy="7" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="12" cy="17" r="2.2"/><circle cx="19" cy="15" r="1.8"/><path d="M8 7.7l8-1.3M7.2 8.8l3.7 6.4M13.9 16.4l3.4-1"/>',
    agent: '<rect x="4" y="7" width="16" height="12" rx="4"/><path d="M12 7V4"/><circle cx="12" cy="3.2" r="1"/><circle cx="9" cy="13" r="1.3"/><circle cx="15" cy="13" r="1.3"/>',
    tool: '<circle cx="10.5" cy="10.5" r="5.5"/><path d="M15 15l5 5"/><path d="M8 10.5h5M10.5 8v5"/>',
    model: '<path d="M4 19l5-6 4 3 7-9"/><path d="M4 4v15h16"/>',
    output: '<path d="M4 12h12M12 6l6 6-6 6"/>',
    alloc: '<circle cx="12" cy="12" r="8"/><path d="M12 4v8l6 5"/>',
    calendar: '<rect x="4" y="5" width="16" height="15" rx="2.5"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    arrow: '<path d="M5 12h12M13 7l5 5-5 5"/>',
    cost: '<ellipse cx="12" cy="7" rx="6" ry="2.5"/><path d="M6 7v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V7M6 12v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-5"/>',
    cash: '<rect x="3" y="6" width="18" height="12" rx="2.5"/><circle cx="12" cy="12" r="2.6"/><path d="M6.5 9v6M17.5 9v6"/>',
    window: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M9 6v12M15 6v12"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".8"/>',
    chart: '<path d="M5 20V11M11 20V5M17 20v-7"/>',
    scale: '<path d="M12 4v16M7 20h10M5 8h14M5 8l-2.5 6a2.8 2.8 0 0 0 5 0zM19 8l-2.5 6a2.8 2.8 0 0 0 5 0z"/>',
    bench: '<path d="M4 17l5-5 4 3 7-7"/><path d="M4 12h16" stroke-dasharray="2 3"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
    refresh: '<path d="M19 12a7 7 0 1 1-2.1-5"/><path d="M19 4v5h-5"/>',
    assets: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    check: '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.5l2.6 2.5L16 9.5"/>',
    hourglass: '<path d="M7 4h10M7 20h10M8 4c0 4 8 4 8 8s-8 4-8 8M16 4c0 4-8 4-8 8s8 4 8 8"/>',
    planned: '<circle cx="12" cy="12" r="8" stroke-dasharray="3 3"/>',
    blocked: '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
    pause: '<circle cx="12" cy="12" r="8.5"/><path d="M10 9v6M14 9v6"/>',
    review: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
    chev: '<path d="M9 6l6 6-6 6"/>',
    flow: '<rect x="3" y="9" width="5" height="6" rx="1.5"/><rect x="16" y="9" width="5" height="6" rx="1.5"/><path d="M8 12h8M13 9l3 3-3 3"/>',
    layers: '<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4M4 16l8 4 8-4"/>',
    method: '<rect x="5" y="3.5" width="14" height="17" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
    dash: '<path d="M7 12h10"/>',
  };
  const icon = (k, cls) => `<svg class="i${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true">${P[k] || ''}</svg>`;

  const STATUS = {   // implementation status (experiments)
    tested: ['ok', 'check', 'Tested'], awaiting_validation: ['wait', 'hourglass', 'Awaiting validation'], planned: ['plan', 'planned', 'Planned'],
    blocked: ['block', 'blocked', 'Blocked'], paused: ['pause', 'pause', 'Paused'],
  };
  const GATE = {     // validation status (methodology)
    pass: ['pass', 'check', 'Passed'], review: ['review', 'review', 'Needs a decision'], pending: ['pending', 'planned', 'Pending'],
    blocked: ['blocked', 'blocked', 'Blocked'], na: ['na', 'dash', 'Does not apply'],
  };
  const ORDER = { pass: 0, review: 1, pending: 2, blocked: 3, na: 4 };
  const SETTING = { frozen: ['frozen', 'lock', 'Frozen'], approval: ['approval', 'review', 'Needs approval'], design: ['design', 'layers', 'Differs by design'] };

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
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthLabel = m => { const [y, mo] = m.split('-'); return `${MON[+mo - 1]} ${y}`; };
  const tipText = (text, label) => `<span class="tip"><button type="button" aria-label="${esc(label || 'What does this mean?')}">i</button><span role="tooltip">${esc(text)}</span></span>`;
  const tip = (key, label) => tipText(GLOSSARY[key], label);
  const tipw = (word, key) => `<span class="nw">${word}&nbsp;${tip(key)}</span>`;
  const all = () => D.systems.concat(D.variants);
  const sys = key => all().find(s => s.key === key);
  const color = key => css(VAR[key]) || '#888';
  const assetColor = a => css(ASSET_VAR[a]) || '#888';
  const badge = key => `<span class="badge" style="background:var(${VAR[key]})">${NUMBER[key] || ''}</span>`;
  const S = key => D.dev.series[key];
  const devSpan = () => `${monthLabel(D.windows.development[0])} – ${monthLabel(D.windows.development[1])}`;
  const devYears = () => `${D.windows.development[0].slice(0, 4)}–${D.windows.development[1].slice(2, 4)}`;
  const testYears = () => `${D.windows.historical_test[0].slice(0, 4)}–${D.windows.historical_test[1].slice(2, 4)}`;
  const killCharts = () => { charts.forEach(c => c.destroy()); charts = []; };
  const killChart = id => charts.filter(c => c.canvas.id === id).forEach(c => { c.destroy(); charts = charts.filter(x => x !== c); });
  const name = k => esc(sys(k).short);
  const SHORT = { det: 'Deterministic', jev: 'JEV', rag: 'Causal RAG', com: 'Committee' };
  const statusChip = st => { const [c, ic, l] = STATUS[st]; return `<span class="chip ${c}">${icon(ic)}${l}</span>`; };
  const statusLegend = (map, keys) => `<div class="ilegend" aria-label="Status key">${keys.map(k => { const [c, ic, l] = map[k]; return `<span class="${c === 'pass' ? 'ok' : c === 'review' ? 'wait' : c === 'pending' ? 'plan' : c === 'blocked' ? 'block' : c}">${icon(ic)}${l}</span>`; }).join('')}</div>`;
  const NS = '<span class="nsig">Not statistically clear</span>';
  const dataChip = kind => ({
    dev: `<span class="chip dev">${icon('chart')}Development ${devYears()} ${tip('development')}</span>`,
    sealed: `<span class="chip sealed">${icon('lock')}Historical test ${testYears()} · sealed ${tip('test')}</span>`,
    na: `<span class="chip na">${icon('dash')}Results unavailable ${tip('awaiting')}</span>`,
    demo: `<span class="chip demo">${icon('info')}Demo · not a result ${tip('mock')}</span>`,
    live: `<span class="chip plain">${icon('clock')}Live · after the freeze ${tip('live')}</span>`,
  }[kind]);

  function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.font.family = css('--font') || 'system-ui';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css('--muted');
    Chart.defaults.borderColor = css('--border');
    Chart.defaults.animation = false;
    Object.assign(Chart.defaults.plugins.tooltip, { backgroundColor: css('--surface-3'), titleColor: css('--text'), bodyColor: css('--text-2'),
      borderColor: css('--border-strong'), borderWidth: 1, padding: 10 });
    Chart.defaults.maintainAspectRatio = false;
  }
  function chart(canvas, cfg) {
    if (!canvas) return null;
    if (!window.Chart) { canvas.parentElement.innerHTML = '<p class="sub">Charts could not load.</p>'; return null; }
    const c = new Chart(canvas, cfg);
    charts.push(c);
    return c;
  }
  const xTicks = (months, n) => ({ ticks: { maxTicksLimit: n || (window.innerWidth < 560 ? 4 : 8), maxRotation: 0, autoSkip: true, callback: (v, i) => monthLabel(months[i]) }, grid: { display: false } });
  const bottomLegend = { position: 'bottom', labels: { boxWidth: 18, boxHeight: 2 } };
  const FMT_WEALTH = { y: v => '$' + v.toFixed(2), tip: v => '$' + v.toFixed(3) };
  const FMT_GAP = { y: v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(0) + '%', tip: v => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}% vs common benchmark` };
  const CB = () => D.dev.common_benchmark;
  const commonLine = label => ({ label: label || 'Common benchmark', data: CB().wealth, color: css('--c-common'), dash: COMMON_DASH });
  const freezeChip = () => `<span class="chip wait">${icon('hourglass')}${esc(CB().status_label)} ${tip('freeze')}</span>`;

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
  // A line chart plus its clickable legend; replaces any previous chart and legend with the same ids.
  function lineChart(canvasId, legendId, months, lines, fmt) {
    killChart(canvasId);
    const lg = document.getElementById(legendId);
    if (lg) lg.outerHTML = legendButtons(legendId, lines);
    const ch = chart(document.getElementById(canvasId), {
      type: 'line',
      data: { labels: months, datasets: lines.map(l => ({ label: l.label, data: l.data, borderColor: l.color, backgroundColor: l.color, order: l.dash ? 0 : 1,
        borderWidth: l.dash ? 2 : 2.5, borderDash: l.dash || [], pointRadius: 0, pointHoverRadius: 4, tension: 0.15 })) },
      options: { layout: { padding: { right: 8 } }, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]), label: it => ` ${it.dataset.label}: ${fmt.tip(it.parsed.y)}` } } },
        scales: { x: xTicks(months), y: { ticks: { callback: fmt.y }, grid: { color: css('--border') } } } } });
    if (ch) wireLegend(legendId, ch);
  }
  function weightsChart(canvas, months, weights, ticks) {
    const assets = Object.keys(weights);
    chart(canvas, { type: 'line',
      data: { labels: months, datasets: assets.map((a, i) => ({ label: PLAIN[a] || a, data: weights[a].map(v => v * 100), fill: i === 0 ? 'origin' : '-1',
        borderColor: css('--surface'), backgroundColor: assetColor(a), borderWidth: 1.5, pointRadius: 0, tension: 0.1 })) },
      options: { interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12 } },
          tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]), label: it => ` ${it.dataset.label}: ${(weights[assets[it.datasetIndex]][it.dataIndex] * 100).toFixed(0)}%` } } },
        scales: { x: xTicks(months, ticks), y: { stacked: true, min: 0, max: 100, ticks: { stepSize: 25, callback: v => v + '%' }, grid: { color: css('--border') } } } } });
  }

  // One shared symmetric axis for every interval bar, so bars compare across pages.
  function ciAxis() {
    const vals = Object.values(D.dev.series).flatMap(s => s.vs_neutral.ci95.concat(s.vs_common.ci95).map(Math.abs)).concat((D.dev.within_contrasts || []).flatMap(c => c.ci95.map(Math.abs)))
      .concat(D.dev.primary_contrasts.items.filter(c => c.computed).flatMap(c => c.ci95.map(Math.abs)));
    return Math.max(0.01, Math.ceil(Math.max(...vals) * 100) / 100);
  }
  function ciBar(c, key, leftLabel, rightLabel) {
    const A = ciAxis(), x = v => ((v + A) / (2 * A) * 100).toFixed(2) + '%';
    return `<div class="ci" role="img" aria-label="Difference ${pts(c.cer_difference)}, likely range ${pts(c.ci95[0])} to ${pts(c.ci95[1])}">
      <div class="cibar"><span class="zero" style="left:${x(0)}"></span>
        <span class="range" style="left:${x(c.ci95[0])};width:calc(${x(c.ci95[1])} - ${x(c.ci95[0])});background:${color(key)}"></span>
        <span class="pt" style="left:${x(c.cer_difference)};background:${color(key)}"></span></div>
      <div class="cilabels num"><span>${leftLabel || 'behind'}</span><span>0</span><span>${rightLabel || 'ahead'}</span></div></div>`;
  }
  const chance = c => c.ci95[0] <= 0 && c.ci95[1] >= 0;

  // ---------------------------------------------------------------- phase strip (overview and methodology)
  function phaseStrip(big) {
    const ph = D.methodology.phases;
    const span = p => p.from ? (Date.UTC(+p.to.slice(0, 4), +p.to.slice(5, 7)) - Date.UTC(+p.from.slice(0, 4), +p.from.slice(5, 7) - 1)) / 2.6e9 : 14;
    const lbl = p => p.from ? `${monthLabel(p.from)} – ${monthLabel(p.to)}` : 'Not started';
    const icons = { train: 'refresh', dev: 'chart', test: 'lock', live: 'clock' };
    const tipk = { train: 'training', dev: 'development', test: 'test', live: 'live' };
    const segs = ph.map(p => {
      const ov = p.overlap ? (() => { const w = (Date.UTC(+p.overlap.to.slice(0, 4), +p.overlap.to.slice(5, 7)) - Date.UTC(+p.overlap.from.slice(0, 4), +p.overlap.from.slice(5, 7) - 1)) / 2.6e9 / span(p) * 100;
        return `<span class="overlap" style="width:${w.toFixed(1)}%" title="${esc(p.overlap.label)}"></span>`; })() : '';
      const yrs = p.from ? `${p.from.slice(0, 4)}–${p.to.slice(2, 4)}` : '';
      const shortName = { train: 'Training', dev: 'Dev.', test: 'Test', live: 'Live' }[p.key];
      return `<div class="pseg ${p.key}" style="flex:${span(p).toFixed(1)} 1 0">${ov}<b>${icon(icons[p.key], p.key === 'test' ? 'keep' : '')}<span class="full">${esc(p.name)}</span><span class="short">${shortName}</span></b><small><span class="full">${lbl(p)}</span><span class="short">${yrs}</span></small></div>`;
    }).join('');
    const axis = big ? `<div class="paxis">${ph.map(p => `<span style="flex:${span(p).toFixed(1)} 1 0" title="${esc(GLOSSARY[tipk[p.key]])}">${esc(p.what)}</span>`).join('')}</div>` : '';
    const swatch = { train: 'var(--surface-3)', dev: 'var(--accent)', test: 'var(--warn)', live: 'var(--border-strong)' };
    const plist = big ? `<ul class="plist">${ph.map(p => `<li><i style="background:${swatch[p.key]}"></i><span><b>${esc(p.name)}</b> · ${esc(p.what)} ${tip(tipk[p.key])}</span><small>${p.from ? `${monthLabel(p.from)} – ${monthLabel(p.to)}` : ''}</small></li>`).join('')}</ul>` : '';
    return `<div class="phases" role="img" aria-label="Timeline: ${ph.map(p => `${p.name} ${lbl(p)}`).join('; ')}"><div class="pbar">${segs}</div>${axis}${plist}</div>`;
  }

  // ---------------------------------------------------------------- overview
  function miniFlow(key) {
    const f = D.flows[key];
    return `<div class="mini-flow" aria-label="${esc(f.map(n => n.label).join(' → '))}">${f.map((n, i) => `${i ? '<span class="ar"></span>' : ''}<span class="n ${n.kind === 'agent' ? 'agent' : ''}" title="${esc(n.label)}">${icon(n.kind)}</span>`).join('')}</div>`;
  }
  function approachCard(s) {
    const r = S(s.key);
    const ragGates = D.validation.gates.filter(g => g.cells.rag.status !== 'na');
    const passed = ragGates.filter(g => g.cells.rag.status === 'pass').length;
    const blocked = ragGates.filter(g => g.cells.rag.status === 'blocked').length;
    const segColor = st => st === 'pass' ? css('--pos') : st === 'blocked' ? css('--neg') : css('--surface-3');
    const body = r ? `
      <div class="big"><span class="v num">${pct(r.metrics.cer)}</span><span class="l">net CER per year ${tip('cer')}</span></div>
      <div class="vsrow"><span>vs common benchmark: <b class="num">${pts(r.vs_common.cer_difference)}</b>, likely range ${pts(r.vs_common.ci95[0])} to ${pts(r.vs_common.ci95[1])} ${tip('commonbench')}</span>
        ${ciBar(r.vs_common, s.key)}${r.vs_common.p >= 0.05 ? NS : ''}</div>`
      : `<div class="unavail"><span><b>Not run yet.</b> Its AI model runs await approval; until they pass validation there are no results.</span>
          <div class="prog" role="img" aria-label="${passed} of ${ragGates.length} validation checks passed, ${blocked} blocked">${ragGates.slice().sort((x, y) => ORDER[x.cells.rag.status] - ORDER[y.cells.rag.status]).map(g => `<i style="flex:1;background:${segColor(g.cells.rag.status)};margin-right:2px"></i>`).join('')}</div>
          <div class="ilegend"><span><i class="sw" style="background:${css('--pos')}"></i>${passed} passed</span><span><i class="sw" style="background:${css('--surface-3')}"></i>${ragGates.length - passed - blocked} to do</span><span><i class="sw" style="background:${css('--neg')}"></i>${blocked} blocked</span></div></div>`;
    return `<article class="acard" style="--c:var(${VAR[s.key]})">
      <div class="t">${badge(s.key)}<a href="#${SLUG[s.key]}">${esc(s.name)}</a></div>
      ${r ? '' : `<div class="chips"><span class="chip wait">${icon('hourglass')}Awaiting validation ${tip('awaiting')}</span></div>`}
      <p>${esc(s.summary || s.tagline)}</p>
      ${body}
      <span class="go">Details →</span>
    </article>`;
  }

  function triangle() {
    const pos = { det: [220, 22], jev: [40, 250], rag: [400, 250] };
    const items = D.dev.primary_contrasts.items;
    const edge = c => {
      // labels sit along each edge, away from the apex, so the two upper labels never overlap
      const [x1, y1] = pos[c.a], [x2, y2] = pos[c.b];
      const apex = c.a === 'det' ? [x1, y1] : c.b === 'det' ? [x2, y2] : null, other = apex ? (c.a === 'det' ? [x2, y2] : [x1, y1]) : null;
      const mx = apex ? apex[0] + 0.62 * (other[0] - apex[0]) : (x1 + x2) / 2, my = apex ? apex[1] + 0.62 * (other[1] - apex[1]) : (y1 + y2) / 2;
      const t1 = c.computed ? pts(c.cer_difference) : 'Pending';
      const t2 = c.computed ? (c.significant ? 'statistically clear' : 'not clear') : 'needs Causal RAG';
      const w = 132;
      return `<line class="edge ${c.computed ? 'done' : 'pending'}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>
        <g class="lbl" transform="translate(${mx},${my})"><rect x="${-w / 2}" y="-20" width="${w}" height="40" rx="9"/>
          <text text-anchor="middle" y="-3">${t1}</text><text class="s" text-anchor="middle" y="12">${t2}</text></g>`;
    };
    const node = k => { const [x, y] = pos[k]; const below = y > 100;
      return `<g class="node"><circle cx="${x}" cy="${y}" r="17" fill="var(${VAR[k]})"/><text x="${x}" y="${y + 4.5}" text-anchor="middle">${NUMBER[k]}</text>
        <text class="n" x="${x}" y="${below ? y + 36 : y - 26}" text-anchor="middle">${name(k)}</text></g>`; };
    const list = `<ul class="tri-list">${items.map(c => `<li class="${c.computed ? 'done' : 'pending'}"><span class="pair">${badge(c.a)}${badge(c.b)}</span>
      <span>${SHORT[c.a]} ${c.computed ? '−' : 'vs'} ${SHORT[c.b]}: <b>${c.computed ? pts(c.cer_difference) : 'pending'}</b></span><small>${c.computed ? `range ${pts(c.ci95[0])} to ${pts(c.ci95[1])} · ${c.significant ? 'statistically clear' : 'not statistically clear'}` : 'needs Causal RAG results'}</small></li>`).join('')}</ul>`;
    return list + `<svg class="tri" viewBox="-50 -30 540 330" role="img" aria-label="Primary comparison: ${items.map(c => c.computed ? `${sys(c.a).short} minus ${sys(c.b).short} ${pts(c.cer_difference)}, ${c.significant ? 'significant' : 'not significant'}` : `${sys(c.a).short} vs ${sys(c.b).short} pending`).join('; ')}">
        ${items.map(edge).join('')}${['det', 'jev', 'rag'].map(node).join('')}</svg>
      <div class="tri-legend"><span><i></i>Computed on development months</span><span><i class="p"></i>Pending</span></div>
      ${items.filter(c => c.computed).map(c => `<p class="sub"><b>${SHORT[c.a]} − ${SHORT[c.b]}</b>: ${pts(c.cer_difference)} net CER per year, likely range ${pts(c.ci95[0])} to ${pts(c.ci95[1])}: ${c.significant ? 'statistically clear' : 'not statistically clear'}.</p>`).join('')}
      <p class="sub">The comparisons with Causal RAG are pending. All three are judged together ${tip('significance')}</p>`;
  }

  // Same metrics for every approach; with bench=true a final column for the common benchmark itself.
  function compareTable(keys, bench) {
    const rows = [['cer', 'Net CER', m => pct(m.cer), true], ['sharpe', 'Sharpe ratio', m => num(m.sharpe)], ['drawdown', 'Worst fall', m => pct(m.max_drawdown)],
      ['cumulative', 'Cumulative return', m => pct(m.cumulative_return)], ['volatility', 'Volatility', m => pct(m.volatility)], ['turnover', 'Turnover', m => pct(m.turnover, 0)],
      ['vscommon', 'Net CER vs common benchmark', null]];
    const cell = (x, f, pr, k) => { const r = S(x); if (!r) return pr ? 'not run' : '—'; return f ? f(r.metrics) : pts(r.vs_common.cer_difference); };
    const col = k => k === 'rag' ? ' class="rag-col"' : '';
    const head = k => `<th${col(k)}><span class="nw"><span class="badge" style="background:var(${VAR[k]});width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:5px"></span>${SHORT[k]}</span></th>`;
    const label = (l, k) => { const w = l.split(' '); return `${w.slice(0, -1).join(' ')} ${tipw(w.at(-1), k)}`; };
    return `<div class="cmpwrap"><table class="cmp"><thead><tr><th>Development ${devYears()}</th>${keys.map(head).join('')}${bench ? `<th class="cb"><span class="ln-cb" aria-hidden="true"></span>Common<span class="ph-hide"> benchmark</span></th>` : ''}</tr></thead>
      <tbody>${rows.map(([k, l, f, pr]) => `<tr${pr ? ' class="primary"' : ''}${f ? '' : ' class="rel"'}><td>${label(l, k)}</td>${keys.map(x => `<td class="num${x === 'rag' ? ' rag-col' : ''}">${cell(x, f, pr, k)}</td>`).join('')}${bench ? `<td class="num cb">${f ? f(CB().metrics) : 'reference'}</td>` : ''}</tr>`).join('')}</tbody></table></div>
      ${keys.includes('rag') ? '<p class="sub ph-only">Causal RAG has no results yet, so it is left out of this table on small screens.</p>' : ''}`;
  }

  function viewOverview() {
    const months = D.dev.months;
    const res = D.systems.filter(s => S(s.key));
    const cbw = CB().wealth;
    // One common reference line for every approach; each approach's own benchmark is in its details.
    const growthLines = mode => mode === 'gap'
      ? res.map(s => ({ label: s.short, data: S(s.key).wealth.map((w, i) => (w / cbw[i] - 1) * 100), color: color(s.key) }))
          .concat([{ label: 'Common benchmark', data: months.map(() => 0), color: css('--c-common'), dash: COMMON_DASH }])
      : res.map(s => ({ label: s.short, data: S(s.key).wealth, color: color(s.key) })).concat([commonLine()]);
    app.innerHTML = `<div class="wrap">
      <section>
        <h1>Three ways to build a portfolio, scored by the same rules</h1>
        <p class="lede">Same months, trading costs and cash rate for every approach. Each keeps its own design.</p>
        <div class="verdict"><span class="ic">${icon('scale')}</span><div><b>No clear winner yet</b><span>Results below are development diagnostics (${devSpan()}): no difference is statistically clear. The historical test is sealed and Causal RAG has not run.</span></div></div>
        ${phaseStrip(false)}
      </section>
      <section aria-label="The three primary approaches"><div class="grid3">${D.systems.map(approachCard).join('')}</div></section>
      <section class="grid2">
        <div class="panel"><div class="phead"><h2>What the primary backtest compares</h2></div><p class="sub">Each approach against each other, on the same months.</p>${triangle()}</div>
        <div class="panel"><div class="phead"><h2>Findings so far</h2><span class="chip plain">${esc(D.notes.finding)}</span></div>
          <h3>What we know</h3><ul class="facts ok">${D.notes.know.map(t => `<li>${icon('check')}<span>${esc(t)}</span></li>`).join('')}</ul>
          <h3>Not yet known</h3><ul class="facts wait">${D.notes.not_yet.map(t => `<li>${icon('hourglass')}<span>${esc(t)}</span></li>`).join('')}</ul></div>
      </section>
      <section class="panel">
        <div class="phead"><h2 id="g-title"><span>Growth of $1, after costs</span> ${tip('growth')}</h2>
          <div class="seg" role="group" aria-label="Chart view"><button type="button" data-g="abs" aria-pressed="true">Growth of $1</button><button type="button" data-g="gap" aria-pressed="false">Versus common benchmark</button></div></div>
        <div class="legend" id="lg-growth"></div>
        <div class="chartbox"><canvas id="c-growth" aria-label="Growth of one dollar for each approach with results and the common benchmark"></canvas></div>
        <div class="cbnote"><span class="ln-cb" aria-hidden="true"></span><span><b>Common benchmark</b> · ${esc(CB().label)}, rebalanced monthly under the same rules ${tip('commonbench')}</span>${freezeChip()}</div>
        <p class="sub">The gaps are within what chance could produce. Causal RAG has no line: it has not run. Each approach's own benchmark is in its details ${tip('benchmark')}</p>
      </section>
      <section class="panel">
        <div class="phead"><h2>Key metrics</h2></div>
        ${compareTable(['det', 'jev', 'rag'], true)}
        <p class="sub">Net CER is the primary metric; the others describe risk and trading. Values differ, but no difference is statistically clear.</p>
      </section>
      <section aria-label="Explore"><div class="explore">
        <a href="#approaches"><span class="ic">${icon('flow')}</span><span><b>How each approach works</b><span>Workflows, forecasts and holdings</span></span></a>
        <a href="#experiments"><span class="ic">${icon('layers')}</span><span><b>Within-approach experiments</b><span>Committee vs JEV and other secondary tests</span></span></a>
        <a href="#methodology"><span class="ic">${icon('method')}</span><span><b>Methodology and validation</b><span>Frozen rules, timeline, what is still pending</span></span></a>
      </div></section>
    </div>`;
    const drawGrowth = mode => {
      lineChart('c-growth', 'lg-growth', months, growthLines(mode), mode === 'gap' ? FMT_GAP : FMT_WEALTH);
      document.querySelector('#g-title > span').textContent = mode === 'gap' ? 'Ahead of or behind the common benchmark' : 'Growth of $1, after costs';
      document.querySelector('#g-title .tip span[role=tooltip]').textContent = GLOSSARY[mode === 'gap' ? 'gap' : 'growth'];
    };
    drawGrowth('abs');
    document.querySelectorAll('[data-g]').forEach(b => b.addEventListener('click', () => {
      document.querySelectorAll('[data-g]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); drawGrowth(b.dataset.g); }));
  }

  // ---------------------------------------------------------------- flow diagram (approach pages)
  const KIND = { data: 'Input data', store: 'Knowledge base', agent: 'AI agent', tool: 'Tool', model: 'Model', output: 'Forecast', alloc: 'Allocation' };
  function flowDiagram(key) {
    const f = D.flows[key];
    const kinds = [...new Set(f.map(n => n.kind))];
    const legend = [['data', '', 'Data'], ['store', 'store', 'Knowledge base'], ['agent', 'agent', 'AI agent'], ['tool', 'tool', 'Tool'], ['model', '', 'Model'], ['alloc', 'out', 'Forecast or allocation']]
      .filter(([k]) => kinds.includes(k) || (k === 'alloc' && kinds.includes('output')));
    return `<div class="flowd" style="--c:var(${VAR[key]})">
      <div class="fnodes" role="group" aria-label="How information becomes a portfolio">${f.map((n, i) => `${i ? `<span class="farrow" aria-hidden="true">${icon('arrow')}</span>` : ''}
        <button type="button" class="fnode ${n.kind}" data-i="${i}" aria-pressed="${i === 0}" aria-controls="fd-${key}"><span class="ic">${icon(n.kind)}</span><span class="k">${KIND[n.kind]}</span><span class="lb">${esc(n.label)}</span></button>`).join('')}</div>
      <div class="fdetail" id="fd-${key}" aria-live="polite"><b>${esc(f[0].label)}.</b> ${esc(f[0].text)}</div>
      <div class="fkinds">${legend.map(([, c, l]) => `<span><i class="${c}"></i>${l}</span>`).join('')}<span>Select a step for a short explanation</span></div></div>`;
  }
  function wireFlow(key) {
    const f = D.flows[key], box = document.getElementById(`fd-${key}`);
    const show = b => { document.querySelectorAll('.fnode').forEach(x => x.setAttribute('aria-pressed', String(x === b))); const n = f[+b.dataset.i];
      box.innerHTML = `<b>${esc(n.label)}.</b> ${esc(n.text)}`; };
    document.querySelectorAll('.fnode').forEach(b => { b.addEventListener('click', () => show(b)); b.addEventListener('mouseenter', () => show(b)); b.addEventListener('focus', () => show(b)); });
  }

  function approachTabs(current) {
    return `<div class="atabs" role="navigation" aria-label="Approaches">${D.systems.map(s => `<a href="#${SLUG[s.key]}" style="--c:var(${VAR[s.key]})"${s.key === current ? ' aria-current="page"' : ''}>${badge(s.key)}<span class="t">${esc(s.short)}</span></a>`).join('')}</div>`;
  }

  // ---------------------------------------------------------------- one approach (or the Committee variant)
  function signalsBlock(s, r) {
    const months = D.dev.months, fc = r.forecasts;
    const yPct = d => ({ ticks: { callback: v => v.toFixed(d) + '%' }, grid: { color: css('--border') } });
    if (s.key === 'det') {
      return { html: `<h3>Monthly return forecasts ${tip('ridge')}</h3><p class="sub">Expected return above cash for the coming month.</p><div class="chartbox sm"><canvas id="c-sig" aria-label="Monthly return forecasts by asset"></canvas></div>`,
        draw: () => chart(document.getElementById('c-sig'), { type: 'line', data: { labels: months, datasets: s.universe.map(a => ({ label: PLAIN[a], data: fc.map(f => f[a] * 100),
          borderColor: assetColor(a), borderDash: ASSET_DASH[a], borderWidth: 2, pointRadius: 0 })) },
          options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: bottomLegend, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]), label: it => ` ${it.dataset.label}: ${it.parsed.y.toFixed(2)}%` } } },
            scales: { x: xTicks(months), y: yPct(1) } } }) };
    }
    if (s.key === 'com') {
      return { html: `<h3>The CIO's 12-month views ${tip('confidence')}</h3><p class="sub">Expected total return over 12 months. Amber dots: confidence lowered by high uncertainty ${tip('regime')}</p><div class="chartbox sm"><canvas id="c-sig" aria-label="Committee 12-month views"></canvas></div>`,
        draw: () => chart(document.getElementById('c-sig'), { type: 'line', data: { labels: months, datasets: [
          { label: 'Stocks', data: fc.map(f => f.SPY), borderColor: assetColor('SPY'), borderWidth: 2, pointRadius: fc.map(f => f.confidence === 'Low' ? 3.5 : 0), pointBackgroundColor: css('--warn'), pointBorderColor: css('--warn') },
          { label: 'Long Treasuries', data: fc.map(f => f.TLT), borderColor: assetColor('TLT'), borderDash: ASSET_DASH.TLT, borderWidth: 2, pointRadius: 0 }] },
          options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: bottomLegend, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]),
            label: it => ` ${it.dataset.label}: ${it.parsed.y.toFixed(1)}%`, afterBody: it => `Confidence used: ${fc[it[0].dataIndex].confidence}` } } },
            scales: { x: xTicks(months), y: yPct(0) } } }) };
    }
    if (s.key === 'jev') {
      return { html: `<h3>JEV's answer each month ${tip('jev')}</h3><p class="sub">Chance stocks beat bonds over 12 months, and JEV's confidence.</p><div class="chartbox sm"><canvas id="c-sig" aria-label="JEV probability and confidence"></canvas></div>`,
        draw: () => chart(document.getElementById('c-sig'), { type: 'line', data: { labels: months, datasets: [
          { label: 'Chance stocks beat bonds', data: fc.map(f => f.p * 100), borderColor: color('jev'), borderWidth: 2, pointRadius: 0 },
          { label: 'Confidence', data: fc.map(f => f.confidence * 100), borderColor: css('--c-bench'), borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0 }] },
          options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: bottomLegend, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]),
            label: it => ` ${it.dataset.label}: ${it.parsed.y.toFixed(0)}%`, afterBody: it => `Answer: ${String(fc[it[0].dataIndex].tilt || '').replace(/_/g, ' ')}` } } },
            scales: { x: xTicks(months), y: { min: 0, max: 100, ticks: { callback: v => v + '%' }, grid: { color: css('--border') } } } } }) };
    }
    return { html: '', draw: () => {} };
  }

  function limitations(key) {
    const common = 'Development months were used to build and check the approaches: diagnostics, not historical-test results.';
    if (key === 'det') return [common, 'Uses economic-data surprises only; no prices, news or research.', 'Learns from 2015 onward, a short history.'];
    if (key === 'com') return [common, 'GPT-4o was trained on data to October 2023, so it may know how 2019–2022 turned out.',
      'Its inputs name the assets and show the cash-yield level, which can hint at the period.', "Uncertainty indexes are today's revised values."];
    if (key === 'jev') return [common, "JEV's model version, prompt and raw replies were not saved: answers can be replayed, not re-created, and it cannot run live.",
      'Its tilt sizes were set by hand.', 'Its inputs name the assets and show the cash-yield level, which can hint at the period.',
      'Chosen to represent the Agentic Workflow after full-range results existed; this possible selection bias is disclosed.'];
    return [common];
  }

  // Exact split of the gap to the common benchmark: decisions (vs own benchmark) + benchmark mix (own vs common).
  function attributionBars(a, key) {
    const A = Math.max(0.005, Math.abs(a.total), Math.abs(a.decisions), Math.abs(a.mix)) * 1.1;
    const bar = (v, c) => { const w = Math.abs(v) / A * 50; return `<span class="ab" style="left:${(v < 0 ? 50 - w : 50).toFixed(2)}%;width:${w.toFixed(2)}%;background:${c}"></span>`; };
    const row = (l, sub, v, c, cls) => `<div class="arow${cls ? ' ' + cls : ''}"><span class="al">${l}<small>${sub}</small></span><span class="atrack"><span class="zero"></span>${bar(v, c)}</span><b class="num">${pts(v, 2)}</b></div>`;
    return `<div class="attr" role="img" aria-label="Gap to the common benchmark ${pts(a.total, 2)}: decisions ${pts(a.decisions, 2)}, benchmark mix ${pts(a.mix, 2)}">
      ${row('Decisions', 'vs its own starting mix', a.decisions, color(key))}
      ${row('Benchmark mix', 'own starting mix vs common', a.mix, css('--c-bench'))}
      ${row('Total', 'vs common benchmark', a.total, css('--c-common'), 'tot')}</div>`;
  }

  function viewApproach(key) {
    const s = sys(key);
    if (key === 'rag') return viewCausalRag(s);
    const variant = s.role === 'variant';
    const r = S(key), months = D.dev.months, bench = D.dev.benchmarks[r.neutral], vs = r.vs_neutral, vc = r.vs_common;
    const sig = signalsBlock(s, r), rep = D.reproduction[key], steps = D.native_vs_common[key], ex = r.example;
    const repLabel = { reproduced: 'matched saved results', replayed: 'matched saved results (replay only)' }[rep.status] || 'did not match';
    app.innerHTML = `<div class="wrap" style="--c:var(${VAR[key]})">
      ${variant ? `<a class="back" href="#experiments">← Experiments</a>` : approachTabs(key)}
      <section class="ahead">
        <div class="row">${variant ? `<span class="chip pause" style="color:var(--c-com)">${icon('layers')}Within-approach variant of the Agentic Workflow ${tip('variant')}</span>` : ''}${dataChip('dev')}</div>
        <h1>${esc(s.name)}</h1>
        <p class="lede">${esc(s.tagline)}</p>
        <div class="chips"><span class="chip plain">${icon('assets')}${esc(s.assets_label)}</span><span class="chip plain">${icon('calendar')}${esc(s.horizon)}</span><span class="chip plain">${icon('model')}${esc(s.model)}</span></div>
        ${key === 'jev' ? `<p class="sub">JEV represents the Agentic Workflow in the primary comparison. The <a href="#committee">Agent Committee</a> version is compared with it under <a href="#experiments">Experiments</a>.</p>` : ''}
      </section>
      <section class="panel"><h2>How it works</h2>${flowDiagram(key)}</section>
      <section class="grid2">
        <div class="panel"><div class="phead"><h2>Results</h2></div>
          <div class="kpis">
            <div class="kpi primary"><div class="v num">${pct(r.metrics.cer)}</div><div class="l">Net CER ${tip('cer')}</div></div>
            <div class="kpi"><div class="v num">${num(r.metrics.sharpe)}</div><div class="l">Sharpe ${tip('sharpe')}</div></div>
            <div class="kpi"><div class="v num">${pct(r.metrics.max_drawdown)}</div><div class="l">Worst fall ${tip('drawdown')}</div></div>
            <div class="kpi"><div class="v num">${pct(r.metrics.volatility)}</div><div class="l">Volatility ${tip('volatility')}</div></div>
            <div class="kpi"><div class="v num">${pct(r.metrics.turnover, 0)}</div><div class="l">Turnover ${tip('turnover')}</div></div>
            <div class="kpi"><div class="v num">${pct(r.metrics.cumulative_return)}</div><div class="l">Cumulative ${tip('cumulative')}</div></div>
          </div>
          <h3>Versus the common benchmark ${tip('commonbench')}</h3>
          <p class="sub"><b class="num">${pts(vc.cer_difference)}</b> net CER per year against ${esc(CB().label)}; likely range ${pts(vc.ci95[0])} to ${tipw(pts(vc.ci95[1]), 'ci')}</p>
          ${ciBar(vc, key)}${vc.p >= 0.05 ? NS : ''}
          <p class="sub">Cumulative return ${pts(vc.cumulative_difference)} versus the common benchmark. Historical test ${testYears()}: sealed ${tip('test')}</p>
        </div>
        <div class="panel"><h2>Growth of $1 ${tip('growth')}</h2><div class="legend" id="lg-one"></div><div class="chartbox sm"><canvas id="c-one" aria-label="Growth of one dollar, with the common benchmark and the approach's own benchmark"></canvas></div></div>
      </section>
      <section class="grid2">
        <div class="panel"><div class="phead"><h2>Where the gap comes from ${tip('attribution')}</h2></div>
          ${attributionBars(r.attribution, key)}
          <p class="sub">${Math.abs(r.attribution.mix) > Math.abs(r.attribution.decisions) ? 'Most of the gap comes from the assets this approach may hold, not from its decisions.' : 'Most of the gap comes from the approach\'s decisions.'} Parts may not add up exactly because of rounding.</p></div>
        <div class="panel"><div class="phead"><h2>Versus its own benchmark ${tip('benchmark')}</h2><span class="chip plain">Secondary check</span></div>
          <p class="sub"><b class="num">${pts(vs.cer_difference)}</b> net CER per year against ${esc(bench.label)}; likely range ${pts(vs.ci95[0])} to ${pts(vs.ci95[1])}</p>
          ${ciBar(vs, key)}${vs.p >= 0.05 ? NS : ''}
          <p class="sub">Shows whether its decisions beat its own starting mix. It differs by approach, so it is not used to compare approaches.</p></div>
      </section>
      <section class="grid2">
        <div class="panel">${sig.html}</div>
        <div class="panel"><h3>Holdings over time</h3><p class="sub">Share of the portfolio in each asset.</p><div class="chartbox sm"><canvas id="c-w" aria-label="Portfolio weights over time"></canvas></div></div>
      </section>
      ${ex && ex.cio_rationale ? `<details class="more"><summary>Sample reasoning (${monthLabel(ex.month)})</summary><div>
        <div class="quote"><b>Economist</b>${esc(ex.economist?.text)}</div>
        <div class="quote"><b>Risk Manager</b>${esc(ex.risk_manager?.text)}</div>
        <div class="quote"><b>CIO decision</b>${esc(ex.cio_rationale)}</div></div></details>` : ''}
      <details class="more"><summary>Reproduction check: ${repLabel}</summary><div>
        <p style="margin:0">The approach's own code was re-run to confirm it reproduces its saved ${tipw('results', 'reproduction')}. This shows the decisions are faithful, not that they were good.</p>
        ${rep.checks.map(t => { const w = /re-run|not saved/i.test(t); return `<div class="check${w ? ' warn' : ''}"><i>${w ? '!' : '✓'}</i><span>${esc(t)}</span></div>`; }).join('')}
        ${steps ? `<h3>From its own scoring to the shared rules ${tip('common')}</h3><p class="sub" style="margin:0">Net CER after each adjustment (${devSpan()}). Decisions never change; only the scoring does.</p>
          <div class="chartbox sm"><canvas id="c-steps" aria-label="Net CER after each scoring adjustment"></canvas></div>` : '<p class="sub" style="margin:0">Already uses the shared trading and cost rules, so its own and shared results are identical.</p>'}
      </div></details>
      <details class="more"><summary>Limitations</summary><div><ul>${limitations(key).map(t => `<li>${esc(t)}</li>`).join('')}</ul></div></details>
    </div>`;
    wireFlow(key);
    lineChart('c-one', 'lg-one', months, [{ label: s.short, data: r.wealth, color: color(key) }, commonLine(),
      { label: `Own benchmark (${bench.label})`, data: bench.wealth, color: css('--c-bench'), dash: OWN_DASH }], FMT_WEALTH);
    sig.draw();
    weightsChart(document.getElementById('c-w'), months, r.weights);
    const drawSteps = () => { const c = document.getElementById('c-steps'); if (!steps || !c || c.dataset.drawn) return; c.dataset.drawn = '1';
      chart(c, { type: 'bar', data: { labels: steps.map(x => x.step), datasets: [{ data: steps.map(x => x.cer * 100), backgroundColor: steps.map((x, i) => i === steps.length - 1 ? color(key) : css('--c-bench')), borderRadius: 6 }] },
        options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` Net CER: ${it.parsed.y.toFixed(2)}% per year` } } },
          scales: { x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 0, callback: function (v) { const w = this.getLabelForValue(v).split(' '), h = Math.ceil(w.length / 2); return [w.slice(0, h).join(' '), w.slice(h).join(' ')]; } } },
            y: { ticks: { callback: v => v + '%' }, grid: { color: css('--border') } } } } }); };
    document.querySelectorAll('details.more').forEach(d => d.addEventListener('toggle', () => { if (d.open && d.querySelector('#c-steps')) drawSteps(); }));
  }

  // ---------------------------------------------------------------- Causal RAG
  function viewCausalRag(s) {
    const a = D.ap3, demo = a.demo, g = a.graph;
    const steps = D.validation.gates.filter(x => x.cells.rag.status !== 'na');
    app.innerHTML = `<div class="wrap" style="--c:var(--c-rag)">
      ${approachTabs('rag')}
      <section class="ahead">
        <div class="row"><span class="chip wait">${icon('hourglass')}Awaiting validation ${tip('awaiting')}</span>${dataChip('na')}</div>
        <h1>${esc(s.name)} ${tip('causalrag')}</h1>
        <p class="lede">${esc(s.tagline)}</p>
        <div class="chips"><span class="chip plain">${icon('assets')}${esc(s.assets_label)}</span><span class="chip plain">${icon('calendar')}${esc(s.horizon)}</span><span class="chip plain">${icon('model')}${esc(s.model)}</span></div>
      </section>
      <section class="panel"><h2>How it works</h2>${flowDiagram('rag')}</section>
      <section class="grid2">
        <div class="panel"><div class="phead"><h2>Validation progress</h2><span class="chip plain num">${steps.filter(x => x.cells.rag.status === 'pass').length} of ${steps.length} passed</span></div>
          <ol class="track-steps">${steps.map(x => { const c = x.cells.rag, [cls, ic, l] = GATE[c.status];
            return `<li class="${cls}"><span class="dot">${icon(ic)}</span><span>${esc(x.name)}${c.note ? `<small>${esc(c.note)}</small>` : ''}</span><span class="chip ${cls === 'pass' ? 'ok' : cls === 'blocked' ? 'block' : cls === 'review' ? 'wait' : 'plan'}">${l}</span></li>`; }).join('')}</ol>
          ${statusLegend(GATE, ['pass', 'pending', 'blocked'])}
          <p class="sub">No development or historical-test results exist, so none are shown.</p></div>
        <div class="panel"><div class="phead"><h2>Inputs: research the agents can draw on</h2><span class="chip na">${icon('dash')}No results yet ${tip('inventory')}</span></div>
          <h3>Papers available to each decision year</h3>
          <div class="chartbox sm"><canvas id="c-kg" aria-label="Research papers available each year"></canvas></div>
          <h3>Research pathways by economic channel, ${g.at(-1).decision_year}</h3>
          <div class="chartbox sm"><canvas id="c-ch" aria-label="Research pathways by channel"></canvas></div></div>
      </section>
      ${demo ? `<details class="more demo-panel"><summary>Demo: one month, step by step</summary><div>${demoBlock(demo)}</div></details>` : ''}
      <details class="more"><summary>Safeguards</summary><div><ul>
        <li>Each year's research graph contains only papers published before that year; claims mentioning later events are removed.</li>
        <li>Documents and market data are filtered to what was public before 8 p.m. New York time on decision day, including revised values.</li>
        <li>Quotes the Testing Agent cites must appear word for word in the documents it was given.</li>
        <li>Each hypothesis is tested three times independently; a split decision counts as Insufficient.</li>
        <li>“Supported” means consistent with the evidence available at the time, never proof of cause.</li>
        <li>The graph rebuilds identically from the same data: ${a.graph_rebuild_identical ? 'checked' : 'not yet checked'}.</li></ul></div></details>
    </div>`;
    wireFlow('rag');
    chart(document.getElementById('c-kg'), { type: 'bar', data: { labels: g.map(x => x.decision_year), datasets: [{ label: 'Papers', data: g.map(x => x.papers), backgroundColor: css('--border-strong'), borderRadius: 4 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.parsed.y.toLocaleString()} papers · ${g[it.dataIndex].claims.toLocaleString()} claims` } } },
        scales: { x: { grid: { display: false } }, y: { ticks: { callback: v => v === 0 ? '0' : (v / 1000) + 'k' }, grid: { color: css('--border') } } } } });
    const last = g.at(-1).pathways_by_channel;
    const names = { growth: 'Growth', inflation: 'Inflation', policy_rates: 'Policy & rates', risk_credit: 'Risk & credit', other: 'Other', direct: 'Direct' };
    const order = Object.keys(names).filter(k => k in last);
    chart(document.getElementById('c-ch'), { type: 'bar', data: { labels: order.map(k => names[k]), datasets: [{ data: order.map(k => last[k]), backgroundColor: css('--border-strong'), borderRadius: 4 }] },
      options: { indexAxis: 'y', plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.parsed.x} pathways` } } }, scales: { x: { grid: { color: css('--border') } }, y: { grid: { display: false } } } } });
  }

  function demoBlock(d) {
    const arrow = v => v > 0 ? '▲ up' : v < 0 ? '▼ down' : '— no view';
    const n = v => v > 0 ? `+${v}` : v < 0 ? `−${-v}` : '0';
    return `<div class="demo-banner"><b>Demo only.</b><span>Canned responses and synthetic documents that show how the screens work. Nothing here is a result. ${tip('mock')}</span></div>
      <div class="dflow">
        <div><b>1 · Event</b>${d.triggers.map(t => `${esc(t.event)}${t.surprise_z != null ? ` (surprise ${n(t.surprise_z)} std)` : ''}`).join('<br>')}</div>
        ${d.hypotheses.map(h => `
        <div><b>2 · Hypothesis</b>Channel: ${esc(h.channel)}<br>Stocks ${arrow(h.predicted.SPY)}, Treasuries ${arrow(h.predicted.IEF)}, corporate bonds ${arrow(h.predicted.LQD)}</div>
        <div><b>3 · Research</b>${h.research_records} papers behind ${h.graph_paths_cited} pathway${h.graph_paths_cited === 1 ? '' : 's'}</div>
        <div><b>4 · Testing</b>${h.testing_runs.map((r, i) => `<span>Run ${i + 1}: <span class="status ${r.status}">${r.status}</span></span>`).join('')}</div>
        <div><b>5 · Verdict</b><span class="status ${h.final_status}">${h.final_status}</span><span>${Math.round(h.run_agreement * 100)}% of runs agree</span></div>`).join('')}
        <div><b>6 · Signals ${tip('signals')}</b>${['SPY', 'IEF', 'LQD'].map(x => `<span><b>${PLAIN[x]}</b>: Supported ${n(d.signals[x].F_S)} · Contradicted ${n(d.signals[x].F_C)} · Insufficient ${n(d.signals[x].F_I)}</span>`).join('')}</div>
      </div>`;
  }

  // ---------------------------------------------------------------- experiments
  function viewExperiments() {
    const E = D.experiments, months = D.dev.months, w = E.within_contrast;
    const TITLES = { det: 'Deterministic Quantitative Model', jev: 'Agentic Workflow', rag: 'Agentic Causal RAG' };
    const branch = (v, gi, i) => `<div class="branch ${v.status}"><button type="button" aria-expanded="false" aria-controls="b-${gi}-${i}">
        <span class="nm">${esc(v.name)}</span>${statusChip(v.status)}${icon('chev', 'chev')}</button>
        <div class="bd" id="b-${gi}-${i}" hidden><span>${esc(v.detail)}</span>${v.link ? `<a class="go" href="#${SLUG[v.link]}">See its results →</a>` : ''}</div></div>`;
    const group = (g, gi) => `<section class="panel" style="--c:var(${VAR[g.approach]})">
        <div class="phead"><h2>${badge(g.approach)}${TITLES[g.approach]}</h2></div>
        <div class="tree">
          <div class="base"><b>${esc(g.base.name)}</b>${statusChip(g.base.status)}<span class="sub">${esc(g.base.detail)}</span>${g.blocked_by ? `<span class="sub">Waiting on: ${esc(g.blocked_by.join(', '))}</span>` : ''}${g.base.link ? `<a href="#${SLUG[g.base.link]}" class="more">${g.base.link === 'rag' ? 'How it works →' : 'See its results →'}</a>` : ''}</div>
          <div class="branches">${g.variants.map((v, i) => branch(v, gi, i)).join('')}</div>
        </div></section>`;
    const keys = ['com', 'jev'], bk = S('jev').neutral;
    app.innerHTML = `<div class="wrap">
      <section><h1>Within-approach experiments</h1>
        <p class="lede">Secondary tests inside each approach. None enters the primary comparison.</p>
        ${statusLegend(STATUS, Object.keys(STATUS))}</section>
      ${E.groups.map(group).join('')}
      <section class="panel" style="--c:var(--c-com)">
        <div class="phead"><h2>Agent Committee only vs JEV only</h2>${dataChip('dev')}</div>
        <p class="sub">Same assets, inputs and own 60/40 benchmark, so this isolates how the views are formed.</p>
        <div class="grid2">
          <div><div class="legend" id="lg-exp"></div><div class="chartbox sm"><canvas id="c-exp" aria-label="Growth of one dollar, Committee and JEV"></canvas></div></div>
          <div style="display:grid;gap:12px;align-content:start">${compareTable(keys)}
            <div class="vsrow"><span>${name(w.a)} − ${name(w.b)}: <b class="num">${pts(w.cer_difference)}</b> net CER per year, likely range ${pts(w.ci95[0])} to ${pts(w.ci95[1])} ${tip('ci')}</span>${ciBar(w, 'com', 'JEV ahead', 'Committee ahead')}${w.significant ? '' : NS}</div></div>
        </div>
        <p class="sub">A within-approach result. It does not change the primary comparison, where JEV represents the Agentic Workflow.</p>
      </section>
    </div>`;
    document.querySelectorAll('.branch > button').forEach(b => b.addEventListener('click', () => {
      const open = b.getAttribute('aria-expanded') === 'true'; b.setAttribute('aria-expanded', String(!open));
      document.getElementById(b.getAttribute('aria-controls')).hidden = open; }));
    lineChart('c-exp', 'lg-exp', months, keys.map(k => ({ label: sys(k).short, data: S(k).wealth, color: color(k) }))
      .concat([{ label: `Shared own benchmark (${D.dev.benchmarks[bk].label})`, data: D.dev.benchmarks[bk].wealth, color: css('--c-bench'), dash: OWN_DASH }]), FMT_WEALTH);
  }

  // ---------------------------------------------------------------- methodology
  function viewMethodology() {
    const M = D.methodology, V = D.validation;
    const COLS = { det: ['Deterministic', ''], jev: ['Agentic Workflow (JEV)', ''], rag: ['Causal RAG', ''], com: ['Agent Committee (variant)', ''] };
    const LETTER = { det: '1', jev: '2', rag: '3', com: 'C' };
    const cell = (g, k) => { const c = g.cells[k], [cls, ic, l] = GATE[c.status];
      return c.status === 'na' ? `<div class="cell na" aria-label="${esc(COLS[k][0])}: does not apply">–</div>`
        : `<div class="cell ${cls}"><span class="tip"><button type="button" aria-label="${esc(COLS[k][0])}: ${l}${c.note ? '. ' + esc(c.note) : ''}">${icon(ic)}</button><span role="tooltip">${esc(l)}${c.note ? ': ' + esc(c.note) : ''}</span></span></div>`; };
    const pc = D.dev.primary_contrasts.items;
    app.innerHTML = `<div class="wrap">
      <section><h1>Methodology</h1><p class="lede">What is fixed, what is still open, and how far each approach has been validated.</p></section>
      <section class="panel"><div class="phead"><h2>Timeline</h2>${dataChip('sealed')}</div>
        ${phaseStrip(true)}
        <div class="olegend"><i></i>2023 overlaps the AI models' training data ${tip('overlap')}</div>
        <div class="callout">${icon('review')}<div><b>Awaiting decision</b><ul>${M.pending.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div></div>
      </section>
      <section><div class="phead"><h2>Rules and settings</h2><div class="ilegend">${Object.keys(SETTING).map(k => `<span>${icon(SETTING[k][1])}${SETTING[k][2]} ${tip(k)}</span>`).join('')}</div></div>
        <div class="settings">${M.settings.map(x => { const [c, ic, l] = SETTING[x.status];
          return `<div class="setting"><span class="ic">${icon(x.icon)}</span><div><b>${esc(x.name)}${x.tip ? ' ' + tip(x.tip) : ''}</b><p>${esc(x.value)}</p><span class="chip ${c}">${icon(ic)}${l}</span></div></div>`; }).join('')}</div>
      </section>
      <section class="panel"><div class="phead"><h2>Common benchmark ${tip('commonbench')}</h2>${freezeChip()}</div>
        <div class="cbspec"><div class="cbmix" role="img" aria-label="${esc(CB().label)}">${Object.entries(CB().weights).map(([a, w]) => `<span style="flex:${w} 1 0;background:${assetColor(a)}"><b>${Math.round(w * 100)}%</b> ${a === 'SPY' ? 'US equities' : 'Intermediate-term Treasuries'}<small>${esc(CB().instruments[a].split('(')[0].trim())}</small></span>`).join('')}</div>
          <ul class="rules">${CB().rules.map(x => `<li>${icon('check')}<span><b>${esc(x.name)}</b>${esc(x.text)}</span></li>`).join('')}</ul></div>
        <p class="sub">${esc(CB().not_neutral)} ${esc(CB().data_checks)} It is a reference for all three approaches and never changes their decisions or the primary comparison.</p>
      </section>
      <section class="panel"><div class="phead"><h2>Validation status</h2><span class="chip block">${icon('lock')}Decision: ${V.decision === 'NO-GO' ? 'not yet approved to open the test' : esc(V.decision)}</span></div>
        <div class="matrix" role="table" aria-label="Validation checks by approach">
          <div class="mh" role="columnheader">Check</div>${V.columns.map(k => `<div class="mh" role="columnheader" aria-label="${esc(COLS[k][0])}"><span class="badge" style="background:var(${VAR[k]});width:20px;height:20px;font-size:11.5px;border-radius:6px">${LETTER[k]}</span><span class="full">${esc(COLS[k][0])}</span></div>`).join('')}
          ${V.gates.map(g => `<div class="gate" role="rowheader">${esc(g.name)}</div>${V.columns.map(k => cell(g, k)).join('')}`).join('')}
        </div>
        ${statusLegend(GATE, ['pass', 'review', 'pending', 'blocked'])}
        <div class="ilegend phone-key">${V.columns.map(k => `<span><span class="badge" style="background:var(${VAR[k]});width:18px;height:18px;font-size:11px;border-radius:5px">${LETTER[k]}</span>${esc(COLS[k][0])}</span>`).join('')}</div>
        <p class="sub">Select a symbol for its note.</p>
      </section>
      <details class="more"><summary>How net CER is calculated</summary><div>
        <p class="formula num">Net CER = 12 × ( average monthly net excess return − ½ × 2.5 × variance of monthly net excess return )</p>
        <p style="margin:0">The certainty-equivalent return: the guaranteed yearly return above cash that an investor with risk aversion 2.5 would accept instead of the strategy, after trading costs. It is not a compound annual return.</p></div></details>
      <details class="more"><summary>The primary comparison and its statistics</summary><div><ul>
        <li>Three approaches, compared in pairs: ${pc.map(c => `${name(c.a)} vs ${name(c.b)}`).join('; ')}.</li>
        <li>Differences are measured on the same months; uncertainty comes from resampling 6-month blocks 5,000 times.</li>
        <li>The three comparisons are corrected together (Holm). Within-approach experiments never enter this family.</li>
        <li>The common benchmark is a secondary reference: it never enters this family, and it leaves every difference between approaches unchanged.</li>
        <li>With few months, only large differences are detectable: “not significant” means not enough evidence, not “no difference”.</li></ul></div></details>
      <details class="more"><summary>Why this is not a controlled experiment</summary><div><ul>
        <li>The Agentic Workflow holds stocks and 20+ year Treasuries; the other two hold stocks, 7–10 year Treasuries and corporate bonds.</li>
        <li>Horizons differ: 12-month views versus 1-month forecasts.</li>
        <li>Each reads different information, from data surprises to research papers and documents.</li>
        <li>The common benchmark gives one reference line but does not remove these differences: part of each approach's gap to it comes from the assets it may hold.</li>
        <li>Comparing each approach with its own benchmark helps but does not remove these differences either.</li></ul></div></details>
      <details class="more"><summary>Keeping the test honest</summary><div><ul>
        <li>Every input is used only after it became public, including later revisions.</li>
        <li>Saved AI outputs are replayed exactly; nothing missing is filled in.</li>
        <li>The historical test opens once, only with a signed approval; the scoring software refuses it otherwise.</li>
        <li>Demo screens are labelled and can never enter results.</li>
        <li>AI models may have seen past market history in training; this is disclosed, and only live months are free of it.</li></ul></div></details>
    </div>`;
  }

  // ---------------------------------------------------------------- router
  function route() {
    if (!D) return;
    killCharts();
    chartDefaults();
    let h = (location.hash || '#overview').slice(1);
    if (h === 'method' || h === 'timeline') h = 'methodology';
    if (h === 'approaches') h = 'deterministic';
    const key = ROUTES[h];
    const view = key ? (key === 'com' ? 'experiments' : 'approaches') : (['overview', 'experiments', 'methodology'].includes(h) ? h : 'overview');
    document.querySelectorAll('header nav a').forEach(a => { if (a.dataset.route === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    try {
      if (key) viewApproach(key);
      else if (view === 'experiments') viewExperiments();
      else if (view === 'methodology') viewMethodology();
      else viewOverview();
    } catch (e) {
      console.error(e);
      app.innerHTML = `<div class="wrap"><p class="err">This view could not be drawn: ${esc(e.message)}</p></div>`;
    }
    window.scrollTo(0, 0);
  }

  // Tooltips: hover or focus on desktop, tap on touch screens. Fixed-positioned and clamped to the viewport.
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
      document.getElementById('foot-right').textContent = `Results built ${j.generated_at_utc.slice(0, 10)}`;
      route();
    })
    .catch(e => { app.innerHTML = `<div class="wrap"><p class="err">Results could not be loaded: ${esc(e.message)}. Start the dashboard with the local server described in the README.</p></div>`; });
})();
