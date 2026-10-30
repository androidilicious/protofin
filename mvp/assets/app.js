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
    gap: 'How far ahead (or behind) $1 in the approach is compared with $1 in the Deterministic baseline.',
    baseline: 'Research baseline: the Deterministic Quantitative Model. The research question is whether the AI approaches improve on it.',
    correlation: 'Correlation: how closely two series move together month by month, from −1 (opposite) to +1 (in lockstep). It compares monthly returns, not the curves\' levels.',
    nosignal: 'No-signal portfolio: the same assets and starting weights as the approach, rebalanced every month on the same dates, prices and costs, with the forecasting signal switched off.',
    pvalue: 'p-value: how often a difference at least this large would appear by chance if the signals added nothing. Below 0.05 counts as statistically significant; here both are well above it.',
    signalvalue: 'Signal value: net CER with the forecasts minus net CER of the same portfolio with the forecasts switched off (same assets, starting mix, trading rules and costs). Positive means the signals helped.',
    commonbench: 'Passive Portfolio Reference: a simple 60% SPY / 40% IEF portfolio, rebalanced monthly under the same rules. A secondary investment reference, not the research baseline and not a fourth approach.',
    separate: 'A separate question from the research comparison: beating the passive portfolio does not show that AI improves on the Deterministic baseline, and the reverse.',
    benchmark: "Own benchmark: each approach's own fixed starting mix, rebalanced monthly. Beating it means the approach's decisions added value. It differs by approach, so it is not used to compare approaches.",
    decomposition: "An accounting split, not a cause: the gap to the passive reference equals the approach versus its own starting mix (decisions) plus its own starting mix versus the passive reference (benchmark mix).",
    cumulative: 'Cumulative return: total growth over the period after trading costs, including dividends. Not adjusted for risk.',
    vsbase: 'Net CER of the approach minus net CER of the Deterministic baseline, in percentage points per year (pre-registered comparison).',
    freeze: 'Frozen: approved and fixed before the historical test opens. Any change needs a new approval, and none is allowed once the test opens.',
    significance: 'Statistically clear: too large to be explained by chance (5% level), after adjusting for the three research comparisons.',
    ci: 'Likely range (95%): where the true difference most likely lies. If it spans zero, the gap could be chance.',
    bl: 'Black–Litterman: starts from a neutral mix and tilts toward the forecasts, more when they are confident.',
    walkforward: 'Walk-forward: each month, models are rebuilt from past data only and judged on the month that follows.',
    causalrag: 'Causal RAG: AI retrieval guided by a map of cause-and-effect findings from economics research, not just keyword similarity.',
    training: 'Training: from February 2015 the models learn from data; nothing is scored yet.',
    development: 'Development: months used to build and check the approaches. Good for spotting problems, not for picking a winner.',
    test: 'Historical test: months held back and scored once, after the freeze. Still sealed, so no results exist.',
    live: 'Live: months after the freeze. The cleanest evidence, since nobody could have seen them in advance.',
    overlap: "2023 overlaps the AI models' training data, so it is reported separately as a secondary period. The primary test is Jan 2024 – Aug 2026.",
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
    awaiting: 'Awaiting validation: built and tested without an AI model. Results stay unavailable until its real model run is done and passes its checks.',
    frozen: 'Frozen: fixed before any protected month is scored; cannot change without a new version and a full rerun.',
    approval: 'Needs approval: implemented and used, but awaiting final team sign-off.',
    design: 'Differs by design: each approach keeps its own version of this.',
    versions: 'Two versions of Causal RAG with identical agents, model, rules and settings. Only the evidence the Testing Agent may use differs.',
    substitution: 'Model substitution: the free Qwen3 4B model (the one CauseTrace uses) stands in for the planned Llama 3.1 70B. Same agents, evidence, rules and checks; a much smaller model, so results are labelled as the substitute.',
    insufficient: 'When the evidence available at the time cannot settle a hypothesis, it is marked Insufficient. It is never counted as support.',
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
    tested: ['ok', 'check', 'Tested'], exploratory: ['explor', 'review', 'Ran \u2014 gates failed'],
    awaiting_validation: ['wait', 'hourglass', 'Awaiting validation'], planned: ['plan', 'planned', 'Planned'],
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
  const FMT_GAP = { y: v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(0) + '%', tip: v => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}% vs Deterministic baseline` };
  const CB = () => D.dev.common_benchmark;
  const PASSIVE = 'Passive 60/40 reference';
  // The passive portfolio is an optional reference line: drawn dashed and hidden until the viewer turns it on.
  const commonLine = () => ({ label: PASSIVE, data: CB().wealth, color: css('--c-common'), dash: COMMON_DASH, hidden: true });
  const baseVs = k => D.dev.primary_contrasts.items.find(c => c.a === k && c.b === 'det');
  const baseChip = () => `<span class="chip base">${icon('target')}Research baseline ${tip('baseline')}</span>`;
  const freezeChip = () => CB().status === 'frozen' ? `<span class="chip frozen">${icon('lock')}Frozen ${tip('freeze')}</span>` : `<span class="chip wait">${icon('hourglass')}${esc(CB().status_label)}</span>`;

  function legendButtons(id, items) {
    return `<div class="legend" id="${id}">` + items.map((it, i) => {
      const cls = it.dash ? (it.dash[0] <= 2 ? ' dot' : ' dash') : '';
      return `<button type="button" data-i="${i}" aria-pressed="${!it.hidden}"><span class="ln${cls}" style="border-top-color:${it.color}"></span>${esc(it.label)}</button>`;
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
      data: { labels: months, datasets: lines.map(l => ({ label: l.label, data: l.data, borderColor: l.color, backgroundColor: l.color, order: l.dash ? 0 : 1, hidden: !!l.hidden,
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
  function ciBar(c, key, leftLabel, rightLabel, axis) {
    const A = axis || ciAxis(), x = v => ((v + A) / (2 * A) * 100).toFixed(2) + '%';
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
  // Causal RAG's figures are real but its agents did not pass their reliability gates. One quiet marker goes
  // wherever one of its numbers appears; the full account lives in the Appendix.
  const XNOTE = 'Exploratory: the Causal RAG agents did not pass their pre-registered reliability checks, so these '
    + 'figures are a diagnostic of the pipeline, not validated evidence. Full detail in the Appendix.';
  const SIM = () => (D.sensitivity && D.sensitivity.similarity) || {};
  const xtag = () => `<span class="xmark">exploratory${tipText(XNOTE, 'What exploratory means')}</span>`;

  // Causal RAG's series and contrasts come only from the labelled exploratory block, never from dev.series.
  const ragSeries = () => { const X = D.ap3_exploratory;
    return (X && X.state === 'results' && X.wealth) ? X : null; };
  const ragVsDet = () => { const X = D.ap3_exploratory;
    const v = X && X.vs && X.vs.vs_deterministic;
    return v ? { ...v, computed: true, significant: false, exploratory: true } : null; };

  function approachCard(s) {
    const r = s.key === 'rag' ? ragSeries() : S(s.key);
    const ragGates = D.validation.gates.filter(g => g.cells.rag.status !== 'na');
    const passed = ragGates.filter(g => g.cells.rag.status === 'pass').length;
    const blocked = ragGates.filter(g => g.cells.rag.status === 'blocked').length;
    const segColor = st => st === 'pass' ? css('--pos') : st === 'blocked' ? css('--neg') : css('--surface-3');
    const c = s.key === 'rag' ? ragVsDet() : baseVs(s.key);
    const vs = s.key === 'det' ? `<div class="vsrow"><span>The AI approaches are measured against this model.</span></div>`
      : c && c.computed ? `<div class="vsrow"><span>vs Deterministic baseline: <b class="num">${pts(c.cer_difference)}</b>, likely range ${pts(c.ci95[0])} to ${pts(c.ci95[1])} ${tip('vsbase')}</span>
        ${ciBar(c, s.key)}${c.significant ? '' : NS}</div>` : '';
    const body = r ? `
      <div class="big"><span class="v num">${pct(r.metrics.cer)}</span><span class="l">net CER per year ${tip('cer')}</span></div>
      ${s.key === 'rag' ? `<p class="sub">${esc(D.ap3_exploratory.why)}</p>` : ''}${vs}`
      : `<div class="unavail"><span><b>No results yet.</b> No comparison with the baseline until a real model run passes its reliability checks.</span>
          <div class="prog" role="img" aria-label="${passed} of ${ragGates.length} validation checks passed, ${blocked} blocked">${ragGates.slice().sort((x, y) => ORDER[x.cells.rag.status] - ORDER[y.cells.rag.status]).map(g => `<i style="flex:1;background:${segColor(g.cells.rag.status)};margin-right:2px"></i>`).join('')}</div>
          <div class="ilegend"><span><i class="sw" style="background:${css('--pos')}"></i>${passed} passed</span><span><i class="sw" style="background:${css('--surface-3')}"></i>${ragGates.length - passed - blocked} to do</span><span><i class="sw" style="background:${css('--neg')}"></i>${blocked} blocked</span></div></div>`;
    return `<article class="acard${s.key === 'det' ? ' baseline' : ''}" style="--c:var(${VAR[s.key]})">
      <div class="t">${badge(s.key)}<a href="#${SLUG[s.key]}">${esc(s.name)}</a>${s.key === 'rag' && r ? xtag() : ''}</div>
      ${s.key === 'det' ? `<div class="chips">${baseChip()}</div>`
        : s.key === 'rag' ? ''
        : r ? '' : `<div class="chips"><span class="chip wait">${icon('hourglass')}Awaiting validation ${tip('awaiting')}</span></div>`}
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
      return `<g class="node">${k === 'det' ? `<circle class="ring" cx="${x}" cy="${y}" r="23"/>` : ''}<circle cx="${x}" cy="${y}" r="17" fill="var(${VAR[k]})"/><text x="${x}" y="${y + 4.5}" text-anchor="middle">${NUMBER[k]}</text>
        <text class="n" x="${x}" y="${below ? y + 36 : y - 30}" text-anchor="middle">${k === 'det' ? 'Deterministic · baseline' : name(k)}</text></g>`; };
    const list = `<ul class="tri-list">${items.map(c => `<li class="${c.computed ? 'done' : 'pending'}"><span class="pair">${badge(c.a)}${badge(c.b)}</span>
      <span>${SHORT[c.a]} ${c.computed ? '−' : 'vs'} ${SHORT[c.b]}: <b>${c.computed ? pts(c.cer_difference) : 'pending'}</b></span><small>${c.computed ? `range ${pts(c.ci95[0])} to ${pts(c.ci95[1])} · ${c.significant ? 'statistically clear' : 'not statistically clear'}` : 'needs Causal RAG results'}</small></li>`).join('')}</ul>`;
    return list + `<svg class="tri" viewBox="-50 -30 540 330" role="img" aria-label="Primary comparison: ${items.map(c => c.computed ? `${sys(c.a).short} minus ${sys(c.b).short} ${pts(c.cer_difference)}, ${c.significant ? 'significant' : 'not significant'}` : `${sys(c.a).short} vs ${sys(c.b).short} pending`).join('; ')}">
        ${items.map(edge).join('')}${['det', 'jev', 'rag'].map(node).join('')}</svg>
      <div class="tri-legend"><span><i></i>Computed on development months</span><span><i class="p"></i>Pending</span></div>
      ${items.filter(c => c.computed).map(c => `<p class="sub"><b>${SHORT[c.a]} − ${SHORT[c.b]}</b>: ${pts(c.cer_difference)} net CER per year, likely range ${pts(c.ci95[0])} to ${pts(c.ci95[1])}: ${c.significant ? 'statistically clear' : 'not statistically clear'}.</p>`).join('')}
      <p class="sub">The comparisons with Causal RAG are pending. All three are judged together ${tip('significance')}</p>`;
  }

  // Same metrics for every approach. opts.baseline adds the pre-registered "vs Deterministic baseline" row;
  // opts.bench adds a final, visually separate column for the passive 60/40 reference.
  function compareTable(keys, opts = {}) {
    const rows = [['cer', 'Net CER', m => pct(m.cer), true], ['sharpe', 'Sharpe ratio', m => num(m.sharpe)], ['drawdown', 'Worst fall', m => pct(m.max_drawdown)],
      ['cumulative', 'Cumulative return', m => pct(m.cumulative_return)], ['volatility', 'Volatility', m => pct(m.volatility)], ['turnover', 'Turnover', m => pct(m.turnover, 0)]]
      .concat(opts.baseline ? [['vsbase', 'Net CER vs baseline', null]] : []);
    const seriesOf = x => x === 'rag' ? ragSeries() : S(x);
    const vsb = x => { if (x === 'det') return 'baseline';
      const c = x === 'rag' ? ragVsDet() : baseVs(x);
      return c && c.computed ? pts(c.cer_difference) : 'pending'; };
    const cell = (x, f, pr) => { if (!f) return vsb(x); const r = seriesOf(x);
      if (!r) return pr ? 'not run' : '—';
      const m = r.metrics;
      return f({ ...m, cumulative_return: m.cumulative_return ?? m.cumulative, max_drawdown: m.max_drawdown ?? m.drawdown }); };
    const col = k => k === 'rag' ? ' class="rag-col"' : '';
    const head = k => `<th${col(k)}><span class="nw"><span class="badge" style="background:var(${VAR[k]});width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:5px"></span>${SHORT[k]}</span>${k === 'det' && opts.baseline ? '<small class="bl">baseline</small>' : ''}${k === 'rag' && ragSeries() ? '<small class="bl xs">exploratory</small>' : ''}</th>`;
    const label = (l, k) => { const w = l.split(' '); return `${w.slice(0, -1).join(' ')} ${tipw(w.at(-1), k)}`; };
    return `<div class="cmpwrap"><table class="cmp"><thead><tr><th>Development ${devYears()}</th>${keys.map(head).join('')}${opts.bench ? `<th class="cb"><span class="ln-cb" aria-hidden="true"></span>Passive<span class="ph-hide"> 60/40 reference</span></th>` : ''}</tr></thead>
      <tbody>${rows.map(([k, l, f, pr]) => `<tr${pr ? ' class="primary"' : ''}${f ? '' : ' class="rel"'}><td>${label(l, k)}</td>${keys.map(x => `<td class="num${x === 'rag' ? ' rag-col' : ''}">${cell(x, f, pr)}</td>`).join('')}${opts.bench ? `<td class="num cb">${f ? f(CB().metrics) : '—'}</td>` : ''}</tr>`).join('')}</tbody></table></div>
      ${keys.includes('rag') ? (ragSeries()
        ? '<p class="sub">Causal RAG holds a different mix and trades far more, and its column is exploratory. <a href="#appendix?c=causal-rag">What that means</a>.</p>'
        : '<p class="sub ph-only">Causal RAG has no results yet, so it is left out of this table on small screens.</p>') : ''}`;
  }

  // Passive investment comparison: a separate, secondary question from the research comparison.
  function passivePanel(keys) {
    const row = k => { const r = k === 'rag' ? ragSeries() : S(k); if (!r) return `<div class="prow"><span class="nw">${badge(k)}${SHORT[k]}</span><span class="sub">Not run yet</span></div>`;
      const v = r.vs_common; return `<div class="prow"><span class="nw">${badge(k)}${SHORT[k]}: <b class="num">${pts(v.cer_difference)}</b></span>${ciBar(v, k)}${v.p >= 0.05 ? NS : ''}</div>`; };
    return `<section class="panel passive">
        <div class="phead"><h2>Passive investment comparison ${tip('separate')}</h2><span class="chip plain"><span class="ln-cb" aria-hidden="true"></span>${esc(PASSIVE)}</span></div>
        <p class="sub">Did a strategy beat a simple 60% SPY / 40% IEF portfolio? Net CER difference per year ${tip('commonbench')}</p>
        <div class="prows">${keys.map(row).join('')}</div>
      </section>`;
  }

  // Optional diagnostic: why the JEV and Deterministic curves look alike (from the independent integrity audit).
  const corrTxt = x => (x < 0 ? '−' : '') + Math.abs(x).toFixed(2);
  function alikePanel() {
    const A = D.audit;
    if (!A || !S('det') || !S('jev')) return '';
    const tile = (v, l, t) => `<div class="kpi"><div class="v num">${v}</div><div class="l">${esc(l)} ${tipText(t)}</div></div>`;
    return `<details class="more" id="d-alike"><summary>Why do JEV and the Deterministic curves look alike?</summary><div>
      <ul class="facts ok">
        <li>${icon('check')}<span><b>No calculation error.</b> An independent rebuild from the raw prices matches every monthly return of both approaches.</span></li>
        <li>${icon('check')}<span><b>Similar by design.</b> Both hold a balanced portfolio built on the same S&amp;P 500 fund, with bonds that move together. Their decisions shift those portfolios by only a few points.</span></li>
      </ul>
      <div class="kpis k4">
        ${tile(corrTxt(A.corr_monthly_net), 'Monthly returns move together', 'Correlation of the two approaches’ monthly returns after costs. 1 would mean identical moves.')}
        ${tile(corrTxt(A.corr_own_mixes), 'Their fixed mixes alone', 'Correlation of the two starting portfolios held unchanged, with no forecasting at all. The similarity is already there.')}
        ${tile(corrTxt(A.corr_decisions), 'Their decisions', 'Correlation of each approach’s return minus its own fixed starting portfolio. The decisions themselves are unrelated.')}
        ${tile(pct(A.same_direction, 0), 'Months moving the same way', 'Share of months in which both approaches gained, or both lost.')}
      </div>
      <h3>Monthly return gap: JEV minus Deterministic</h3>
      <div class="chartbox sm"><canvas id="c-spread" aria-label="Monthly return of JEV minus the Deterministic baseline"></canvas></div>
      <p class="sub">Above zero, JEV did better that month. The gap exceeded 1 point in ${A.months_gap_gt_1pt} of ${A.spread.length} months.</p>
      <h3>Stock (S&amp;P 500) weight each month</h3>
      <div class="legend" id="lg-spy"></div>
      <div class="chartbox sm"><canvas id="c-spy" aria-label="Share of the portfolio in the S&amp;P 500 fund for each approach"></canvas></div>
      <p class="sub">JEV always holds more stocks and longer-term bonds. About ${Math.round(A.share_from_mixes * 100)}% of the month-to-month gap comes from these different starting portfolios and ${Math.round(A.share_from_decisions * 100)}% from the decisions. Full audit report in the project repository.</p>
      <a class="go" href="#signal-value">The full story: Signal Value-Added →</a>
    </div></details>`;
  }
  function drawAlike() {
    const months = D.dev.months, A = D.audit;
    killChart('c-spread');
    chart(document.getElementById('c-spread'), { type: 'bar',
      data: { labels: months, datasets: [{ label: 'JEV minus Deterministic', data: A.spread.map(v => v * 100),
        backgroundColor: A.spread.map(v => v >= 0 ? color('jev') : color('det')), borderWidth: 0 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => monthLabel(months[it[0].dataIndex]), label: it => ` JEV minus Deterministic: ${pts(A.spread[it.dataIndex], 2)}` } } },
        scales: { x: xTicks(months), y: { ticks: { callback: v => sgn(v, Math.abs(v) + ' pts') }, grid: { color: css('--border') } } } } });
    lineChart('c-spy', 'lg-spy', months, [
      { label: 'Deterministic (baseline)', data: S('det').weights.SPY.map(v => v * 100), color: color('det') },
      { label: 'JEV', data: S('jev').weights.SPY.map(v => v * 100), color: color('jev') }],
      { y: v => v.toFixed(0) + '%', tip: v => v.toFixed(1) + '%' });
  }

  // ---------------------------------------------------------------- A. Overview (landing page)
  function viewOverview() {
    const months = D.dev.months, base = S('det');
    const c = (D.dev.primary_contrasts.items || []).find(x => x.a === 'jev' && x.b === 'det') || {};
    const done = [
      ['check', `Development backtest on ${months.length} months (${devSpan()}) for the Deterministic baseline and JEV`],
      ['check', 'Portfolio integrity audit: every monthly return rebuilt independently from raw prices'],
      ['check', 'Signal value-added: each approach against its own signal-free portfolio'],
      ['check', 'Forecast-to-allocation sensitivity: four signal strengths through each native allocator'],
      ['check', 'Within-approach experiments for the Deterministic model and the Agentic Workflow']];
    const pending = [
      ['hourglass', 'Causal RAG: 12 of 95 agent months run; both reliability gates still failing'],
      ['lock', `Historical test ${testYears()} — sealed, never opened`],
      ...(D.methodology.pending || []).slice(0, 2).map(x => ['review', String(x)])];
    const kpi = (v, l, t) => `<div class="okpi"><span class="v num">${v}</span><span class="l">${l}${t ? ' ' + tip(t) : ''}</span></div>`;
    app.innerHTML = `<div class="wrap ov">
      <section class="hero">
        <div>
          <h1>Does AI improve on our Deterministic baseline?</h1>
          <p class="lede">Three forecasting architectures, one shared evaluator, ${months.length} development months. The protected historical test is sealed.</p>
          <div class="verdict"><span class="ic">${icon('scale')}</span><div><b>No clear answer yet</b><span>${rpSeries('rag')
            ? 'All three now have development results. No difference between them is statistically clear, and Causal RAG\'s agents failed their reliability checks, so nothing here is confirmatory.'
            : 'JEV is not statistically different from the baseline, Causal RAG has no results, and nothing here is confirmatory.'}</span></div></div>
        </div>
        <div class="okpis">
          ${kpi(pct(base.metrics.cer, 2), 'Baseline net CER', 'cer')}
          ${kpi(pts(c.cer_difference, 2), 'JEV versus baseline', 'vsbase')}
          ${kpi(NSIG_LABEL, 'Every primary contrast', 'significance')}
        </div>
      </section>

      <section aria-label="The three primary approaches">
        <div class="grid3">${D.systems.map(approachCard).join('')}</div>
        <p class="sub">The Agent Committee is a variant of the Agentic Workflow, not a fourth approach. The approaches hold different assets, so differences cannot be attributed to the agents alone.</p>
      </section>

      <section class="panel">
        <div class="phead"><h2>Growth of $1, after costs ${tip('growth')}</h2><a class="go" href="#comparison">Full comparison ${icon('arrow')}</a></div>
        <div class="legend" id="lg-ov"></div>
        <div class="chartbox sm"><canvas id="c-ov" aria-label="Growth of one dollar, Deterministic baseline and JEV, across the development months"></canvas></div>
      </section>

      <section class="grid2">
        <div class="panel"><h2>${icon('check')}Completed</h2><ul class="facts ok">${done.map(([i, t]) => `<li>${icon(i)}<span>${esc(t)}</span></li>`).join('')}</ul></div>
        <div class="panel"><h2>${icon('hourglass')}Pending</h2><ul class="facts wait">${pending.filter(x => x[1]).map(([i, t]) => `<li>${icon(i)}<span>${esc(t)}</span></li>`).join('')}</ul></div>
      </section>

      <section class="panel">
        <h2>What we have found</h2>
        <div class="finds">
          ${findCard('scale', 'The two working approaches behave almost identically', `Their monthly net returns correlate at ${corr3(D.audit.corr_monthly_net)} — but with both signals switched off they correlate at ${corr3(D.sensitivity.similarity.corr_0x)}, higher still. The similarity is their starting portfolios, not agreement between their forecasts.`, '#sensitivity')}
          ${findCard('model', 'Neither approach’s signals demonstrably added value', `Against its own signal-free portfolio the Deterministic model is ${pts(D.signal_value.systems.det.value.cer_difference, 2)} and JEV ${pts(D.signal_value.systems.jev.value.cer_difference, 2)} a year. Neither interval excludes zero.`, '#signal-value')}
          ${findCard('flow', 'Each architecture loses its signal somewhere different', `The Deterministic view is shrunk to ${(D.sensitivity.systems.det.posterior_keeps * 100).toFixed(1)}% inside Black–Litterman; JEV’s allocator passes its view through in full but the view is tiny before it arrives; only the Committee is attenuated by a position limit.`, '#sensitivity')}
          ${rpSeries('rag')
            ? findCard('review', 'Causal RAG now has a full exploratory backtest — but it is not validated', `All ${D.ap3_exploratory.months_needed} agent months ran and its net CER is ${pct(rpSeries('rag').metrics.cer, 2)}, the highest of the three. Both reliability gates still fail, no contrast is statistically clear, and its placebo test puts the real signal near the bottom of the random distribution.`, '#causal-rag')
            : findCard('hourglass', 'Causal RAG has not produced a usable result', `${D.ap3_exploratory.months_done} of ${D.ap3_exploratory.months_needed} agent months exist and both reliability gates fail, so no backtest is shown for it.`, '#causal-rag')}
        </div>
      </section>

      <section aria-label="Explore"><div class="explore">
        <a href="#pipeline"><span class="ic">${icon('flow')}</span><span><b>How a decision is made</b><span>Step through a real month, stage by stage</span></span></a>
        <a href="#experiments"><span class="ic">${icon('layers')}</span><span><b>Experiments</b><span>Every variation tested, with status and result</span></span></a>
        <a href="#appendix"><span class="ic">${icon('method')}</span><span><b>Appendix</b><span>Methods, formulas, full tables, artifacts</span></span></a>
      </div></section>
    </div>`;
    lineChart('c-ov', 'lg-ov', months, D.systems.filter(x => rpSeries(x.key)).map(x => ({
      label: x.key === 'det' ? 'Deterministic (baseline)' : x.key === 'rag' ? x.short + ' (exploratory)' : x.short,
      data: rpSeries(x.key).wealth, color: color(x.key), ...(x.key === 'rag' ? { dash: [5, 4] } : {}) })).concat([commonLine()]), FMT_WEALTH);
  }

  const NSIG_LABEL = 'Not statistically clear';
  const findCard = (ic, title, body, href) => `<a class="find" href="${href}"><span class="ic">${icon(ic)}</span><span class="tx"><b>${esc(title)}</b><span>${esc(body)}</span></span>${icon('chev', 'chev')}</a>`;

  // ---------------------------------------------------------------- C. Primary backtest comparison
  function viewComparison() {
    const months = D.dev.months, base = S('det').wealth;
    const res = D.systems.filter(s => rpSeries(s.key));
    const lbl = s => s.key === 'det' ? 'Deterministic (baseline)' : s.key === 'rag' ? s.short + ' (exploratory)' : s.short;
    const growthLines = mode => mode === 'gap'
      ? res.filter(s => s.key !== 'det').map(s => ({ label: lbl(s), data: rpSeries(s.key).wealth.map((w, i) => (w / base[i] - 1) * 100), color: color(s.key), ...(s.key === 'rag' ? { dash: [5, 4] } : {}) }))
          .concat([{ label: 'Deterministic baseline', data: months.map(() => 0), color: color('det'), dash: [6, 4] }])
      : res.map(s => ({ label: lbl(s), data: rpSeries(s.key).wealth, color: color(s.key), ...(s.key === 'rag' ? { dash: [5, 4] } : {}) })).concat([commonLine()]);
    const card = s => { const src = s.key === 'rag' ? rpSeries('rag') : S(s.key); const m = src && src.metrics;
      return `<div class="ccard" style="--c:var(${VAR[s.key]})">
        <div class="cch">${badge(s.key)}<b>${esc(s.short)}</b>${s.key === 'det' ? '<span class="chip base">Research baseline</span>' : ''}${s.key === 'rag' && m ? xtag() : ''}</div>
        <p class="sub">${esc((s.universe || []).map(a => PLAIN[a] || a).join(' · '))}</p>
        ${m ? `<div class="cmetrics">
            <div><span class="l">Net CER ${tip('cer')}</span><b class="num">${pct(m.cer, 2)}</b></div>
            <div><span class="l">Sharpe ${tip('sharpe')}</span><b class="num">${num(m.sharpe, 2)}</b></div>
            <div><span class="l">Volatility ${tip('volatility')}</span><b class="num">${pct(m.volatility, 1)}</b></div>
            <div><span class="l">Worst fall ${tip('drawdown')}</span><b class="num">${pct(m.drawdown ?? m.max_drawdown, 1)}</b></div>
          </div>` : `<div class="unavail"><span>${esc(D.ap3_exploratory.label)}. ${D.ap3_exploratory.months_done} of ${D.ap3_exploratory.months_needed} agent months exist and both reliability gates fail, so no backtest curve or metric is shown.</span></div>`}
        <a class="go" href="#${SLUG[s.key]}">How it works and full detail ${icon('arrow')}</a>
      </div>`; };
    app.innerHTML = `<div class="wrap">
      <section><div class="phead"><h1>Primary comparison</h1>${dataChip('dev')}</div>
        <p class="lede">The three primary approaches on the same ${months.length} development months, the same trade timing, the same ${esc(costLabel())} cost and the same cash rate.</p>
        <div class="callout">${icon('review')}<div><b>Different native universes.</b> The Deterministic model holds stocks, Treasuries and corporate bonds; JEV holds stocks and long Treasuries. Differences between them are not attributable to the forecasting method alone. ${tipw('A shared reference', 'commonbench')} is drawn for context.</div></div>
      </section>
      <section aria-label="The approaches"><div class="grid3">${D.systems.map(card).join('')}</div></section>
      <section class="panel">
        <div class="phead"><h2 id="g-title"><span>Growth of $1, after costs</span> ${tip('growth')}</h2>
          <div class="seg" role="group" aria-label="Chart view"><button type="button" data-g="abs" aria-pressed="true">Growth of $1</button><button type="button" data-g="gap" aria-pressed="false">Versus baseline</button></div></div>
        <div class="legend" id="lg-growth"></div>
        <div class="chartbox"><canvas id="c-growth" aria-label="Growth of one dollar for each approach with results"></canvas></div>
        <p class="sub">The gaps are within what chance could produce. ${rpSeries('rag') ? 'Causal RAG is drawn dashed: it is an <b>exploratory</b> series whose agents failed their reliability gates, and it is not comparable evidence.' : 'Causal RAG has no line: no results yet.'} ${esc(PASSIVE)}: optional dashed line ${tip('commonbench')}</p>
      </section>
      <section class="panel">
        <div class="phead"><h2>Headline metrics</h2><a class="go" href="#appendix?c=statistics">Full tables and intervals ${icon('arrow')}</a></div>
        ${compareTable(['det', 'jev', 'rag'], { bench: true, baseline: true })}
        <p class="sub">Net CER is the primary metric. No difference from the baseline is statistically clear.</p>
      </section>
      <section class="panel"><h2>Research comparisons</h2><p class="sub">Each AI approach against the Deterministic baseline, and against each other.</p>${triangle()}</section>
      ${passivePanel(['det', 'jev', 'rag'])}
      ${alikePanel()}
    </div>`;
    const drawGrowth = mode => {
      lineChart('c-growth', 'lg-growth', months, growthLines(mode), mode === 'gap' ? FMT_GAP : FMT_WEALTH);
      document.querySelector('#g-title > span').textContent = mode === 'gap' ? 'Ahead of or behind the Deterministic baseline' : 'Growth of $1, after costs';
      document.querySelector('#g-title .tip span[role=tooltip]').textContent = GLOSSARY[mode === 'gap' ? 'gap' : 'growth'];
    };
    drawGrowth('abs');
    const da = document.getElementById('d-alike');
    if (da) da.addEventListener('toggle', () => { if (da.open) drawAlike(); });
    document.querySelectorAll('[data-g]').forEach(b => b.addEventListener('click', () => {
      document.querySelectorAll('[data-g]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); drawGrowth(b.dataset.g); }));
  }

  const costLabel = () => { const c = (D.methodology.settings || []).find(x => /cost/i.test(x.title || x.label || '')); return c ? (c.value || '5 bp per dollar traded') : '5 bp per dollar traded'; };

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

  // Accounting split of the gap to the passive reference: decisions (vs own benchmark) + benchmark mix (own vs passive).
  function decompositionBars(a, key) {
    const A = Math.max(0.005, Math.abs(a.total), Math.abs(a.decisions), Math.abs(a.mix)) * 1.1;
    const bar = (v, c) => { const w = Math.abs(v) / A * 50; return `<span class="ab" style="left:${(v < 0 ? 50 - w : 50).toFixed(2)}%;width:${w.toFixed(2)}%;background:${c}"></span>`; };
    const row = (l, sub, v, c, cls) => `<div class="arow${cls ? ' ' + cls : ''}"><span class="al">${l}<small>${sub}</small></span><span class="atrack"><span class="zero"></span>${bar(v, c)}</span><b class="num">${pts(v, 2)}</b></div>`;
    return `<div class="attr" role="img" aria-label="Gap to the passive reference ${pts(a.total, 2)}: decisions ${pts(a.decisions, 2)}, benchmark mix ${pts(a.mix, 2)}">
      ${row('Decisions', 'vs its own starting mix', a.decisions, color(key))}
      ${row('Benchmark mix', 'own starting mix vs passive', a.mix, css('--c-bench'))}
      ${row('Total', 'vs passive reference', a.total, css('--c-common'), 'tot')}</div>`;
  }

  function viewApproach(key) {
    const s = sys(key);
    if (key === 'rag') return viewCausalRag(s);
    const variant = s.role === 'variant';
    const r = S(key), months = D.dev.months, bench = D.dev.benchmarks[r.neutral], vs = r.vs_neutral, vc = r.vs_common;
    const sig = signalsBlock(s, r), rep = D.reproduction[key], steps = D.native_vs_common[key], ex = r.example;
    const repLabel = { reproduced: 'matched saved results', replayed: 'matched saved results (replay only)' }[rep.status] || 'did not match';
    // Research comparison first: the baseline itself, an AI approach against the baseline, or (variant) against JEV.
    const cb = baseVs(key), wc = (D.dev.within_contrasts || [])[0];
    const research = key === 'det'
      ? `<h3>Research baseline ${tip('baseline')}</h3><p class="sub">The AI approaches are compared with this model. ${D.dev.primary_contrasts.items.filter(c => c.b === 'det').map(c => `${SHORT[c.a]} − Deterministic: <b class="num">${c.computed ? pts(c.cer_difference) : 'pending'}</b>`).join('; ')}.</p>`
      : variant && wc ? `<h3>Versus JEV (within-approach) ${tip('variant')}</h3><p class="sub"><b class="num">${pts(wc.cer_difference)}</b> net CER per year; likely range ${pts(wc.ci95[0])} to ${tipw(pts(wc.ci95[1]), 'ci')}</p>${ciBar(wc, key, 'JEV ahead', 'Committee ahead')}${wc.significant ? '' : NS}`
      : cb && cb.computed ? `<h3>Versus the Deterministic baseline ${tip('vsbase')}</h3><p class="sub"><b class="num">${pts(cb.cer_difference)}</b> net CER per year; likely range ${pts(cb.ci95[0])} to ${tipw(pts(cb.ci95[1]), 'ci')}</p>${ciBar(cb, key, 'baseline ahead', 'JEV ahead')}${cb.significant ? '' : NS}` : '';
    app.innerHTML = `<div class="wrap" style="--c:var(${VAR[key]})">
      ${variant ? `<a class="back" href="#experiments">← Experiments</a>` : approachTabs(key)}
      <section class="ahead">
        <div class="row">${variant ? `<span class="chip pause" style="color:var(--c-com)">${icon('layers')}Within-approach variant of the Agentic Workflow ${tip('variant')}</span>` : ''}${key === 'det' ? baseChip() : ''}${dataChip('dev')}</div>
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
          ${research}
          <p class="sub">Historical test ${testYears()}: sealed ${tip('test')}</p>
        </div>
        <div class="panel"><h2>Growth of $1 ${tip('growth')}</h2><div class="legend" id="lg-one"></div><div class="chartbox sm"><canvas id="c-one" aria-label="Growth of one dollar, with the baseline and the approach's own benchmark"></canvas></div></div>
      </section>
      <section class="grid2">
        <div class="panel passive"><div class="phead"><h2>Versus the passive 60/40 reference ${tip('commonbench')}</h2><span class="chip plain">Investment reference</span></div>
          <p class="sub"><b class="num">${pts(vc.cer_difference)}</b> net CER per year; likely range ${pts(vc.ci95[0])} to ${pts(vc.ci95[1])}</p>
          ${ciBar(vc, key)}${vc.p >= 0.05 ? NS : ''}
          <h3>Gap split ${tip('decomposition')}</h3>
          ${decompositionBars(r.decomposition, key)}
          <p class="sub">An accounting split. Parts may not add up exactly because of rounding.</p></div>
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
    lineChart('c-one', 'lg-one', months, [{ label: key === 'det' ? 'Deterministic (baseline)' : s.short, data: r.wealth, color: color(key) }]
      .concat(key === 'det' ? [] : variant ? [{ label: 'JEV', data: S('jev').wealth, color: color('jev'), dash: [6, 4] }]
        : [{ label: 'Deterministic baseline', data: S('det').wealth, color: color('det'), dash: [6, 4] }])
      .concat([{ label: `Own benchmark (${bench.label})`, data: bench.wealth, color: css('--c-bench'), dash: OWN_DASH }, commonLine()]), FMT_WEALTH);
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
  // ---------------------------------------------------------------- exploratory Causal RAG baseline (gate-failed)
  function exploratoryPanel() {
    const X = D.ap3_exploratory;
    if (!X) return '';
    const gates = Object.entries(X.gates_failed || {});
    const GATE_LABEL = { accuracy: 'Testing Agent fixture accuracy', opposite_direction_errors: 'Opposite-direction errors',
                         failed_months: 'Sample months without a final answer' };
    const gateVal = (k, v) => k === 'accuracy' ? pct(v, 0) : String(v);
    const head = `<div class="xhead"><span class="xtag">${icon('blocked')}${esc(X.label)}</span><span class="sub">${esc(X.identity)}</span></div>`;
    const why = `<p class="sub">${esc(X.why)}</p>`;
    const failed = gates.length ? `<ul class="xgates">${gates.map(([n, checks]) =>
        `<li><b>${esc(n)}</b> failed${Object.entries(checks).map(([k, v]) => ` · ${esc(GATE_LABEL[k] || k)} ${esc(gateVal(k, v))}`).join('')}</li>`).join('')}</ul>` : '';
    if (X.state !== 'results') {
      const pctDone = Math.round((X.months_done / X.months_needed) * 100);
      return `<section class="panel xpanel">
        ${head}${why}${failed}
        <div class="xprog"><div class="xbar"><span style="width:${pctDone}%"></span></div>
          <span class="sub">${X.months_done} of ${X.months_needed} decision months have genuine agent output${X.run_date ? ` (last run ${esc(X.run_date)})` : ''}</span></div>
        <p class="sub">No portfolio results are shown, because the replay has not finished. Nothing here is estimated or filled in: the
        curve appears only once every month has been produced by the model itself.</p>
      </section>`;
    }
    const m = X.metrics, c = X.coverage;
    const tile = (v, l) => `<div class="kpi"><div class="v num">${v}</div><div class="l">${esc(l)}</div></div>`;
    const vs = Object.entries(X.vs || {}).map(([k, v]) => {
      const nm = k.replace('AP3-AP1', 'vs the Deterministic baseline').replace('AP3-AP2B', 'vs JEV');
      return `<div class="prow"><span class="nw">${esc(nm)}: <b class="num">${pts(v.cer_difference)}</b></span><span class="sub">95% ${pts(v.ci95[0])} to ${pts(v.ci95[1])}, p = ${v.p.toFixed(2)}</span></div>`;
    }).join('');
    return `<section class="panel xpanel">
      ${head}${why}${failed}
      <div class="kpis k4">
        ${tile(pct(m.cer, 2), 'Net CER')}${tile(num(m.sharpe, 2), 'Sharpe ratio')}
        ${tile(pct(m.drawdown, 1), 'Worst fall')}${tile(pct(m.turnover, 0), 'Turnover a year')}
      </div>
      <div class="legend" id="lg-xrag"></div>
      <div class="chartbox sm"><canvas id="c-xrag" aria-label="Growth of one dollar, exploratory Causal RAG against the Deterministic baseline and JEV"></canvas></div>
      <h3>Coverage: what the agents actually produced</h3>
      <div class="kpis k4">
        ${tile(`${c.months_with_a_hypothesis} / ${c.months_scored}`, 'Scored months with a hypothesis')}
        ${tile(String(c.agent_failures), 'Months the agent failed')}
        ${tile(String(c.tests), 'Hypotheses tested')}
        ${tile(String(c.failed_tests), 'Tests that failed')}
      </div>
      <p class="sub">Months where no hypothesis survived keep the system's own failure handling: no view, so the allocator falls back to its
      starting mix. Those months are counted above and are not removed from the record.</p>
      ${vs ? `<h3>Against the other approaches</h3><div class="prows">${vs}</div>
      <p class="sub">The three approaches hold different assets and build portfolios differently, so a difference here cannot be put down to
      the agents. These comparisons are diagnostics against unvalidated output.</p>` : ''}
    </section>`;
  }
  function drawExploratory() {
    const X = D.ap3_exploratory;
    if (!X || X.state !== 'results') return;
    lineChart('c-xrag', 'lg-xrag', X.months, [
      { label: 'Causal RAG (exploratory)', data: X.wealth, color: color('rag'), dash: [5, 3] },
      { label: 'Deterministic (baseline)', data: S('det').wealth, color: color('det') },
      { label: 'Agentic Workflow (JEV)', data: S('jev').wealth, color: color('jev') }], FMT_WEALTH);
  }

  function viewCausalRag(s) {
    const a = D.ap3, demo = a.demo, g = a.graph;
    const steps = D.validation.gates.filter(x => x.cells.rag.status !== 'na');
    app.innerHTML = `<div class="wrap" style="--c:var(--c-rag)">
      ${approachTabs('rag')}
      <section class="ahead">
        <div class="row"><span class="chip wait">${icon('hourglass')}Awaiting validation ${tip('awaiting')}</span>${dataChip('na')}</div>
        <h1>${esc(s.name)} ${tip('causalrag')}</h1>
        <p class="lede">${esc(s.tagline)}</p>
        <div class="chips"><span class="chip plain">${icon('assets')}${esc(s.assets_label)}</span><span class="chip plain">${icon('calendar')}${esc(s.horizon)}</span><span class="chip plain">${icon('model')}${esc(s.model)} ${tip('substitution')}</span></div>
      </section>
      <section class="panel"><h2>How it works</h2>${flowDiagram('rag')}</section>
      ${versionsPanel()}
      ${exploratoryPanel()}
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
        <li>Too little evidence means Insufficient, never support.</li>
        <li>“Supported” means consistent with the evidence available at the time, never proof of cause.</li>
        <li>The graph rebuilds identically from the same data: ${a.graph_rebuild_identical ? 'checked' : 'not yet checked'}.</li></ul></div></details>
    </div>`;
    wireFlow('rag');
    drawExploratory();
    chart(document.getElementById('c-kg'), { type: 'bar', data: { labels: g.map(x => x.decision_year), datasets: [{ label: 'Papers', data: g.map(x => x.papers), backgroundColor: css('--border-strong'), borderRadius: 4 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.parsed.y.toLocaleString()} papers · ${g[it.dataIndex].claims.toLocaleString()} claims` } } },
        scales: { x: { grid: { display: false } }, y: { ticks: { callback: v => v === 0 ? '0' : (v / 1000) + 'k' }, grid: { color: css('--border') } } } } });
    const last = g.at(-1).pathways_by_channel;
    const names = { growth: 'Growth', inflation: 'Inflation', policy_rates: 'Policy & rates', risk_credit: 'Risk & credit', other: 'Other', direct: 'Direct' };
    const order = Object.keys(names).filter(k => k in last);
    chart(document.getElementById('c-ch'), { type: 'bar', data: { labels: order.map(k => names[k]), datasets: [{ data: order.map(k => last[k]), backgroundColor: css('--border-strong'), borderRadius: 4 }] },
      options: { indexAxis: 'y', plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.parsed.x} pathways` } } }, scales: { x: { grid: { color: css('--border') } }, y: { grid: { display: false } } } } });
  }

  function versionsPanel() {
    const V = D.ap3.versions;
    if (!V) return '';
    return `<section class="panel"><div class="phead"><h2>Two versions ${tip('versions')}</h2>
        <span class="chip plain">${icon('target')}Primary version: ${V.primary ? esc(V.primary) : 'not yet chosen'}</span></div>
      <div class="vcards">${V.items.map(v => `<div class="vcard">
        <div class="vtop"><b>${esc(v.short)}</b>${statusChip(v.status)}</div>
        <div class="vlbl">Evidence the Testing Agent can use</div>
        <ul class="ev">${v.evidence.map(e => `<li>${icon('data')}<span>${esc(e)}</span></li>`).join('')}</ul>
        <ul class="vchecks">${v.checks.map(c => `<li class="${c.done ? 'done' : 'todo'}">${icon(c.done ? 'check' : 'planned')}<span>${esc(c.text)}</span></li>`).join('')}</ul>
        <div>${dataChip('na')}</div></div>`).join('')}</div>
      <p class="sub">${esc(V.primary_note)} Comparing the two is a secondary experiment: do historical documents help? ${tip('insufficient', 'What if evidence is thin?')}</p></section>`;
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
  // ---------------------------------------------------------------- signal value-added (its own tab)
  const fmtDay = d => { const [y, m, dd] = d.split('-'); return `${+dd} ${MON[+m - 1]} ${y}`; };
  const corr3 = x => (x < 0 ? '−' : '') + Math.abs(x).toFixed(3);
  // ------------------------------------------------- Forecast-to-Allocation Sensitivity (Signal Value-Added tab)
  function sensitivitySections() {
    const S = D.sensitivity;
    if (!S) return '';
    const KEYS = ['det', 'jev', 'com'].concat(S.systems.rag ? ['rag'] : []);
    const NAME = { det: 'Deterministic', jev: 'JEV', com: 'Agent Committee', rag: 'Causal RAG' };
    const sy = k => S.systems[k];
    const pp = (v, d) => (v * 100).toFixed(d === undefined ? 2 : d) + ' pp';
    const share = v => (v * 100).toFixed(1) + '%';
    const chain = [
      { i: 'model', t: 'Forecast strength', d: 'We rescale each model\u2019s own view \u2014 to nothing, to half, as it was, to double \u2014 at the single point where a number enters its allocator.' },
      { i: 'alloc', t: 'Portfolio weight response', d: 'The allocator then does everything else, untouched: same prior, same limits, same costs. We record what it proposes and what it finally holds.' },
      { i: 'chart', t: 'Risk and return', d: 'Each scenario is run through the same evaluator, so the four versions differ only in how strongly the forecast was expressed.' }];
    const WHERE = {
      det: { head: 'Inside Black\u2013Litterman', body: `The views are large, but \u03a9 \u2014 estimated from the model\u2019s own out-of-sample errors \u2014 is large too, so the posterior keeps only ${share(sy('det').posterior_keeps)} of them. The position limits bind in ${sy('det').by_scenario['1x'].binding_months} month of ${S.months}.`,
             steps: [['View the allocator receives', sy('det').view_vs_prior_bp.toFixed(1) + ' bp'], ['What the posterior passes on', (sy('det').view_vs_prior_bp * sy('det').posterior_keeps).toFixed(2) + ' bp'], ['Resulting position change', pp(sy('det').by_scenario['1x'].active_weight)]],
             keep: sy('det').posterior_keeps },
      jev: { head: 'Before the allocator', body: `This engine has no posterior step and its cap never binds: it passes the signal on in full. The shrinking happens earlier, when the five-way tilt is averaged into one number and then weighted by the model\u2019s own confidence.`,
             steps: [['Largest tilt available', sy('jev').jev_stages.largest_tilt.toFixed(2) + ' pts'], ['After averaging the five options', sy('jev').jev_stages.weighted_offset.toFixed(2) + ' pts'], ['After the confidence weight', sy('jev').jev_stages.signal_points.toFixed(2) + ' pts']],
             keep: 1 },
      rag: { head: 'Inside Black\u2013Litterman', body: `Its view is the largest of the three posterior allocators \u2014 ${sy('rag').view_vs_prior_bp.toFixed(1)} bp a month from its own prior \u2014 but its \u03a9, estimated from its own errors, leaves only ${share(sy('rag').posterior_keeps)}. Its limits bind in ${sy('rag').by_scenario['1x'].binding_months} of ${S.months} months, rising to ${sy('rag').by_scenario['2x'].binding_months} at double strength.`,
             steps: [['View the allocator receives', sy('rag').view_vs_prior_bp.toFixed(1) + ' bp'], ['What the posterior passes on', (sy('rag').view_vs_prior_bp * sy('rag').posterior_keeps).toFixed(2) + ' bp'], ['Resulting position change', pp(sy('rag').by_scenario['1x'].active_weight)]],
             keep: sy('rag').posterior_keeps },
      com: { head: 'At the position limit', body: `Its view uncertainty is set as a multiple of the prior rather than measured from errors, so the posterior keeps ${share(sy('com').posterior_keeps)} and the response is large. The cap then does the attenuating: it binds in ${sy('com').by_scenario['2x'].binding_months} of ${S.months} months at double strength and removes ${share(sy('com').by_scenario['2x'].attenuation)} of the proposed move.`,
             steps: [['View the allocator receives', sy('com').view_vs_prior_bp.toFixed(0) + ' bp'], ['What the posterior passes on', (sy('com').view_vs_prior_bp * sy('com').posterior_keeps).toFixed(0) + ' bp'], ['Resulting position change', pp(sy('com').by_scenario['1x'].active_weight)]],
             keep: sy('com').posterior_keeps } };
    const xw = k => sy(k) && sy(k).exploratory ? xtag() : '';
    const whereCard = k => `<div class="fas-where" style="--c:var(${VAR[k]})">
        <h3>${badge(k)}${esc(NAME[k])}${xw(k)}</h3>
        <span class="fas-tag">${esc(WHERE[k].head)}</span>
        <ol class="fas-funnel">${WHERE[k].steps.map((st, i) => `<li><span class="l">${esc(st[0])}</span><b class="num">${esc(st[1])}</b>${i < 2 ? '<i aria-hidden="true"></i>' : ''}</li>`).join('')}</ol>
        <div class="fas-keep"><span class="l">Share the allocator passes on</span><span class="t"><span style="width:${(WHERE[k].keep * 100).toFixed(1)}%;background:var(${VAR[k]})"></span></span><b class="num">${share(WHERE[k].keep)}</b></div>
        <p class="sub">${esc(WHERE[k].body)}</p>
      </div>`;
    const row = (k, s) => { const r = sy(k).by_scenario[s];
      return `<tr${s === '1x' ? ' class="now"' : ''}><th scope="row">${esc(S.labels[s])}</th>
        <td class="num">${pp(r.active_weight)}</td><td class="num">${pct(r.net_cer, 2)}</td><td class="num">${pct(r.vol, 1)}</td>
        <td class="num">${r.turnover.toFixed(2)}&times;</td><td class="num">${r.cost_bp.toFixed(1)} bp</td>
        <td class="num">${r.binding_months}</td>
        <td class="num">${r.vs_1x ? `${pts(r.vs_1x.cer_difference, 2)} <span class="sub nw">[${pts(r.vs_1x.ci95[0], 2)}, ${pts(r.vs_1x.ci95[1], 2)}]</span>` : '\u2014'}</td></tr>`; };
    const scenTable = k => `<div class="fas-tbl"><h3>${badge(k)}${esc(NAME[k])} <span class="sub">\u00b7 ${esc(sy(k).neutral_label)}</span>${xw(k)}</h3>
        <div class="fas-scroll"><table class="cmp"><thead><tr><th scope="col">Signal strength</th><th scope="col">Position change</th><th scope="col">Net CER</th>
          <th scope="col">Volatility</th><th scope="col">Turnover</th><th scope="col">Cost</th><th scope="col">Limit binds</th>
          <th scope="col">Net CER vs as-built</th></tr></thead>
        <tbody>${S.scenarios.map(s => row(k, s)).join('')}</tbody></table></div></div>`;
    const sim = S.similarity;
    return `
      <section class="panel" id="sva-transmission">
        <h2>Do the forecasts actually move the portfolios?</h2>
        <p class="sva-body">The experiments above compared each approach with its signals switched off. That answers whether the signals helped. It does not say whether they ever reached the portfolio. So we turned the dial: each model\u2019s own view was rescaled to nothing, to half, to as it was, and to double, at the one point where a number enters its allocator \u2014 and nothing else was changed.</p>
        <div class="fas-chain">${chain.map((c, i) => `<div class="fas-step"><span class="ic">${icon(c.i)}</span><b>${esc(c.t)}</b><p>${esc(c.d)}</p>${i < 2 ? '<i class="arw" aria-hidden="true"></i>' : ''}</div>`).join('')}</div>
        <p class="sub">${S.months} development months. The as-built version reproduces the already-published results exactly, and the zero-strength version is a genuine signal-free configuration \u2014 both checked before any result was read.</p>
      </section>

      <section class="panel" id="sva-response">
        <h2>Turning the dial</h2>
        <div class="sva-split">
          <div><div class="legend" id="lg-fas-wt"></div>
            <div class="chartbox xs"><canvas id="c-fas-wt" aria-label="Average position change away from each approach's starting weights, at zero, half, as-built and double signal strength"></canvas></div>
            <p class="sub">How far the portfolio sits from its own starting weights, on average.</p></div>
          <div><div class="legend" id="lg-fas-cer"></div>
            <div class="chartbox xs"><canvas id="c-fas-cer" aria-label="Net certainty-equivalent return at zero, half, as-built and double signal strength"></canvas></div>
            <p class="sub">Net CER per ${tipw('year', 'cer')} for the same four scenarios.</p></div>
        </div>
        <p class="sva-body">The two primary approaches barely move. At their as-built strength the Deterministic portfolio sits ${pp(sy('det').by_scenario['1x'].active_weight)} from its starting weights and JEV ${pp(sy('jev').by_scenario['1x'].active_weight)}. Doubling the signal still leaves both inside ${pp(Math.max(sy('det').by_scenario['2x'].active_weight, sy('jev').by_scenario['2x'].active_weight))}. The Agent Committee, a within-approach variant on the same two assets and the same starting weights, moves ${pp(sy('com').by_scenario['1x'].active_weight)} \u2014 which is what a transmitted signal looks like.</p>
        ${KEYS.map(scenTable).join('')}
        <p class="sub">Position change is the average distance from the approach\u2019s own starting weights. Turnover is annualised one-way; cost is annualised. Intervals are 95% ranges from the frozen paired bootstrap. ${S.validation.any_scenario_statistically_clear ? '' : 'No scenario difference excludes zero, so none of these differences is statistically supported.'}</p>
      </section>

      <section class="panel" id="sva-where">
        <h2>Where each signal is lost</h2>
        <p class="sva-body">The three architectures lose their signals in three different places. Only one of them loses it to a position limit.</p>
        <div class="fas-wheres">${KEYS.map(whereCard).join('')}</div>
      </section>

      <section class="panel" id="sva-similarity">
        <h2>What this says about the similarity</h2>
        <div class="fas-corr">
          <div class="fas-cc"><span class="v num">${corr3(sim.corr_1x)}</span><span class="l">Deterministic and JEV, as built ${tipw('', 'correlation')}</span></div>
          <div class="fas-cc hi"><span class="v num">${corr3(sim.corr_0x)}</span><span class="l">The same two with both signals switched off</span></div>
          <div class="fas-cc"><span class="v num">${corr3(sim.corr_signal_parts)}</span><span class="l">Just the part their signals contribute</span></div>
        </div>
        <p class="sva-body">With the signals off, the two portfolios are <b>more</b> alike, not less. The parts their forecasts contribute are mildly negatively related, so the forecasts do disagree \u2014 there is simply very little of that disagreement in the result: it is ${share(sy('det').signal_variance_share)} of the Deterministic portfolio\u2019s month-to-month variation and ${share(sy('jev').signal_variance_share)} of JEV\u2019s. The similarity is two comparable stock-and-bond portfolios, lightly disturbed.</p>
        <p class="sva-body">The Agent Committee is the check on that reading. Same approach family, same two assets, same starting weights, same cap \u2014 but its signal does reach the portfolio, and its correlation with the Deterministic model falls to ${corr3(sim.corr_det_vs_committee_1x)}. When a signal transmits, the similarity breaks.</p>
      </section>

      <section class="panel" id="sva-transmission-read">
        <h2>How to read this</h2>
        <ul class="sva-read">
          <li><b>Reaching the portfolio is not the same as being useful.</b> This experiment measures how much of a view survives to the weights. A portfolio can react strongly to a view that carries no information, and a useful view can be shrunk to nothing. Whether these views are informative is the question the experiments above ask.</li>
          <li><b>Stronger is not better.</b> Doubling the signal raised JEV\u2019s net CER, lowered the Deterministic model\u2019s, and cost the Committee ${pts(sy('com').by_scenario['2x'].vs_1x.cer_difference, 2)} as its cap began to bind. Costs rose in all three. The double-strength scenario is a diagnostic stress test, not a proposal.</li>
          <li><b>Nothing here is statistically supported.</b> ${S.months} months is a short sample and every interval in the tables includes zero. The weight responses are exact; the performance differences are not.</li>
          <li><b>The approaches are not interchangeable.</b> They hold different assets with different starting weights, so position changes compare only in relative terms.</li>
        </ul>
        <p class="sub">Pre-registered before the scenarios were run. Rebuilt independently from the pinned prices: ${S.validation.audit_checks} checks, ${S.validation.audit_failures} failures. Full method and results: <code>${esc(S.report)}</code>.</p>
      </section>

      ${S.systems.rag ? '' : `<section class="panel" id="sva-transmission-rag">
        <h2>${badge('rag')}Agentic Causal RAG \u2014 not included</h2>
        <div class="unavail"><span><b>${esc(S.ap3.status.toLowerCase().replace(/^./, c => c.toUpperCase()))}.</b> Genuine model outputs cover ${S.ap3.months_available} of the ${S.ap3.months_required} months this needs, and both reliability checks are still failing, so there is no forecast series to rescale. No scenario was estimated or stood in for it.</span>
          <ul class="sub">${S.ap3.blockers.map(b => `<li>${esc(b)}</li>`).join('')}</ul>
          <span class="sub">Anything later built on the current outputs keeps the label ${esc(S.ap3.designation)}.</span></div>
      </section>`}

      ${S.systems.rag ? `<section class="panel" id="sva-transmission-rag">
        <h2>${badge('rag')}Agentic Causal RAG${xtag()}</h2>
        <p class="sva-body">${esc(S.ap3.categorical_note || '')} <a href="#appendix?c=causal-rag">Why its figures are exploratory</a>.</p>
      </section>` : ''}`;
  }

  function sensitivityCharts() {
    const S = D.sensitivity;
    if (!S) return;
    const KEYS = ['det', 'jev', 'com'].concat(S.systems.rag ? ['rag'] : []);
    const NAME = { det: 'Deterministic', jev: 'JEV', com: 'Agent Committee', rag: 'Causal RAG' };
    const labels = S.scenarios.map(s => S.labels[s].replace(/ \(.*\)/, '') + ' (' + s + ')');
    const bars = (canvasId, legendId, pick, fmt) => {
      killChart(canvasId);
      const items = KEYS.map(k => ({ label: NAME[k], color: color(k), data: S.scenarios.map(s => pick(S.systems[k].by_scenario[s])) }));
      const lg = document.getElementById(legendId);
      if (lg) lg.outerHTML = legendButtons(legendId, items);
      const ch = chart(document.getElementById(canvasId), {
        type: 'bar',
        data: { labels, datasets: items.map(it => ({ label: it.label, data: it.data, backgroundColor: it.color, borderColor: it.color, borderWidth: 0, borderRadius: 3 })) },
        options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.dataset.label}: ${fmt(it.parsed.y)}` } } },
          scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: false, font: { size: 11 } } },
                    y: { beginAtZero: true, ticks: { callback: fmt }, grid: { color: css('--border') } } } } });
      if (ch) wireLegend(legendId, ch);
    };
    bars('c-fas-wt', 'lg-fas-wt', r => r.active_weight * 100, v => v.toFixed(0) + ' pp');
    bars('c-fas-cer', 'lg-fas-cer', r => r.net_cer * 100, v => v.toFixed(1) + '%');
  }

  function viewSignalValue() {
    const V = D.signal_value, A = D.audit;
    if (!V || !A) { app.innerHTML = '<div class="wrap"><p class="sub">This analysis is not in the current data build.</p></div>'; return; }
    const months = D.dev.months, sv = k => V.systems[k], g = V.gap, P = g.parts, IM = V.influential_month;
    const TITLE = { det: 'Deterministic signal value', jev: 'JEV signal value', rag: 'Causal RAG signal value' };
    const SVK = ['det', 'jev'].concat(sv('rag') ? ['rag'] : []);
    const ONLY = { det: 'Only the Ridge-generated portfolio tilts are switched off', jev: 'Only the JEV-generated portfolio tilts are switched off',
                   rag: 'Only the tilts driven by the agents\' assessments are switched off' };
    const Q = { det: 'Do the Deterministic model\'s forecasting signals improve performance beyond its underlying portfolio?',
                jev: 'Do JEV\'s AI-generated forecasts improve performance beyond its underlying portfolio?',
                rag: 'Do the Causal RAG agents\' assessments improve performance beyond the same underlying portfolio?' };
    const TAKE = { det: v => `Lower with signals, by ${mag(v.cer_difference)}. No statistically significant improvement from the Deterministic signals.`,
                   jev: v => `Higher with signals, by ${mag(v.cer_difference)}: a positive observed contribution, but not statistically significant.`,
                   rag: v => `Higher with signals, by ${mag(v.cer_difference)}, but not statistically significant — and its agents failed their reliability checks, so this is a diagnostic, not evidence.` };
    const eyebrow = (n, label) => `<div class="sva-eyebrow"><span class="n">${n}</span>${esc(label)}</div>`;
    const mix = k => { const w = sv(k).no_signal_weights, as = Object.keys(w);
      return `<div class="mixbar" role="img" aria-label="Starting weights: ${as.map(a => `${a} ${Math.round(w[a] * 100)} percent`).join(', ')}">${as.map(a => `<span style="flex:${w[a]} 1 0;background:${assetColor(a)}"></span>`).join('')}</div>
        <div class="mixlegend">${as.map(a => `<span><i style="background:${assetColor(a)}"></i>${a} ${Math.round(w[a] * 100)}%</span>`).join('')}</div>`; };
    const xbadge = k => sv(k) && sv(k).exploratory ? xtag() : '';
    const expCard = (k, n) => `<div class="sva-exp" style="--c:var(${VAR[k]})">
        <div class="sva-exp-h"><span class="sva-tag">Experiment ${n}</span><h3>${badge(k)}${TITLE[k]}</h3></div>${xbadge(k)}
        <div class="sva-vs"><span class="pill">With signals</span><span class="x">vs</span><span class="pill off">Without signals</span>${tip('nosignal')}</div>
        ${mix(k)}
        <ul class="sva-setup">
          <li>${icon('assets')}<span>Same assets: ${sv(k).universe.join(', ')}</span></li>
          <li>${icon('alloc')}<span>Same starting weights: ${Object.values(sv(k).no_signal_weights).map(w => Math.round(w * 100) + '%').join(' / ')}</span></li>
          <li>${icon('calendar')}<span>Same evaluation dates, prices, monthly rebalancing and trading costs</span></li>
          <li class="only">${icon('model')}<span>${ONLY[k]}</span></li>
        </ul>
        <p class="sva-q">${esc(Q[k])}</p>
      </div>`;
    const cerMax = Math.max(...SVK.flatMap(k => [sv(k).with.cer, sv(k).without.cer])) * 1.12;
    const ciAx = Math.max(...SVK.flatMap(k => sv(k).value.ci95.map(Math.abs))) * 1.1;
    const cerRow = (label, v, c, dashed) => `<div class="cerbar"><span>${label}</span><span class="t"><span class="${dashed ? 'off' : ''}" style="width:${(v / cerMax * 100).toFixed(1)}%;background:${c}"></span></span><b class="num">${pct(v, 2)}</b></div>`;
    const resCard = (k, n) => { const s = sv(k), v = s.value;
      return `<div class="sva-exp" style="--c:var(${VAR[k]})">
        <div class="sva-exp-h"><span class="sva-tag">Experiment ${n}</span><h3>${badge(k)}${esc(sys(k).short)}</h3></div>${xbadge(k)}
        <div class="cerbars" aria-label="Net CER with signals ${pct(s.with.cer, 2)}, without signals ${pct(s.without.cer, 2)}">
          <div class="sub">Net CER per ${tipw('year', 'cer')}</div>
          ${cerRow('With signals', s.with.cer, color(k), false)}${cerRow('Without signals', s.without.cer, css('--c-bench'), true)}</div>
        <div class="sva-delta"><span class="big num">${pts(v.cer_difference, 2)}</span><span class="sub">incremental net ${tipw('CER', 'signalvalue')}</span></div>
        <div class="vsrow"><span>95% interval ${pts(v.ci95[0], 2)} to <span class="nw">${pts(v.ci95[1], 2)}&nbsp;${tip('ci')}</span> · <span class="nw">p = ${v.p.toFixed(2)}&nbsp;${tip('pvalue')}</span></span>
          ${ciBar(v, k, 'signals hurt', 'signals help', ciAx)}<span class="nsig">${v.ci95[0] <= 0 && v.ci95[1] >= 0 ? 'Interval includes zero: not statistically significant' : 'Interval excludes zero'}</span></div>
        <div class="legend" id="lg-sva-${k}"></div>
        <div class="chartbox xs"><canvas id="c-sva-${k}" aria-label="Growth of one dollar, ${esc(sys(k).short)} with and without its signals"></canvas></div>
        <p class="sva-take">${esc(TAKE[k](v))}</p>
      </div>`; };
    const share = v => Math.round(v / g.total.cer_difference * 100);
    const steps = [['observe', 'Observation'], ['tests', 'Experiments'], ['results', 'Results'], ['explain', 'Explanation'], ['takeaway', 'Takeaway']];
    const detail = [
      { l: 'Higher equity exposure', sub: '60% vs 45% stocks in the no-signal portfolios', v: P.stock, c: css('--c-bench') },
      { l: 'Different bond exposure', sub: 'long Treasuries vs Treasuries and corporate bonds', v: P.bond, c: css('--c-bench') },
      { l: 'JEV\'s signal contribution', sub: 'vs its own no-signal portfolio', v: P.jev, c: color('jev') },
      { l: 'Avoided Deterministic signal loss', sub: 'the Deterministic signals cost a little', v: P.det, c: color('det') },
      { l: 'Total', sub: 'JEV minus Deterministic', v: g.total.cer_difference, c: css('--c-common'), tot: true }];
    const im = IM, tilt = im.jev_spy_weight - im.no_signal_spy_weight;
    app.innerHTML = `<div class="wrap sva">
      <section>
        <div class="phead"><h1>Signal Value-Added</h1>${dataChip('dev')}</div>
        <p class="lede">Two very different forecasting approaches produced remarkably similar results. Do their forecasting signals add value beyond the portfolio each one starts from?</p>
        <ol class="sva-steps" aria-label="The story in five steps">${steps.map(([id, l], i) => `<li><button type="button" data-jump="sva-${id}"><span class="n">${i + 1}</span>${l}</button></li>`).join('')}</ol>
      </section>

      <section class="panel" id="sva-observe">
        ${eyebrow(1, 'Observation')}
        <h2>${ragSeries() ? 'Three very different forecasting approaches, remarkably similar performance curves' : 'Two very different forecasting approaches, remarkably similar performance curves'}</h2>
        <div class="sva-split">
          <div><div class="legend" id="lg-sva-growth"></div>
            <div class="chartbox sm"><canvas id="c-sva-growth" aria-label="Growth of one dollar for each approach, March 2019 to December 2022"></canvas></div>
            <p class="sub">Growth of $1 after costs, ${devSpan()}.</p></div>
          <div class="sva-stats">
            <div class="sva-stat"><span class="v num">${corr3(A.corr_monthly_net)}</span><span class="l">Correlation of their monthly net ${tipw('returns', 'correlation')}</span></div>
            <div class="sva-stat"><span class="v num">${corr3(A.corr_own_mixes)}</span><span class="l">Correlation of their no-signal portfolios ${tipw('alone', 'nosignal')}</span></div>
            ${ragSeries() && SIM().corr_det_vs_rag_1x != null ? `<div class="sva-stat"><span class="v num">${corr3(SIM().corr_det_vs_rag_1x)}</span><span class="l">Deterministic and Causal RAG, monthly ${tipw('returns', 'correlation')}</span></div>` : ''}
          </div>
        </div>
        <p class="sva-body">${ragSeries() ? 'All three use different forecasting methods, and all three portfolios respond similarly to market movements.' : 'Although the models use different forecasting methods, their portfolios respond similarly to market movements.'} We investigated whether the forecasting signals actually added investment value or whether most performance came from the underlying asset allocations.</p>
        <p class="sva-note">${icon('check')}<span>An integrity audit rebuilt every monthly return independently from the raw prices. It matched the backtest and this dashboard and found no calculation or charting error.</span></p>
      </section>

      <section class="panel" id="sva-tests">
        ${eyebrow(2, 'Experiments')}
        <h2>What we tested</h2>
        <div class="sva-principle" role="img" aria-label="Keep the investment framework fixed; change only the forecasting signal">
          <div class="fixed"><b>${icon('assets')}Same assets</b><span>as the approach</span></div>
          <div class="fixed"><b>${icon('alloc')}Same starting weights</b><span>its own mix</span></div>
          <div class="fixed"><b>${icon('calendar')}Same dates, prices, rebalancing, costs</b><span>the shared rules</span></div>
          <div class="switch"><b>${icon('model')}Forecasting signal</b><span class="sva-toggle" aria-hidden="true"><span class="on">On</span><span>Off</span></span></div>
        </div>
        <p class="sva-principle-line"><b>Keep the investment framework fixed. Change only the forecasting signal.</b></p>
        <div class="grid2">${SVK.map((k, i) => expCard(k, i + 1)).join('')}</div>
        <p class="sub">Both experiments use the 46 development months, ${devSpan()}. They are development diagnostics, not protected historical test results.</p>
      </section>

      <section class="panel" id="sva-results">
        ${eyebrow(3, 'Results')}
        <h2>Did the signals add value?</h2>
        <div class="grid2">${SVK.map((k, i) => resCard(k, i + 1)).join('')}</div>
        <p class="sub">Both 95% intervals include zero, so neither signal's contribution is statistically significant. Values are rounded; differences are computed at full precision.</p>
      </section>

      <section class="panel" id="sva-explain">
        ${eyebrow(4, 'Explanation')}
        <h2>What explains JEV's original ${pts(g.total.cer_difference, 2)} lead?</h2>
        <p class="sub">JEV net CER minus Deterministic net CER, split into two parts that add up exactly.</p>
        <div class="gapbar" role="img" aria-label="No-signal portfolio difference ${pts(g.mix.cer_difference, 2)}, signal-related difference ${pts(g.signals.cer_difference, 2)}, total ${pts(g.total.cer_difference, 2)}">
          <span style="width:${(g.mix.cer_difference / g.total.cer_difference * 100).toFixed(2)}%;background:${css('--c-bench')}"></span><span style="width:${(g.signals.cer_difference / g.total.cer_difference * 100).toFixed(2)}%;background:${color('jev')}"></span></div>
        <div class="gaplegend">
          <div><i style="background:${css('--c-bench')}"></i><span><b class="num">${pts(g.mix.cer_difference, 2)}</b> No-signal portfolio <span class="nw">difference (${share(g.mix.cer_difference)}%)&nbsp;${tip('nosignal')}</span><small>JEV's starting mix holds more stocks and longer-term Treasuries</small></span></div>
          <div><i style="background:${color('jev')}"></i><span><b class="num">${pts(g.signals.cer_difference, 2)}</b> Signal-related difference (${share(g.signals.cer_difference)}%)<small>95% interval ${pts(g.signals.ci95[0], 2)} to ${pts(g.signals.ci95[1], 2)}, p = ${g.signals.p.toFixed(2)}: not statistically significant</small></span></div>
          <div class="tot"><span><b class="num">${pts(g.total.cer_difference, 2)}</b> Total</span></div>
        </div>
        <p class="sva-label">Accounting attribution, not proof of causality. The original ${pts(g.total.cer_difference, 2)} JEV lead does not establish AI-generated alpha.</p>
        <details class="more"><summary>Detailed split</summary><div>
          ${partBars(detail, Math.max(...detail.map(r => Math.abs(r.v))) * 1.1)}
          ${g.rounded_parts_sum !== g.rounded_total ? `<p class="sub">Rounded, the parts add up to ${sgn(g.rounded_parts_sum, Math.abs(g.rounded_parts_sum).toFixed(2))} points; at full precision they add up exactly to ${pts(g.total.cer_difference, 2)}.</p>` : ''}
        </div></details>
      </section>

      <section class="panel" id="sva-sensitivity">
        ${eyebrow(4, 'Explanation · one sensitivity check')}
        <h2>One month carries JEV's signal contribution</h2>
        <div class="sva-split">
          <div><div class="chartbox sm"><canvas id="c-sva-month" aria-label="JEV's monthly signal contribution, with the February 2020 decision highlighted"></canvas></div>
            <p class="sub">JEV with signals minus without, each month (points). Highlighted: the ${monthLabel(im.decision_month)} decision.</p></div>
          <div class="sva-stats">
            <div class="sva-stat"><span class="v num">${pts(im.value_with, 2)} → ${pts(im.value_without, 2)}</span><span class="l">JEV's incremental net CER, with and without the ${monthLabel(im.decision_month)} decision</span></div>
            <ul class="sva-list">
              <li>In the ${monthLabel(im.decision_month)} decision JEV reduced its stock allocation to ${pct(im.jev_spy_weight, 1)}, ${mag(-tilt, 1)} below its ${pct(im.no_signal_spy_weight, 0)} starting weight.</li>
              <li>That portfolio was held ${fmtDay(im.entry)} – ${fmtDay(im.exit)}, while SPY fell ${pct(-im.spy_return, 1)} and TLT rose ${pct(im.tlt_return, 1)}.</li>
              <li>That month added ${pts(im.jev_active_return, 2)} over the no-signal portfolio, more than the ${pts(im.jev_active_sum_all_months, 2)} summed over all 46 months.</li>
            </ul>
          </div>
        </div>
        <p class="sva-caution">${icon('info')}<span>JEV's historical answers were recorded after the fact by a model whose training data and cutoff are unknown. This decision may reflect hindsight, so it is a research limitation, not proof of foresight.</span></p>
      </section>

      <section class="panel sva-final" id="sva-takeaway">
        ${eyebrow(5, 'Takeaway')}
        <p class="sva-quote">Different forecasting architectures do not necessarily produce different investment outcomes, and neither system's signals demonstrated statistically significant incremental value in this development sample.</p>
        <ul class="sva-limits">
          <li>${icon('info')}<span>This does not prove the signals have zero value.</span></li>
          <li>${icon('calendar')}<span>The analysis uses a limited 46-month development sample (${devSpan()}).</span></li>
          <li>${icon('lock')}<span>The protected historical test has not been opened.</span></li>
          <li>${icon('hourglass')}<span>Agentic Causal RAG has not yet produced validated real-model backtest results.</span></li>
          <li>${icon('model')}<span>Turning each signal up or down moved the two primary portfolios very little, so their similarity is mostly the portfolios they start from rather than agreement between their forecasts.</span></li>
        </ul>
        <p class="sub">Full reports in the project repository: Portfolio Integrity Audit and Signal Value-Added (29 Oct 2026). Detailed calculations and diagnostics are in the <a href="#appendix?c=experiments">Appendix</a>.</p>
        <a class="go" href="#sensitivity">Next: did the forecasts ever reach the portfolios? ${icon('arrow')}</a>
      </section>
    </div>`;
    document.querySelectorAll('[data-jump]').forEach(b => b.addEventListener('click', () => document.getElementById(b.dataset.jump).scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })));
    lineChart('c-sva-growth', 'lg-sva-growth', months, [
      { label: 'Deterministic (baseline)', data: S('det').wealth, color: color('det') },
      { label: 'Agentic Workflow (JEV)', data: S('jev').wealth, color: color('jev') },
      ...(ragSeries() ? [{ label: 'Causal RAG (exploratory)', data: ragSeries().wealth, color: color('rag'), dash: [5, 4] }] : [])],
      FMT_WEALTH);
    for (const k of SVK)
      lineChart(`c-sva-${k}`, `lg-sva-${k}`, months, [
        { label: 'With signals', data: (k === 'rag' ? ragSeries() : S(k)).wealth, color: color(k), ...(k === 'rag' ? { dash: [5, 4] } : {}) },
        { label: `Without signals (${sv(k).no_signal_label})`, data: D.dev.benchmarks[sv(k).no_signal].wealth, color: css('--c-bench'), dash: OWN_DASH }], FMT_WEALTH);
    const act = sv('jev').active, hi = months.indexOf(im.decision_month);
    chart(document.getElementById('c-sva-month'), { type: 'bar',
      data: { labels: months, datasets: [{ label: 'JEV signal contribution', data: act.map(v => v * 100),
        backgroundColor: act.map((v, i) => i === hi ? color('jev') : css('--c-bench')), borderWidth: 0 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => `${monthLabel(months[it[0].dataIndex])} decision`, label: it => ` With minus without signals: ${pts(act[it.dataIndex], 2)}` } } },
        scales: { x: xTicks(months), y: { ticks: { callback: v => sgn(v, Math.abs(v).toFixed(1) + ' pts') }, grid: { color: css('--border') } } } } });
  }

  // ---------------------------------------------------------------- signal value (helpers shared with the tab)
  const mag = (x, d = 2) => Math.abs(x * 100).toFixed(d) + ' pts';
  function partBars(rows, A) {
    const bar = (v, c) => { const w = Math.abs(v) / A * 50; return `<span class="ab" style="left:${(v < 0 ? 50 - w : 50).toFixed(2)}%;width:${w.toFixed(2)}%;background:${c}"></span>`; };
    return `<div class="attr" role="img" aria-label="${esc(rows.map(r => `${r.l} ${pts(r.v, 2)}`).join('; '))}">${rows.map(r =>
      `<div class="arow${r.tot ? ' tot' : ''}"><span class="al">${esc(r.l)}<small>${esc(r.sub)}</small></span><span class="atrack"><span class="zero"></span>${bar(r.v, r.c)}</span><b class="num">${pts(r.v, 2)}</b></div>`).join('')}</div>`;
  }
  function signalValueLink() {
    const V = D.signal_value;
    if (!V) return '';
    const v = k => V.systems[k].value;
    return `<section class="panel">
        <div class="phead"><h2>Do the signals actually add value?</h2>${dataChip('dev')}</div>
        <p class="sub">Each approach against its own portfolio with the forecasting signal switched off. Deterministic: ${pts(v('det').cer_difference, 2)} net CER (p = ${v('det').p.toFixed(2)}). JEV: ${pts(v('jev').cer_difference, 2)} (p = ${v('jev').p.toFixed(2)}). Neither is statistically significant.</p>
        <a class="go" href="#signal-value">See the Signal Value-Added tab →</a>
      </section>`;
  }

  // what a completed within-approach experiment found; shown only for experiments that actually ran
  function expResult(r) {
    if (!r) return '';
    return `<div class="exres">
      <div class="exres-h"><b>${esc(r.headline)}</b><span class="chip dev">${icon('chart')}${esc(r.months)}</span></div>
      <dl class="exres-rows">${r.rows.map(x => `<div><dt>${esc(x.label)}</dt><dd class="num">${esc(x.value)}</dd><small>${esc(x.note)}</small></div>`).join('')}</dl>
      <p>${esc(r.learned)}</p>
      ${r.caution ? `<p class="exres-caution">${icon('info')}<span>${esc(r.caution)}</span></p>` : ''}
    </div>`;
  }

  function viewExperiments() {
    const E = D.experiments, months = D.dev.months, w = E.within_contrast;
    const TITLES = { det: 'Deterministic Quantitative Model', jev: 'Agentic Workflow', rag: 'Agentic Causal RAG' };
    const branch = (v, gi, i) => `<div class="branch ${v.status}"><button type="button" aria-expanded="false" aria-controls="b-${gi}-${i}">
        <span class="nm">${esc(v.name)}</span>${statusChip(v.status)}${icon('chev', 'chev')}</button>
        <div class="bd" id="b-${gi}-${i}" hidden><span>${esc(v.detail)}</span>${expResult(v.result)}${v.link ? `<a class="go" href="#${SLUG[v.link]}">${v.link === 'rag' ? 'How it works →' : 'See its results →'}</a>` : ''}</div></div>`;
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
      ${signalValueLink()}
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
      ${methodologyBody()}
    </div>`;
  }

  // The methodology detail, as a fragment, so the Appendix can hold it without a second copy.
  function methodologyBody() {
    const M = D.methodology, V = D.validation;
    const COLS = { det: ['Deterministic', ''], jev: ['Agentic Workflow (JEV)', ''], rag: ['Causal RAG', ''], com: ['Agent Committee (variant)', ''] };
    const LETTER = { det: '1', jev: '2', rag: '3', com: 'C' };
    const cell = (g, k) => { const c = g.cells[k], [cls, ic, l] = GATE[c.status];
      return c.status === 'na' ? `<div class="cell na" aria-label="${esc(COLS[k][0])}: does not apply">–</div>`
        : `<div class="cell ${cls}"><span class="tip"><button type="button" aria-label="${esc(COLS[k][0])}: ${l}${c.note ? '. ' + esc(c.note) : ''}">${icon(ic)}</button><span role="tooltip">${esc(l)}${c.note ? ': ' + esc(c.note) : ''}</span></span></div>`; };
    const pc = D.dev.primary_contrasts.items;
    return `
      <section class="panel"><div class="phead"><h2>Timeline</h2>${dataChip('sealed')}</div>
        ${phaseStrip(true)}
        <div class="olegend"><i></i>2023 overlaps the AI models' training data: secondary, reported separately ${tip('overlap')}</div>
        <div class="callout">${icon('review')}<div><b>Awaiting decision</b><ul>${M.pending.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div></div>
      </section>
      <section><div class="phead"><h2>Rules and settings</h2><div class="ilegend">${Object.keys(SETTING).map(k => `<span>${icon(SETTING[k][1])}${SETTING[k][2]} ${tip(k)}</span>`).join('')}</div></div>
        <div class="settings">${M.settings.map(x => { const [c, ic, l] = SETTING[x.status];
          return `<div class="setting"><span class="ic">${icon(x.icon)}</span><div><b>${esc(x.name)}${x.tip ? ' ' + tip(x.tip) : ''}</b><p>${esc(x.value)}</p><span class="chip ${c}">${icon(ic)}${l}</span></div></div>`; }).join('')}</div>
      </section>
      <section class="panel"><div class="phead"><h2>${esc(CB().label)} ${tip('commonbench')}</h2>${freezeChip()}</div>
        <div class="cbspec"><div class="cbmix" role="img" aria-label="${esc(CB().label)}">${Object.entries(CB().weights).map(([a, w]) => `<span style="flex:${w} 1 0;background:${assetColor(a)}"><b>${Math.round(w * 100)}%</b> ${a === 'SPY' ? 'US equities' : 'Intermediate-term Treasuries'}<small>${esc(CB().instruments[a].split('(')[0].trim())}</small></span>`).join('')}</div>
          <ul class="rules">${CB().rules.map(x => `<li>${icon('check')}<span><b>${esc(x.name)}</b>${esc(x.text)}</span></li>`).join('')}</ul></div>
        <p class="sub">A secondary investment reference, not the research baseline and not a fourth approach. ${esc(CB().data_checks)} It never changes the approaches' decisions or the research comparisons.</p>
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
        <li>The Deterministic model is the research baseline. The comparisons: ${pc.map(c => `${name(c.a)} vs ${c.b === 'det' ? 'the Deterministic baseline' : name(c.b)}`).join('; ')}.</li>
        <li>Differences are measured on the same months; uncertainty comes from resampling 6-month blocks 5,000 times.</li>
        <li>The three comparisons are corrected together (Holm). Within-approach experiments never enter this family.</li>
        <li>The passive 60/40 reference answers a separate investment question. It never enters this family and leaves every difference between approaches unchanged.</li>
        <li>With few months, only large differences are detectable: “not significant” means not enough evidence, not “no difference”.</li></ul></div></details>
      <details class="more"><summary>Why this is not a controlled experiment</summary><div><ul>
        <li>The Agentic Workflow holds stocks and 20+ year Treasuries; the other two hold stocks, 7–10 year Treasuries and corporate bonds.</li>
        <li>Horizons differ: 12-month views versus 1-month forecasts.</li>
        <li>Each reads different information, from data surprises to research papers and documents.</li>
        <li>The passive 60/40 reference does not remove these differences either: part of each approach's gap to it comes from the assets it may hold.</li>
        <li>Comparing each approach with its own benchmark helps but does not remove these differences either.</li></ul></div></details>
      <details class="more"><summary>Keeping the test honest</summary><div><ul>
        <li>Every input is used only after it became public, including later revisions.</li>
        <li>Saved AI outputs are replayed exactly; nothing missing is filled in.</li>
        <li>The historical test opens once, only with a signed approval; the scoring software refuses it otherwise.</li>
        <li>Demo screens are labelled and can never enter results.</li>
        <li>AI models may have seen past market history in training; this is disclosed, and only live months are free of it.</li></ul></div></details>`;
  }

  // ---------------------------------------------------------------- router

  // ---------------------------------------------------------------- B. Interactive backtest pipeline
  // Every value shown is read from dashboard.json's pipeline block, which the builder reads from committed
  // artifacts. Nothing is recomputed here, and an architecture with no genuine outputs shows no numbers.
  const PIPE_ICON = { data: 'data', signal: 'target', forecast: 'model', alloc: 'alloc', trade: 'cost', eval: 'chart' };
  const VKIND = { input: ['Input', 'Known before the decision'], forecast: ['Forecast', 'Made at the decision, about the future'],
                  decision: ['Decision', 'The portfolio actually chosen'], realized: ['Realised', 'What the market did afterwards'] };
  let pipeKey = 'det', pipeMonth = null, pipeStage = 'data';

  const bp = (x, d = 2) => x == null ? '—' : sgn(+(x * 1e4).toFixed(d), Math.abs(x * 1e4).toFixed(d) + ' bp');
  const ppw = (x, d = 2) => x == null ? '—' : (x * 100).toFixed(d) + '%';

  function vrow(label, value, kind, note) {
    return `<div class="prow"><span class="l">${label}</span><b class="num">${value}</b>${kind ? `<span class="k k-${kind}" title="${esc(VKIND[kind][1])}">${VKIND[kind][0]}</span>` : '<span class="k"></span>'}${note ? `<small>${note}</small>` : ''}</div>`;
  }
  const pbars = (rows, max, fmt) => `<div class="pbars">${rows.map(r => {
      const w = max > 0 ? Math.min(100, Math.abs(r.v) / max * 50) : 0;
      return `<div class="pbar"><span class="l">${esc(r.label)}</span><span class="t"><i style="${r.v >= 0 ? 'left:50%' : 'right:50%'};width:${w}%;background:${r.color || 'var(--accent)'}"></i><u></u></span><b class="num">${fmt(r.v)}</b></div>`;
    }).join('')}</div>`;

  function pipeStages(key) { return (D.pipeline && D.pipeline.stages[key]) || []; }

  function pipeValues(key, m) {
    const P = D.pipeline; if (!P) return null;
    return (P[key] || {})[m] || null;
  }

  function stagePanel(key, stage, m) {
    const st = pipeStages(key).find(x => x.id === stage) || {};
    const v = pipeValues(key, m);
    const head = `<div class="pstage-h"><span class="ic">${icon(PIPE_ICON[stage])}</span><div><b>${esc(st.name || '')}${key === 'rag' ? xtag() : ''}</b><span class="sub">${esc(st.what || '')}</span></div></div>`;
    if (!v) {
      return `<div class="pstage">${head}
        <div class="unavail"><span><b>No genuine values.</b> ${esc((D.pipeline.rag_status && D.pipeline.rag_status.reason) || '')} The stage above is the implemented design, not a result. Anything later built on the current gate-failed outputs keeps the label ${esc((D.pipeline.rag_status && D.pipeline.rag_status.designation) || '')}.</span></div>
        <p class="sub">Produces: ${esc(st.out || '')}</p></div>`;
    }
    return `<div class="pstage">${head}<div class="pbody">${stageBody(key, stage, v)}</div>
      <p class="sub">Produces: ${esc(st.out || '')} — used by the next stage.</p></div>`;
  }

  const STBADGE = { Supported: 'ok', Contradicted: 'neg', Insufficient: 'mut' };

  function ragBody(stage, v) {
    const A = ['SPY', 'IEF', 'LQD'], ac = a => assetColor(a);
    if (stage === 'data') {
      const tg = v.triggers || [];
      return `<div class="pgrid">${vrow('Decision date', esc(v.decision_date), 'input')}${vrow('Knowledge-graph vintage', esc(String(v.graph_vintage ?? '—')), 'input')}${vrow('Evidence lookups by the agent', v.evidence_calls, 'input')}${vrow('Traded at the close of', esc(v.entry), 'input')}</div>
        ${tg.length ? `<h4>What happened that month</h4><ul class="evlist">${tg.map(e => `<li><b>${esc(e.description || e.trigger)}</b><span>${esc(e.direction || '')}</span>${e.z == null ? '' : `<em class="num">${sgn(e.z, Math.abs(e.z).toFixed(2))} σ</em>`}</li>`).join('')}</ul>` : ''}
        <p class="sub">Only evidence dated before the decision enters the pool: the graph is filtered to its vintage year.</p>`;
    }
    if (stage === 'signal') {
      const h = v.hypotheses || [], c = v.status_counts || {};
      return `<div class="stbar">${['Supported', 'Contradicted', 'Insufficient'].map(st => `<span class="st-${STBADGE[st]}" style="flex:${Math.max(0.0001, c[st] || 0)} 1 0"><b>${c[st] || 0}</b>${esc(st)}</span>`).join('')}</div>
        <ul class="hyps">${h.map(x => `<li class="s-${STBADGE[x.status] || 'mut'}">
            <div class="hh"><code>${esc(x.id || '')}</code><span class="chip plain">${esc(x.trigger || '')}</span><span class="st">${esc(x.status || '—')}</span></div>
            <p>${esc(x.mechanism || '')}</p>
            <small>${esc(x.channel || '')} · stated confidence ${esc(x.confidence || '—')}</small></li>`).join('')}</ul>
        ${h.length ? '' : '<div class="unavail"><span>The agent proposed no hypothesis this month. The existing failure policy gives the month zero status features, so the allocator falls back to its prior. No return is invented.</span></div>'}
        <p class="sub">The Testing Agent's own verdicts, replayed exactly. Insufficient is never counted as support.</p>`;
    }
    if (stage === 'forecast') {
      const mx = Math.max(...A.map(a => Math.abs(v.forecast[a] || 0)), 1e-4);
      return `<h4>Assessments encoded per asset</h4>
        <div class="sfgrid">${A.map(a => `<div><b>${esc(PLAIN[a] || a)}</b>${['F_S', 'F_C', 'F_I'].map(f => `<span><i>${f === 'F_S' ? 'Supported' : f === 'F_C' ? 'Contradicted' : 'Insufficient'}</i><em class="num">${num((v.status_features[a] || {})[f], 1)}</em></span>`).join('')}</div>`).join('')}</div>
        <div class="pgrid">${vrow('Training months used', v.fit.n_train, 'input')}${vrow('Penalty chosen', v.fit.intercept_only ? 'Intercept only' : esc(v.fit.alpha), 'input', v.fit.intercept_only ? 'the encoded assessments were not used this month' : '')}</div>
        ${pbars(A.map(a => ({ label: PLAIN[a] || a, v: v.forecast[a], color: ac(a) })), mx, x => bp(x, 1))}
        <p class="sub">Signed counts of Supported, Contradicted and Insufficient become numbers only here, through the same walk-forward ridge the other approaches use. The categories themselves are never treated as magnitudes.</p>`;
    }
    if (stage === 'alloc') {
      const mx = Math.max(...A.flatMap(a => [Math.abs(v.forecast[a]), Math.abs(v.prior[a]), Math.abs(v.posterior[a])]), 1e-4);
      return `<div class="pcols">
          <div><h4>The view against the prior</h4>
            ${A.map(a => `<div class="vgrp"><h5>${esc(PLAIN[a] || a)}</h5>${pbars([
                { label: 'View (q)', v: v.forecast[a], color: ac(a) },
                { label: 'Prior (π)', v: v.prior[a], color: 'var(--border-strong)' },
                { label: 'Posterior (μ_BL)', v: v.posterior[a], color: 'var(--accent)' }], mx, x => bp(x, 1))}</div>`).join('')}
            <p class="sub">Causal RAG's own Ω, estimated from its own forecast errors, decides how much of its view survives.</p></div>
          <div><h4>Weights before and after the limits</h4>
            ${weightCompare(A, v.w_unconstrained, v.weights)}
            ${vrow('Position limits binding', v.binding ? esc(v.binding) : 'none', 'decision')}</div>
        </div>`;
    }
    if (stage === 'trade') {
      return `<div class="pcols">
          <div><h4>From the drifted holdings to the target</h4>${weightCompare(A, v.pretrade, v.weights, 'Pre-trade (drifted)', 'Target')}</div>
          <div><h4>What the trade cost</h4>
            <div class="pgrid">${vrow('One-way turnover', ppw(v.turnover, 2), 'decision')}${vrow('Transaction cost', costBp(v.cost), 'decision')}${vrow('Traded at the close of', esc(v.entry), 'decision')}${vrow('Held until', esc(v.exit), 'decision')}</div></div>
        </div>`;
    }
    return `<div class="pcols">
        <div><h4>What the month returned</h4>
          <div class="pgrid">${vrow('Gross return above cash', pct(v.gross, 2), 'realized')}${vrow('Transaction cost', costBp(v.cost), 'decision')}${vrow('Net return above cash', pct(v.net, 2), 'realized')}${vrow('Cash rate that month', pct(v.rf, 2), 'realized')}</div></div>
        <div><p class="sub">This month joins the ${D.dev.months.length}-month exploratory series. It is labelled ${esc(D.ap3_exploratory.label)}: the agents did not pass their reliability gates, so this is a diagnostic of the pipeline, not evidence of investment skill.</p></div>
      </div>`;
  }

  function stageBody(key, stage, v) {
    if (key === 'rag') return ragBody(stage, v);
    const A = key === 'det' ? ['SPY', 'IEF', 'LQD'] : ['SPY', 'TLT'];
    const ac = a => assetColor(a);
    if (stage === 'data') {
      return key === 'det'
        ? `<div class="pgrid">${vrow('Decision date', esc(v.decision_date), 'input')}${vrow('Macro releases available', v.n_macro_available + ' of 8', 'input')}${vrow('Traded at the close of', esc(v.entry), 'input')}${vrow('Held until the close of', esc(v.exit), 'input')}</div>
           <p class="sub">Only releases published before the decision date enter the panel.</p>`
        : `<div class="pgrid">${vrow('Decision date', esc(v.decision_date), 'input')}${vrow('Information cut-off', esc(String(v.info_cutoff).replace('T', ' ')), 'input')}${vrow('Regime', esc(v.regime || '—'), 'input')}${vrow('Traded at the close of', esc(v.entry), 'input')}</div>
           <p class="sub">The agent sees only the context packet built at the cut-off.</p>`;
    }
    if (stage === 'signal') {
      if (key === 'det') {
        const mx = Math.max(...v.surprises.map(x => Math.abs(x.z)), 1);
        return pbars(v.surprises.map(x => ({ label: x.label, v: x.z, color: 'var(--accent)' })), mx, x => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(2) + ' σ')
          + `<p class="sub">Standardised surprises: how far each release beat (right) or missed (left) the forecast that preceded it, in standard deviations.</p>`;
      }
      return pbars(v.probs.map(x => ({ label: x.label, v: x.p, color: x.k === v.choice ? color('jev') : 'var(--border-strong)' })), 1, x => (x * 100).toFixed(0) + '%')
        + `<div class="pgrid">${vrow('Chosen tilt', esc(v.choice_label), 'forecast')}${vrow('Probability stocks beat bonds', ppw(v.p_stocks_beat_bonds, 0), 'forecast')}${vrow('Agent confidence', num(v.confidence, 2), 'forecast')}</div>
           <p class="sub">The agent's own distribution over the five tilt choices, replayed exactly as recorded.</p>`;
    }
    if (stage === 'forecast') {
      if (key === 'det') {
        const mx = Math.max(...A.map(a => Math.abs(v.forecast[a] || 0)), 1e-4);
        return `<div class="pgrid">${vrow('Training months used', v.fit.n_train, 'input')}${vrow('Features', v.fit.n_features, 'input')}${vrow('Penalty chosen', v.fit.intercept_only ? 'Intercept only' : esc(v.fit.alpha), 'input', v.fit.intercept_only ? 'the macro features were not used this month' : '')}${vrow('Latest training month', esc(v.fit.latest_train_month), 'input')}</div>
          ${pbars(A.map(a => ({ label: PLAIN[a] || a, v: v.forecast[a], color: ac(a) })), mx, x => bp(x, 1))}
          <p class="sub">Expected return above cash over the next month. ${v.fit.intercept_only ? 'This month the inner cross-validation preferred the intercept alone, so the forecast is the training-sample mean rather than a reading of the surprises.' : ''}</p>`;
      }
      const mx = Math.max(Math.abs(v.offset_original), Math.abs(v.weighted_offset), 0.1);
      return `<div class="pfunnel">
          <div><span class="l">Probability-weighted offset</span><b class="num">${num(v.offset_original, 2)} pts</b><small>the five-way distribution averaged into one number</small></div>
          <i aria-hidden="true"></i>
          <div><span class="l">× agent confidence ${num(v.confidence, 2)}</span><b class="num">${num(v.weighted_offset, 2)} pts</b><small>the signal-induced contribution to the edge</small></div>
        </div>
        ${pbars([{ label: 'Before confidence', v: v.offset_original, color: 'var(--border-strong)' }, { label: 'After confidence', v: v.weighted_offset, color: color('jev') }], mx, x => num(x, 2) + ' pts')}
        <p class="sub">Negative points lean toward bonds, positive toward stocks.</p>`;
    }
    if (stage === 'alloc') {
      if (key === 'det') {
        const mx = Math.max(...A.flatMap(a => [Math.abs(v.forecast[a]), Math.abs(v.prior[a]), Math.abs(v.posterior[a])]), 1e-4);
        return `<div class="pcols">
            <div><h4>The view against the prior</h4>
              ${A.map(a => `<div class="vgrp"><h5>${esc(PLAIN[a] || a)}</h5>${pbars([
                  { label: 'View (q)', v: v.forecast[a], color: ac(a) },
                  { label: 'Prior (π)', v: v.prior[a], color: 'var(--border-strong)' },
                  { label: 'Posterior (μ_BL)', v: v.posterior[a], color: 'var(--accent)' }], mx, x => bp(x, 1))}</div>`).join('')}
              <p class="sub">${tipw('Black–Litterman', 'bl')} blends the view q with the equilibrium prior π. The posterior μ_BL is what the optimiser actually maximises against — here it sits far closer to the prior than to the view.</p></div>
            <div><h4>Weights before and after the limits</h4>
              ${weightCompare(A, v.w_unconstrained, v.weights)}
              ${vrow('Position limits binding', v.binding ? esc(v.binding) : 'none', 'decision')}
              <p class="sub">The unconstrained optimum is the fully invested optimum with the bounds ignored; the final weights add the 20–70 / 15–60 / 10–40 bounds.</p></div>
          </div>`;
      }
      return `<div class="pcols">
          <div><h4>The edge</h4>
            <div class="pgrid">${vrow('Equilibrium edge', num(v.base_edge, 2) + ' pts', 'input')}${vrow('Signal contribution', num(v.weighted_offset, 2) + ' pts', 'forecast')}${vrow('Edge used', num(v.edge, 2) + ' pts', 'forecast')}</div>
            <p class="sub">edge = baseEdge + confidence × offset. This is JEV's own mechanism; it is not Black–Litterman.</p></div>
          <div><h4>Weights before and after the cap</h4>
            ${weightCompare(A, { SPY: v.w_unconstrained.SPY, TLT: 1 - v.w_unconstrained.SPY }, v.weights)}
            ${vrow('Cap binding (40–80% stocks)', v.binding ? esc(v.binding) : 'none', 'decision')}
            <p class="sub">The unclipped fully invested stock weight, then the native 40–80% clip.</p></div>
        </div>`;
    }
    if (stage === 'trade') {
      return `<div class="pcols">
          <div><h4>From the drifted holdings to the target</h4>${weightCompare(A, v.pretrade, v.weights, 'Pre-trade (drifted)', 'Target')}</div>
          <div><h4>What the trade cost</h4>
            <div class="pgrid">${vrow('One-way turnover', ppw(v.turnover, 2), 'decision')}${vrow('Transaction cost', costBp(v.cost), 'decision')}${vrow('Traded at the close of', esc(v.entry), 'decision')}${vrow('Held until', esc(v.exit), 'decision')}</div>
            <p class="sub">Cost is ${esc(costLabel())} against the drifted pre-trade weights. The first month starts from cash.</p></div>
        </div>`;
    }
    const rows = key === 'det' && v.realized
      ? A.map(a => ({ label: PLAIN[a] || a, v: v.realized[a], color: ac(a) })) : [];
    return `<div class="pcols">
        <div><h4>What the month returned</h4>
          <div class="pgrid">${vrow('Gross return above cash', pct(v.gross, 2), 'realized')}${vrow('Transaction cost', costBp(v.cost), 'decision')}${vrow('Net return above cash', pct(v.net, 2), 'realized')}${vrow('Cash rate that month', pct(v.rf, 2), 'realized')}</div></div>
        <div>${rows.length ? `<h4>What each asset did</h4>${pbars(rows, Math.max(...rows.map(r => Math.abs(r.v)), 0.01), x => pct(x, 1))}` : ''}
          <p class="sub">This month joins the ${D.dev.months.length}-month development series scored by the shared evaluator. It is one month: the metrics are built from all of them.</p></div>
      </div>`;
  }

  function weightCompare(A, from, to, lf, lt) {
    const bar = w => `<span class="wbar">${A.map(a => `<span class="b" style="background:${assetColor(a)};flex:${Math.max(0.0001, w[a] || 0)} 1 0">${((w[a] || 0) * 100).toFixed(0)}</span>`).join('')}</span>`;
    return `<div class="wcmp">
      <div class="wrow"><span class="l">${esc(lf || 'Unconstrained')}</span>${bar(from)}</div>
      <div class="warr" aria-hidden="true">${icon('arrow')}</div>
      <div class="wrow"><span class="l">${esc(lt || 'Final weights')}</span>${bar(to)}</div>
      <div class="wkey">${A.map(a => `<span><i style="background:${assetColor(a)}"></i>${esc(PLAIN[a] || a)}</span>`).join('')}<span class="sub">percent of the portfolio</span></div>
      <div class="wdelta">${A.map(a => `<span>${esc(PLAIN[a] || a)} <b class="num">${sgn(+(((to[a] || 0) - (from[a] || 0)) * 100).toFixed(2), Math.abs(((to[a] || 0) - (from[a] || 0)) * 100).toFixed(2) + ' pp')}</b></span>`).join('')}</div>
    </div>`;
  }

  function viewPipeline() {
    const P = D.pipeline;
    if (!P) { app.innerHTML = '<div class="wrap"><p class="sub">The pipeline trace is not in this data build.</p></div>'; return; }
    if (!pipeMonth || !P.months.includes(pipeMonth)) pipeMonth = P.default_month || P.months[0];
    const stages = pipeStages(pipeKey);
    if (!stages.find(x => x.id === pipeStage)) pipeStage = stages[0].id;
    const idx = stages.findIndex(x => x.id === pipeStage);
    const has = !!pipeValues(pipeKey, pipeMonth);
    app.innerHTML = `<div class="wrap pipe">
      <section><div class="phead"><h1>How a decision is made</h1>${has ? dataChip('dev') : dataChip('na')}</div>
        <p class="lede">One real month, followed from the data that existed on the decision date to the return it earned. Every number is read from a committed artifact.</p>
        <div class="pctl">
          <div class="seg" role="group" aria-label="Approach">${D.systems.map(x => `<button type="button" data-pk="${x.key}" aria-pressed="${x.key === pipeKey}">${badge(x.key)}${esc(SHORT[x.key])}</button>`).join('')}</div>
          ${has ? `<label class="pmonth">Decision month
            <select id="pm">${P.months.map(m => `<option value="${m}"${m === pipeMonth ? ' selected' : ''}>${monthLabel(m)}</option>`).join('')}</select>
          </label>` : ''}
        </div>
      </section>
      <section class="panel">
        <ol class="prail" aria-label="Pipeline stages">${stages.map((x, i) => `<li><button type="button" data-ps="${x.id}" aria-current="${x.id === pipeStage ? 'step' : 'false'}" class="${i < idx ? 'done' : ''}"><span class="n">${i + 1}</span><span class="ic">${icon(PIPE_ICON[x.id])}</span><span class="t">${esc(x.name)}</span></button>${i < stages.length - 1 ? '<i class="parr" aria-hidden="true"></i>' : ''}</li>`).join('')}</ol>
        ${stagePanel(pipeKey, pipeStage, pipeMonth)}
        <div class="pnav">
          <button type="button" class="pbtn" data-step="-1"${idx === 0 ? ' disabled' : ''}>${icon('chev', 'flip')}Previous stage</button>
          <span class="sub">Stage ${idx + 1} of ${stages.length}${has ? ` · ${monthLabel(pipeMonth)} decision` : ''}</span>
          <button type="button" class="pbtn" data-step="1"${idx === stages.length - 1 ? ' disabled' : ''}>Next stage${icon('chev')}</button>
        </div>
      </section>
      ${has ? `<section class="panel"><h2>Where these numbers come from</h2>
        <ul class="srcs">${(P.sources[pipeKey] || []).map(f => `<li>${icon('data')}<code>${esc(f)}</code></li>`).join('')}</ul>
        ${pipeKey === 'det' ? `<p class="sub">Across all ${D.dev.months.length} development months the ridge penalty resolved to the intercept alone in ${(P.ridge_intercept_only_share * 100).toFixed(0)}% of asset-months, so for most months the forecast is the training mean rather than a reading of the surprises. That is a property of the frozen model, reported here rather than adjusted.</p>` : ''}
      </section>` : `<section class="panel"><h2>Why there are no numbers yet</h2>
        <div class="unavail"><span>${esc((P.rag_status || {}).reason || '')}</span>
          <ul class="sub">${(D.sensitivity.ap3.blockers || []).map(b => `<li>${esc(b)}</li>`).join('')}</ul>
          <span class="sub">Progress and reliability detail: <a href="#causal-rag">Causal RAG status</a>.</span></div></section>`}
    </div>`;
    document.querySelectorAll('[data-pk]').forEach(b => b.addEventListener('click', () => { pipeKey = b.dataset.pk; pipeStage = 'data'; killCharts(); viewPipeline(); }));
    document.querySelectorAll('[data-ps]').forEach(b => b.addEventListener('click', () => { pipeStage = b.dataset.ps; killCharts(); viewPipeline(); }));
    document.querySelectorAll('[data-step]').forEach(b => b.addEventListener('click', () => {
      const n = idx + (+b.dataset.step); if (n >= 0 && n < stages.length) { pipeStage = stages[n].id; killCharts(); viewPipeline(); } }));
    const sel = document.getElementById('pm');
    if (sel) sel.addEventListener('change', () => { pipeMonth = sel.value; killCharts(); viewPipeline(); });
  }



  // ---------------------------------------------------------------- E. Forecast-to-allocation sensitivity
  function viewSensitivity() {
    const S2 = D.sensitivity;
    if (!S2) { app.innerHTML = '<div class="wrap"><p class="sub">This analysis is not in the current data build.</p></div>'; return; }
    app.innerHTML = `<div class="wrap sva">
      <section><div class="phead"><h1>Forecast-to-allocation sensitivity</h1>${dataChip('dev')}</div>
        <p class="lede">Each approach's own view was rescaled — to nothing, to half, to as it was, to double — at the single point where a number enters its allocator. Nothing else changed.</p>
      </section>
      ${sensitivitySections()}
    </div>`;
    sensitivityCharts();
  }

  // ---------------------------------------------------------------- H. Appendix
  let apxCat = 'all', apxQuery = '';
  function viewAppendix() {
    const A = D.appendix;
    const cats = [{ id: 'all', label: 'Everything' }].concat(A.categories);
    const q = apxQuery.trim().toLowerCase();
    const hit = e => (apxCat === 'all' || e.cat === apxCat) &&
      (!q || (e.title + ' ' + e.what + ' ' + e.where).toLowerCase().includes(q));
    const shown = A.entries.filter(hit).slice().sort((a, b) => (b.primary ? 1 : 0) - (a.primary ? 1 : 0));
    const label = id => (A.categories.find(c => c.id === id) || {}).label || id;
    const entry = e => `<div class="apx${e.primary ? ' apx-primary' : ''}"><div class="apx-h"><b>${esc(e.title)}</b><span class="chip plain">${esc(label(e.cat))}</span></div>
        <p class="sub">${esc(e.what)}</p>
        <code class="apx-w">${esc(e.where)}</code>${e.doc ? '<span class="chip plain">Report</span>' : ''}${e.config ? '<span class="chip plain">Configuration</span>' : ''}</div>`;
    app.innerHTML = `<div class="wrap apxwrap">
      <section><div class="phead"><h1>Appendix</h1><span class="chip plain">${A.entries.length} entries</span></div>
        <p class="lede">Every supporting detail behind the main sections: methods and formulas, data sources, full metric tables, intervals and p-values, experiment configurations, reliability specifications and the artifacts each result came from.</p>
        <div class="apx-ctl">
          <label class="apx-search"><span class="sr">Search the appendix</span>${icon('tool')}<input type="search" id="apxq" placeholder="Search methods, data, statistics…" value="${esc(apxQuery)}"></label>
          <div class="apx-cats" role="group" aria-label="Category">${cats.map(c => `<button type="button" data-ac="${c.id}" aria-pressed="${c.id === apxCat}">${esc(c.label)}</button>`).join('')}</div>
        </div>
      </section>
      <section aria-label="Appendix entries">
        ${shown.length ? `<div class="apxs">${shown.map(entry).join('')}</div>` : '<p class="sub">Nothing matches that search.</p>'}
      </section>
      <section class="panel"><h2>Methodology in full</h2>${methodologyBody()}</section>
      <section class="panel"><h2>Build provenance</h2>
        <div class="pgrid">
          ${vrow('Repository', esc(D.build.repository), 'input')}
          ${vrow('Branch', esc(D.build.branch || '—'), 'input')}
          ${vrow('Commit this data was built against', `<code>${esc((D.build.git_commit_at_build || '').slice(0, 12))}</code>`, 'input')}
          ${vrow('Release manifest digest', `<code>${esc((D.build.release_manifest_sha256 || '').slice(0, 16))}</code>`, 'input')}
          ${vrow('Data generated', esc(D.build.generated_at_utc), 'input')}
          ${vrow('Dashboard schema', esc(D.build.dashboard_schema), 'input')}
        </div>
        <p class="sub">${esc(D.build.git_commit_note)}. The release-manifest digest is content-addressed, so it identifies the repository state exactly.</p>
      </section>
      <section class="panel"><h2>Reports and configurations in the repository</h2>
        <ul class="srcs">${A.docs.concat(A.configs).map(d => `<li>${icon('method')}<span><b>${esc(d.title)}</b><code>${esc(d.path)}</code></span></li>`).join('')}</ul>
      </section>
      <section class="panel"><h2>Glossary</h2>
        <dl class="gloss">${Object.keys(GLOSSARY).sort().map(k => { const t = GLOSSARY[k]; const i = t.indexOf(':');
          return `<div><dt>${esc(i > 0 && i < 48 ? t.slice(0, i) : k)}</dt><dd>${esc(i > 0 && i < 48 ? t.slice(i + 1).trim() : t)}</dd></div>`; }).join('')}</dl>
      </section>
    </div>`;
    const inp = document.getElementById('apxq');
    if (inp) inp.addEventListener('input', () => { apxQuery = inp.value; const at = document.activeElement === inp;
      viewAppendix(); if (at) { const n = document.getElementById('apxq'); n.focus(); n.setSelectionRange(n.value.length, n.value.length); } });
    document.querySelectorAll('[data-ac]').forEach(b => b.addEventListener('click', () => { apxCat = b.dataset.ac; viewAppendix(); }));
  }



  // ---------------------------------------------------------------- Download Content
  // A real ZIP, written here: central-directory format, deflate where the browser offers CompressionStream and
  // stored otherwise. No library and no network call, so the download works wherever the page loads.
  const CRC = (() => { const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
    return b => { let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = t[(c ^ b[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  })();

  async function deflateRaw(bytes) {
    if (typeof CompressionStream !== 'function') return null;
    try {
      const cs = new CompressionStream('deflate-raw');
      const buf = await new Response(new Blob([bytes]).stream().pipeThrough(cs)).arrayBuffer();
      return new Uint8Array(buf);
    } catch (_) { return null; }
  }

  async function makeZip(files) {
    const enc = new TextEncoder(), parts = [], central = [];
    let offset = 0;
    const d = new Date(), dosTime = ((d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1)) & 0xFFFF;
    const dosDate = (((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate()) & 0xFFFF;
    const u8 = v => typeof v === 'string' ? enc.encode(v) : v;
    for (const f of files) {
      const raw = u8(f.data), name = enc.encode(f.path), crc = CRC(raw);
      const def = await deflateRaw(raw);
      const use = def && def.length < raw.length ? def : null;
      const body = use || raw, method = use ? 8 : 0;
      const lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true);
      lh.setUint16(8, method, true); lh.setUint16(10, dosTime, true); lh.setUint16(12, dosDate, true);
      lh.setUint32(14, crc, true); lh.setUint32(18, body.length, true); lh.setUint32(22, raw.length, true);
      lh.setUint16(26, name.length, true); lh.setUint16(28, 0, true);
      parts.push(new Uint8Array(lh.buffer), name, body);
      const ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true); ch.setUint16(8, 0x0800, true);
      ch.setUint16(10, method, true); ch.setUint16(12, dosTime, true); ch.setUint16(14, dosDate, true);
      ch.setUint32(16, crc, true); ch.setUint32(20, body.length, true); ch.setUint32(24, raw.length, true);
      ch.setUint16(28, name.length, true); ch.setUint32(42, offset, true);
      central.push(new Uint8Array(ch.buffer), name);
      offset += 30 + name.length + body.length;
    }
    const cdSize = central.reduce((n, x) => n + x.length, 0);
    const eo = new DataView(new ArrayBuffer(22));
    eo.setUint32(0, 0x06054b50, true); eo.setUint16(8, files.length, true); eo.setUint16(10, files.length, true);
    eo.setUint32(12, cdSize, true); eo.setUint32(16, offset, true);
    return new Blob([...parts, ...central, new Uint8Array(eo.buffer)], { type: 'application/zip' });
  }

  const csvCell = v => { const t = v == null ? '' : String(v); return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; };
  const toCsv = (cols, rows) => [cols.join(','), ...rows.map(r => cols.map(c => csvCell(r[c])).join(','))].join('\n') + '\n';

  function exportTables() {
    const t = {}, months = D.dev.months;
    // performance metrics, every series the dashboard shows
    const perf = [];
    const pushMetrics = (id, label, kind, m) => { if (!m) return;
      perf.push({ series_id: id, label, kind, months: m.months == null ? months.length : m.months,
        net_cer: m.cer, annualized_excess_return: m.ann_excess_return, annualized_volatility: m.volatility,
        net_sharpe: m.sharpe, max_drawdown: m.max_drawdown, cumulative_net_return: m.cumulative_return,
        annualized_one_way_turnover: m.turnover == null ? '' : m.turnover }); };
    D.systems.concat(D.variants).forEach(x => S(x.key) && pushMetrics(x.key, x.short, x.role === 'primary' ? 'approach' : 'variant', S(x.key).metrics));
    const X3 = rpSeries('rag');
    if (X3) pushMetrics('rag', 'Causal RAG (EXPLORATORY - reliability gates failed)', 'approach_exploratory',
      { ...X3.metrics, ann_excess_return: X3.metrics.excess, cumulative_return: X3.metrics.cumulative, max_drawdown: X3.metrics.drawdown, months: D.dev.months.length });
    Object.entries(D.dev.benchmarks || {}).forEach(([k, b]) => pushMetrics(k, b.label || k, 'benchmark', b.metrics));
    if (CB() && CB().metrics) pushMetrics('common', CB().label, 'reference', CB().metrics);
    t['data/performance_metrics.csv'] = toCsv(['series_id', 'label', 'kind', 'months', 'net_cer',
      'annualized_excess_return', 'annualized_volatility', 'net_sharpe', 'max_drawdown',
      'cumulative_net_return', 'annualized_one_way_turnover'], perf);

    // monthly returns for every series with a monthly net series
    const mr = [];
    const addMonthly = (id, label, kind, ser) => { if (!ser || !(ser.monthly_net_return || ser.wealth)) return;
      months.forEach((m, i) => mr.push({ decision_month: m, series_id: id, label, kind,
        net_excess_return: ser.monthly_net_return ? ser.monthly_net_return[i] : '',
        wealth_index: ser.wealth ? ser.wealth[i] : '' })); };
    D.systems.concat(D.variants).forEach(x => addMonthly(x.key, x.short, 'approach', S(x.key)));
    Object.entries(D.dev.benchmarks || {}).forEach(([k, b]) => addMonthly(k, b.label || k, 'benchmark', b));
    if (CB()) addMonthly('common', CB().label, 'reference', CB());
    if (X3) addMonthly('rag', 'Causal RAG (EXPLORATORY - reliability gates failed)', 'approach_exploratory', X3);
    t['data/monthly_returns.csv'] = toCsv(['decision_month', 'series_id', 'label', 'kind', 'net_excess_return', 'wealth_index'], mr);

    // portfolio weights and the trade, per approach and month
    const w = [], P = D.pipeline;
    if (P) ['det', 'jev', 'rag'].forEach(k => Object.entries(P[k] || {}).forEach(([m, v]) => {
      Object.keys(v.weights).forEach(a => w.push({ decision_month: m, approach: SHORT[k] + (k === 'rag' ? ' (EXPLORATORY)' : ''), asset: a,
        target_weight: v.weights[a], pretrade_weight: v.pretrade[a],
        unconstrained_weight: v.w_unconstrained[a] == null ? '' : v.w_unconstrained[a],
        entry_date: v.entry, exit_date: v.exit, one_way_turnover: v.turnover, cost: v.cost,
        binding_bounds: v.binding || '', net_excess_return: v.net, gross_excess_return: v.gross })); }));
    t['data/portfolio_weights.csv'] = toCsv(['decision_month', 'approach', 'asset', 'target_weight', 'pretrade_weight',
      'unconstrained_weight', 'entry_date', 'exit_date', 'one_way_turnover', 'cost', 'binding_bounds',
      'net_excess_return', 'gross_excess_return'], w);

    // signals and forecasts, per approach and month
    const sf = [];
    if (P) {
      Object.entries(P.det || {}).forEach(([m, v]) => {
        v.surprises.forEach(x => sf.push({ decision_month: m, approach: 'Deterministic', kind: 'macro_surprise_z', item: x.label, value: x.z, units: 'standard deviations' }));
        Object.entries(v.forecast).forEach(([a, x]) => sf.push({ decision_month: m, approach: 'Deterministic', kind: 'ridge_forecast', item: a, value: x, units: 'expected excess return, decimal' }));
        Object.entries(v.prior).forEach(([a, x]) => sf.push({ decision_month: m, approach: 'Deterministic', kind: 'bl_prior_pi', item: a, value: x, units: 'expected excess return, decimal' }));
        Object.entries(v.posterior).forEach(([a, x]) => sf.push({ decision_month: m, approach: 'Deterministic', kind: 'bl_posterior_mu', item: a, value: x, units: 'expected excess return, decimal' }));
        sf.push({ decision_month: m, approach: 'Deterministic', kind: 'ridge_penalty', item: 'alpha', value: v.fit.alpha, units: '' });
      });
      Object.entries(P.jev || {}).forEach(([m, v]) => {
        v.probs.forEach(x => sf.push({ decision_month: m, approach: 'JEV', kind: 'tilt_probability', item: x.label, value: x.p, units: 'probability' }));
        sf.push({ decision_month: m, approach: 'JEV', kind: 'chosen_tilt', item: 'choice', value: v.choice, units: '' });
        sf.push({ decision_month: m, approach: 'JEV', kind: 'p_stocks_beat_bonds', item: 'p', value: v.p_stocks_beat_bonds, units: 'probability' });
        sf.push({ decision_month: m, approach: 'JEV', kind: 'probability_weighted_offset', item: 'offset', value: v.offset_original, units: 'points of edge' });
        sf.push({ decision_month: m, approach: 'JEV', kind: 'confidence', item: 'confidence', value: v.confidence, units: '' });
        sf.push({ decision_month: m, approach: 'JEV', kind: 'confidence_weighted_offset', item: 'offset', value: v.weighted_offset, units: 'points of edge' });
        sf.push({ decision_month: m, approach: 'JEV', kind: 'equilibrium_edge', item: 'base_edge', value: v.base_edge, units: 'points of edge' });
        sf.push({ decision_month: m, approach: 'JEV', kind: 'edge_used', item: 'edge', value: v.edge, units: 'points of edge' });
      });
    }
    if (P) Object.entries(P.rag || {}).forEach(([m, v]) => {
      const ap = 'Causal RAG (EXPLORATORY)';
      (v.hypotheses || []).forEach(h => sf.push({ decision_month: m, approach: ap, kind: 'hypothesis_assessment',
        item: h.id, value: h.status, units: h.trigger || '' }));
      Object.entries(v.status_counts || {}).forEach(([st, n]) => sf.push({ decision_month: m, approach: ap, kind: 'status_count', item: st, value: n, units: 'hypotheses' }));
      Object.entries(v.status_features || {}).forEach(([a, f]) => Object.entries(f).forEach(([k2, x]) =>
        sf.push({ decision_month: m, approach: ap, kind: 'status_feature', item: `${a}.${k2}`, value: x, units: 'signed count' })));
      Object.entries(v.forecast || {}).forEach(([a, x]) => sf.push({ decision_month: m, approach: ap, kind: 'calibrated_view', item: a, value: x, units: 'expected excess return, decimal' }));
      Object.entries(v.prior || {}).forEach(([a, x]) => sf.push({ decision_month: m, approach: ap, kind: 'bl_prior_pi', item: a, value: x, units: 'expected excess return, decimal' }));
      Object.entries(v.posterior || {}).forEach(([a, x]) => sf.push({ decision_month: m, approach: ap, kind: 'bl_posterior_mu', item: a, value: x, units: 'expected excess return, decimal' }));
      sf.push({ decision_month: m, approach: ap, kind: 'ridge_penalty', item: 'alpha', value: v.fit.alpha, units: '' });
    });
    t['data/signals_and_forecasts.csv'] = toCsv(['decision_month', 'approach', 'kind', 'item', 'value', 'units'], sf);

    // sensitivity scenarios
    const sc = [], SN = D.sensitivity;
    if (SN) Object.entries(SN.systems).forEach(([k, sy]) => SN.scenarios.forEach(x => { const r = sy.by_scenario[x];
      sc.push({ approach: SHORT[k], scenario: x, label: SN.labels[x], active_weight: r.active_weight, net_cer: r.net_cer,
        annualized_volatility: r.vol, net_sharpe: r.sharpe, max_drawdown: r.max_dd, annualized_turnover: r.turnover,
        annualized_cost_bp: r.cost_bp, months_with_binding_bound: r.binding_months,
        mean_abs_final_weight_change_vs_1x: r.final_change, constraint_attenuation_share: r.attenuation,
        net_cer_minus_1x: r.vs_1x ? r.vs_1x.cer_difference : '', ci95_low: r.vs_1x ? r.vs_1x.ci95[0] : '',
        ci95_high: r.vs_1x ? r.vs_1x.ci95[1] : '', p_two_sided_bootstrap: r.vs_1x ? r.vs_1x.p : '' }); }));
    t['data/sensitivity_scenarios.csv'] = toCsv(['approach', 'scenario', 'label', 'active_weight', 'net_cer',
      'annualized_volatility', 'net_sharpe', 'max_drawdown', 'annualized_turnover', 'annualized_cost_bp',
      'months_with_binding_bound', 'mean_abs_final_weight_change_vs_1x', 'constraint_attenuation_share',
      'net_cer_minus_1x', 'ci95_low', 'ci95_high', 'p_two_sided_bootstrap'], sc);

    // within-approach experiments
    const ex = [];
    (D.experiments.groups || []).forEach(g => [].concat(g.base ? [{ ...g.base, is_base: true }] : [], g.variants || []).forEach(x => {
      const r = x.result || {}, cc = r.contrast || {};
      ex.push({ approach: SHORT[g.approach] || g.approach, experiment: x.name, kind: x.is_base ? 'base' : 'variant',
        detail: x.detail || '', status: x.status, headline: r.headline || '',
        cer_difference: cc.cer_difference == null ? '' : cc.cer_difference,
        ci95_low: cc.ci95 ? cc.ci95[0] : '', ci95_high: cc.ci95 ? cc.ci95[1] : '', p_value: cc.p == null ? '' : cc.p,
        statistically_clear: cc.clear == null ? '' : (cc.clear ? 'yes' : 'no'),
        takeaway: r.learned || '' }); }));
    t['data/within_approach_experiments.csv'] = toCsv(['approach', 'experiment', 'kind', 'detail', 'status',
      'headline', 'cer_difference', 'ci95_low', 'ci95_high', 'p_value', 'statistically_clear', 'takeaway'], ex);

    // reliability gates, coverage and status
    const rel = [];
    Object.entries(D.ap3_exploratory.gates_failed || {}).forEach(([g, v]) => (v.failed_checks || v.checks || []).forEach
      ? (v.failed_checks || v.checks || []).forEach(c => rel.push({ area: 'Causal RAG reliability', gate: g, check: c.name || c.check || '',
          measured: c.value == null ? '' : c.value, threshold: c.threshold == null ? '' : c.threshold, passed: c.pass === true ? 'yes' : 'no' }))
      : null);
    const XE = D.ap3_exploratory;
    rel.push({ area: 'Causal RAG coverage', gate: '', check: 'agent months completed', measured: XE.months_done, threshold: XE.months_needed, passed: XE.months_done >= XE.months_needed ? 'yes' : 'no' });
    if (XE.coverage) Object.entries(XE.coverage).forEach(([k2, v]) => {
      if (k2 === 'status_counts') Object.entries(v || {}).forEach(([st, n]) => rel.push({ area: 'Causal RAG assessments', gate: '', check: st, measured: n, threshold: '', passed: '' }));
      else rel.push({ area: 'Causal RAG coverage', gate: '', check: k2.replace(/_/g, ' '), measured: v, threshold: '', passed: '' }); });
    if (XE.calibration) {
      rel.push({ area: 'Causal RAG calibration', gate: '', check: 'intercept-only share', measured: XE.calibration.intercept_only_share, threshold: '', passed: '' });
      rel.push({ area: 'Causal RAG calibration', gate: '', check: 'calibration slope', measured: XE.calibration.calibration_slope, threshold: '1.0 is perfect', passed: '' });
      rel.push({ area: 'Causal RAG calibration', gate: '', check: 'permutation placebo percentile', measured: (XE.calibration.placebo || {}).percentile, threshold: 'high is better', passed: '' });
    }
    (D.validation.gates || []).forEach(g => D.validation.columns.forEach(k => { const c = g.cells[k];
      if (c && c.status !== 'na') rel.push({ area: 'Validation gate', gate: SHORT[k], check: g.name, measured: c.status, threshold: '', passed: c.status === 'pass' ? 'yes' : 'no' }); }));
    t['data/reliability_and_status.csv'] = toCsv(['area', 'gate', 'check', 'measured', 'threshold', 'passed'], rel);

    t['appendix/appendix_index.csv'] = toCsv(['category', 'title', 'what', 'where'],
      D.appendix.entries.map(e => ({ category: (D.appendix.categories.find(c => c.id === e.cat) || {}).label || e.cat, title: e.title, what: e.what, where: e.where })));
    return t;
  }

  function reportHtml(appendixOnly) {
    const M = D.sensitivity, SV = D.signal_value, months = D.dev.months;
    const tbl = (cols, rows) => `<table><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map((c, i) => `<td class="${i ? 'n' : ''}">${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    const metricRows = D.systems.concat(D.variants).filter(x => S(x.key)).map(x => { const m = S(x.key).metrics;
      return [esc(x.short), pct(m.cer, 2), pct(m.ann_excess_return, 2), pct(m.volatility, 1), num(m.sharpe, 2), pct(m.max_drawdown, 1), pct(m.cumulative_return, 1), m.turnover == null ? '—' : num(m.turnover, 2) + '×']; });
    const senRows = M ? Object.entries(M.systems).flatMap(([k, sy]) => M.scenarios.map(x => { const r = sy.by_scenario[x];
      return [esc(SHORT[k] + ' · ' + M.labels[x]), pct(r.active_weight, 2), pct(r.net_cer, 2), pct(r.vol, 1), num(r.turnover, 2) + '×', r.cost_bp.toFixed(1) + ' bp', String(r.binding_months), r.vs_1x ? `${pts(r.vs_1x.cer_difference, 2)} [${pts(r.vs_1x.ci95[0], 2)}, ${pts(r.vs_1x.ci95[1], 2)}]` : '—']; })) : [];
    const apx = D.appendix.categories.map(c => `<h3>${esc(c.label)}</h3><ul>${D.appendix.entries.filter(e => e.cat === c.id).map(e => `<li><b>${esc(e.title)}</b> — ${esc(e.what)} <code>${esc(e.where)}</code></li>`).join('')}</ul>`).join('');
    const head = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(appendixOnly ? 'Appendix — Protofin Backtest' : 'Protofin Backtest — Research Report')}</title>
<style>
:root{--fg:#15202e;--mut:#5b6678;--line:#dde3ec;--bg:#fff;--accent:#2563eb}
*{box-sizing:border-box}body{margin:0 auto;padding:40px 24px 80px;max-width:900px;background:var(--bg);color:var(--fg);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h1{font-size:30px;line-height:1.2;margin:0 0 6px}h2{font-size:21px;margin:38px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:22px 0 6px}p{margin:0 0 10px}ul{margin:0 0 12px;padding-left:20px}li{margin:3px 0}
.lede{color:var(--mut);font-size:17px}code{font:12.5px ui-monospace,Menlo,monospace;background:#f3f5f9;padding:1px 5px;border-radius:4px}
table{border-collapse:collapse;width:100%;margin:10px 0 16px;font-size:13.5px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}th{color:var(--mut);font-weight:600;font-size:12.5px}
td.n,th+th{text-align:right}.note{background:#f7f9fc;border-left:3px solid var(--accent);padding:10px 14px;margin:14px 0;border-radius:0 8px 8px 0}
.warn{border-left-color:#b45309}.meta{color:var(--mut);font-size:13px}@media print{body{padding:0}h2{break-before:auto}}
</style></head><body>`;
    if (appendixOnly) return head + `<h1>Appendix</h1><p class="lede">Every supporting detail behind the Protofin backtest dashboard.</p>
<p class="meta">Generated ${esc(new Date().toISOString().slice(0, 19))}Z · branch ${esc(D.build.branch || '')} · commit ${esc((D.build.git_commit_at_build || '').slice(0, 12))}</p>
${apx}<h2>Methodology settings</h2>${tbl(['Setting', 'Value', 'Status'], (D.methodology.settings || []).map(x => [esc(x.name), esc(x.value), esc(SETTING[x.status][2])]))}
<h2>Validation gates</h2>${tbl(['Check'].concat(D.validation.columns.map(k => SHORT[k])), (D.validation.gates || []).map(g => [esc(g.name)].concat(D.validation.columns.map(k => esc(GATE[g.cells[k].status][2])))))}
<h2>Glossary</h2><ul>${Object.keys(GLOSSARY).sort().map(k => `<li>${esc(GLOSSARY[k])}</li>`).join('')}</ul></body></html>`;
    return head + `<h1>Protofin — research backtest</h1>
<p class="lede">Does AI improve on our Deterministic baseline? Three forecasting architectures on ${months.length} development months (${esc(devSpan())}), one shared evaluator.</p>
<p class="meta">Generated ${esc(new Date().toISOString().slice(0, 19))}Z · ${esc(D.build.repository)} · branch ${esc(D.build.branch || '')} · commit ${esc((D.build.git_commit_at_build || '').slice(0, 12))} · dashboard schema ${esc(D.build.dashboard_schema)}</p>
<div class="note warn"><b>Status: development diagnostics only.</b> The protected historical test window ${esc(D.windows.historical_test.join(' to '))} is sealed: it has never been opened or scored. Nothing in this report is confirmatory, and no difference reported here is statistically clear.</div>

<h2>1. The approaches</h2>
<ul>${D.systems.map(x => `<li><b>${esc(x.name)}</b> — ${esc((x.universe || []).join(', '))}. ${esc(x.summary || x.what || '')}</li>`).join('')}</ul>
<p>The Agent Committee is a within-approach variant of the Agentic Workflow, not a fourth approach. The approaches hold different assets with different neutral portfolios, so differences between them cannot be attributed to the forecasting method alone.</p>

<h2>2. Headline results</h2>
${tbl(['Series', 'Net CER', 'Ann. excess', 'Volatility', 'Sharpe', 'Worst fall', 'Cumulative', 'Turnover'], metricRows)}
<p>Net CER is the primary metric: the guaranteed yearly return above cash a risk-averse investor would accept instead of the strategy, after costs. ${esc(D.notes.finding || '')}</p>
<h3>Primary contrasts</h3>
${tbl(['Comparison', 'Net CER difference', '95% interval', 'p'], (D.dev.primary_contrasts.items || []).map(c => [esc(`${SHORT[c.a]} vs ${SHORT[c.b]}`), c.computed ? pts(c.cer_difference, 2) : 'not computed', c.ci95 ? `[${pts(c.ci95[0], 2)}, ${pts(c.ci95[1], 2)}]` : '—', c.p == null ? '—' : num(c.p, 3)]))}

<h2>3. How a decision is made</h2>
<p>Each approach keeps its own native pipeline. Historical data → signal generation → forecasting → portfolio allocation → trades and returns → performance evaluation.</p>
<ul>${['det', 'jev', 'rag'].map(k => `<li><b>${esc(SHORT[k])}</b>: ${(D.pipeline ? D.pipeline.stages[k] : []).map(x => esc(x.name)).join(' → ')}</li>`).join('')}</ul>
<p>The dashboard steps through every development month with the genuine archived values at each stage. Those values are exported in <code>data/signals_and_forecasts.csv</code> and <code>data/portfolio_weights.csv</code>. Causal RAG has no genuine development outputs, so no values are shown for it.</p>

<h2>4. Portfolio integrity audit</h2>
<p>${esc(D.audit.verdict)} Every monthly return was rebuilt independently from the raw prices; the largest absolute difference was ${D.audit.max_abs_diff_net_return.toExponential(2)}. The two working approaches' monthly net returns correlate at ${corr3(D.audit.corr_monthly_net)}, and their signal-free portfolios at ${corr3(D.audit.corr_own_mixes)}.</p>

<h2>5. Signal value-added</h2>
<p>Each approach was run again with its forecasting signal switched off and everything else — assets, starting weights, dates, prices, costs — held fixed.</p>
${tbl(['Approach', 'With signals', 'Without signals', 'Difference', '95% interval', 'p'], Object.entries(SV.systems).map(([k, v]) =>
  [esc(SHORT[k]), pct(v.with.cer, 2), pct(v.without.cer, 2), pts(v.value.cer_difference, 2), `[${pts(v.value.ci95[0], 2)}, ${pts(v.value.ci95[1], 2)}]`, num(v.value.p, 3)]))}
<p>Neither interval excludes zero. ${SV.influential_month ? esc(`One month, ${monthLabel(SV.influential_month.decision_month)}, carries most of JEV's signal contribution; removing it moves JEV's incremental net CER from `) + pts(SV.influential_month.value_with, 2) + ' to ' + pts(SV.influential_month.value_without, 2) + '.' : ''}</p>

<h2>6. Forecast-to-allocation sensitivity</h2>
<p>Each approach's view was rescaled at the single point where a number enters its allocator, adjusted = prior + λ × (original − prior), for λ in 0, 0.5, 1 and 2. Nothing else changed.</p>
${tbl(['Approach · scenario', 'Position change', 'Net CER', 'Volatility', 'Turnover', 'Cost', 'Limit binds', 'Net CER vs 1×'], senRows)}
<p>Where each signal is lost: the Deterministic view is shrunk inside Black–Litterman, whose posterior keeps ${M ? (M.systems.det.posterior_keeps * 100).toFixed(1) : ''}% of it; JEV's allocator passes its view through in full and its cap never binds, but the view is already small when it arrives; the Agent Committee is the one architecture where the position limit does the attenuating.</p>
<p>The ${M ? corr3(M.similarity.corr_1x) : ''} correlation between the Deterministic model and JEV is baseline exposure rather than forecast agreement: with both signals switched off they correlate at ${M ? corr3(M.similarity.corr_0x) : ''}, while the parts their signals contribute correlate at ${M ? corr3(M.similarity.corr_signal_parts) : ''}.</p>

<h2>7. Within-approach experiments</h2>
${tbl(['Approach', 'Experiment', 'Status', 'Result'], (D.experiments.groups || []).flatMap(g => [].concat(g.base ? [g.base] : [], g.variants || []).map(x =>
  [esc(SHORT[g.approach] || g.approach), esc(x.name), esc(STATUS[x.status] ? STATUS[x.status][2] : x.status), esc((x.result && x.result.headline) || '—')])))}

<h2>8. Causal RAG status</h2>
<p><b>${esc(D.ap3_exploratory.label)}.</b> ${D.ap3_exploratory.months_done} of ${D.ap3_exploratory.months_needed} agent months have been run. Both pre-registered reliability gates fail, so no backtest result exists and none is shown or exported. ${esc(D.ap3_exploratory.why || '')}</p>
<ul>${(D.sensitivity.ap3.blockers || []).map(b => `<li>${esc(b)}</li>`).join('')}</ul>

<h2>9. Limitations</h2>
<ul>${(D.notes.cannot || []).map(t => `<li>${esc(t)}</li>`).join('')}</ul>
${(M && M.limitations ? '' : '')}

<h2>10. Appendix</h2>
${apx}
<h3>Methodology settings</h3>
${tbl(['Setting', 'Value', 'Status'], (D.methodology.settings || []).map(x => [esc(x.name), esc(x.value), esc(SETTING[x.status][2])]))}
<h3>Validation gates</h3>
${tbl(['Check'].concat(D.validation.columns.map(k => SHORT[k])), (D.validation.gates || []).map(g => [esc(g.name)].concat(D.validation.columns.map(k => esc(GATE[g.cells[k].status][2])))))}
<h3>Glossary</h3><ul>${Object.keys(GLOSSARY).sort().map(k => `<li>${esc(GLOSSARY[k])}</li>`).join('')}</ul>
</body></html>`;
  }

  function manifest(tables) {
    const X = D.export;
    return JSON.stringify({
      package: X.zip_name,
      generated_at_utc: new Date().toISOString(),
      dashboard: { schema: D.build.dashboard_schema, data_generated_at_utc: D.build.generated_at_utc },
      source: { repository: D.build.repository, branch: D.build.branch, commit_at_build: D.build.git_commit_at_build,
                commit_note: D.build.git_commit_note, release_manifest_sha256: D.build.release_manifest_sha256 },
      windows: { training: D.windows.training, development: D.windows.development,
                 historical_test: D.windows.historical_test, historical_test_status: D.windows.historical_test_status },
      approaches: D.systems.map(s => ({ key: s.key, name: s.name, universe: s.universe, role: s.role,
        has_development_results: !!(s.key === 'rag' ? ragSeries() : S(s.key)),
        ...(s.key === 'rag' && ragSeries() ? { validated: false, designation: D.ap3_exploratory.label } : {}) })),
      variants: D.variants.map(s => ({ key: s.key, name: s.name, role: s.role, has_development_results: !!S(s.key) })),
      included_experiments: (D.experiments.groups || []).flatMap(g => [].concat(g.base ? [g.base] : [], g.variants || []).map(x => ({ approach: SHORT[g.approach] || g.approach, experiment: x.name, status: x.status }))),
      analyses_included: ['Portfolio integrity audit', 'Signal value-added', 'Forecast-to-allocation sensitivity',
                          'Within-approach experiments', 'Causal RAG status'],
      validation_status: { decision: D.validation.decision,
        causal_rag: { label: D.ap3_exploratory.label, months_done: D.ap3_exploratory.months_done,
                      months_needed: D.ap3_exploratory.months_needed, gates_failed: Object.keys(D.ap3_exploratory.gates_failed || {}) },
        statistical_note: 'No difference reported in this package is statistically clear. Every interval includes zero.' },
      report_format: X.report_format, report_format_note: X.report_format_note,
      files: Object.keys(tables).concat(['README.txt', 'MANIFEST.json', 'report/Research_Report.html', 'appendix/appendix.html', 'data/dashboard.json']).sort(),
      unavailable_or_excluded: X.excluded,
      limitations: D.notes.cannot || [],
    }, null, 1);
  }

  const readme = () => `Protofin — BNY Capstone dashboard content export
================================================

Package: ${D.export.zip_name}
Generated: ${new Date().toISOString()}
Source: ${D.build.repository}, branch ${D.build.branch}, commit ${D.build.git_commit_at_build}

What is in here
---------------
report/Research_Report.html   The complete research report. Open it in any browser; print to PDF if you need one.
appendix/appendix.html        The full appendix on its own.
appendix/appendix_index.csv   Every appendix entry, its category, and where the underlying data lives.
data/dashboard.json           The entire dashboard dataset, exactly as the page reads it.
data/*.csv                    Performance metrics, monthly returns, portfolio weights, signals and forecasts,
                              sensitivity scenarios, within-approach experiments, reliability and status.
MANIFEST.json                 Versions, source commit, included experiments, validation status and exclusions.

Why HTML and not PDF
--------------------
${D.export.report_format_note}

What is NOT in here
-------------------
${D.export.excluded.map(x => '- ' + x).join('\n')}

Reading the numbers
-------------------
These are development-window diagnostics (${devSpan()}), not confirmatory results. No difference in this
package is statistically clear: every interval includes zero. The approaches hold different assets with
different neutral portfolios, so differences between them are not attributable to the forecasting method alone.
`;

  let downloading = false;
  async function downloadContent(btn) {
    if (downloading || !D) return;
    downloading = true;
    const label = btn ? btn.querySelector('.dl-t') : null;
    const was = label ? label.textContent : '';
    if (label) label.textContent = 'Preparing…';
    if (btn) btn.disabled = true;
    try {
      const tables = exportTables();
      const files = [
        { path: 'README.txt', data: readme() },
        { path: 'report/Research_Report.html', data: reportHtml(false) },
        { path: 'appendix/appendix.html', data: reportHtml(true) },
        { path: 'data/dashboard.json', data: JSON.stringify(D) },
        ...Object.entries(tables).map(([path, data]) => ({ path, data })),
      ];
      files.push({ path: 'MANIFEST.json', data: manifest(tables) });
      files.sort((a, b) => a.path.localeCompare(b.path));
      const blob = await makeZip(files);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = D.export.zip_name; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      if (label) label.textContent = 'Downloaded';
      window.__protofinLastExport = { files: files.map(f => f.path), bytes: blob.size };
      setTimeout(() => { if (label) label.textContent = was; }, 2500);
    } catch (e) {
      console.error(e);
      if (label) label.textContent = 'Download failed';
      setTimeout(() => { if (label) label.textContent = was; }, 3000);
    } finally { downloading = false; if (btn) btn.disabled = false; }
  }



  // ---------------------------------------------------------------- Historical Backtest Replay
  // Playback of committed historical artifacts. Nothing is computed live, no model is called, and a lane with no
  // genuine output for a month shows that rather than animating one. The running metrics are recomputed from the
  // same committed monthly series the rest of the dashboard uses; a test checks the end state reproduces it.
  const RP = {
    i: 0,            // index into the development months
    stage: 0,        // 0..5 within the month
    playing: false,
    speed: 1,
    mode: 'auto',    // 'auto' plays stages then advances; 'step' waits for the presenter
    timer: null,
    reduced: false,
  };
  const RP_STAGE_MS = 700;   // at 1x; one stage per tick
  const RSTAGES = ['data', 'signal', 'forecast', 'alloc', 'trade', 'eval'];
  const RSHORT = { data: 'Data', signal: 'Signal', forecast: 'Forecast', alloc: 'Allocation', trade: 'Trades', eval: 'Result' };
  const LANES = ['det', 'jev', 'rag'];

  const costBp = x => x == null ? '—' : (Math.abs(x) * 1e4).toFixed(2) + ' bp';
  const rpMonths = () => (D.pipeline ? D.pipeline.months : []);
  const rpMonth = () => rpMonths()[RP.i];
  const prefersReduced = () => RP.reduced || matchMedia('(prefers-reduced-motion: reduce)').matches;

  // net CER to date, from the committed monthly series (same definition as the frozen evaluator)
  function cerTo(series, n) {
    const x = series.slice(0, n + 1);
    if (x.length < 2) return null;
    const m = x.reduce((a, b) => a + b, 0) / x.length;
    const v = x.reduce((a, b) => a + (b - m) * (b - m), 0) / (x.length - 1);
    return 12 * (m - 1.25 * v);
  }
  function ddTo(wealth, n) {
    let peak = -Infinity, dd = 0;
    for (let i = 0; i <= n; i++) { peak = Math.max(peak, wealth[i]); dd = Math.min(dd, wealth[i] / peak - 1); }
    return dd;
  }

  // What each lane has for the month in play. A lane with nothing returns {pending:true} and never animates values.
  function laneData(k, m) {
    const P = D.pipeline;
    const v = (P[k] || {})[m];
    return v ? { v, explor: k === 'rag' } : { pending: true };
  }

  function rpStageValue(k, stage, v) {
    // One headline number per stage: what this stage produced, in its own units.
    if (k === 'det') {
      if (stage === 'data') return [`${v.n_macro_available} of 8 releases`, 'available at the decision date'];
      if (stage === 'signal') { const b = v.surprises.reduce((a, x) => Math.abs(x.z) > Math.abs(a.z) ? x : a, v.surprises[0]);
        return [`${b.label} ${sgn(b.z, Math.abs(b.z).toFixed(2))} σ`, 'largest standardised surprise']; }
      if (stage === 'forecast') return [bp(v.forecast.SPY, 1) + ' stocks', v.fit.intercept_only ? 'intercept only: the training mean' : `ridge, penalty ${v.fit.alpha}`];
      if (stage === 'alloc') return [bp(v.posterior.SPY, 1) + ' posterior', `view ${bp(v.forecast.SPY, 1)}, prior ${bp(v.prior.SPY, 1)}`];
      if (stage === 'trade') return [ppw(v.turnover, 2) + ' traded', `cost ${costBp(v.cost)}`];
      return [pct(v.net, 2), 'net return above cash'];
    }
    if (k === 'rag') {
      if (stage === 'data') return [`${(v.triggers || []).length} triggers`, `knowledge graph vintage ${esc(String(v.graph_vintage ?? '—'))}`];
      if (stage === 'signal') { const c = v.status_counts || {};
        return [`${v.n_hypotheses} hypotheses`, `${c.Supported || 0} supported · ${c.Contradicted || 0} contradicted · ${c.Insufficient || 0} insufficient`]; }
      if (stage === 'forecast') return [bp(v.forecast.SPY, 1) + ' stocks', v.fit.intercept_only ? 'intercept only: the training mean' : `ridge on the encoded assessments, penalty ${v.fit.alpha}`];
      if (stage === 'alloc') return [bp(v.posterior.SPY, 1) + ' posterior', `view ${bp(v.forecast.SPY, 1)}, prior ${bp(v.prior.SPY, 1)}`];
      if (stage === 'trade') return [ppw(v.turnover, 2) + ' traded', `cost ${costBp(v.cost)}`];
      return [pct(v.net, 2), 'net return above cash'];
    }
    if (stage === 'data') return [esc(v.regime || '—') + ' regime', 'context at the cut-off'];
    if (stage === 'signal') return [esc(v.choice_label), `confidence ${num(v.confidence, 2)}`];
    if (stage === 'forecast') return [num(v.weighted_offset, 2) + ' pts', `offset ${num(v.offset_original, 2)} × confidence`];
    if (stage === 'alloc') return [num(v.edge, 2) + ' pts edge', `base ${num(v.base_edge, 2)} + signal ${num(v.weighted_offset, 2)}`];
    if (stage === 'trade') return [ppw(v.turnover, 2) + ' traded', `cost ${costBp(v.cost)}`];
    return [pct(v.net, 2), 'net return above cash'];
  }

  function rpWeights(k, v, reached) {
    const A = k === 'jev' ? ['SPY', 'TLT'] : ['SPY', 'IEF', 'LQD'];
    if (!reached) return `<div class="rw-wait">${A.map(() => '<span></span>').join('')}</div>`;
    return `<div class="rw">${A.map(a => `<span class="b" style="background:${assetColor(a)};flex:${Math.max(0.0001, v.weights[a])} 1 0"><b>${(v.weights[a] * 100).toFixed(0)}</b></span>`).join('')}</div>
      <div class="rw-key">${A.map(a => `<span><i style="background:${assetColor(a)}"></i>${esc(PLAIN[a] || a)}</span>`).join('')}</div>`;
  }

  function laneHtml(k) {
    const m = rpMonth(), st = RP.stage, d = laneData(k, m);
    const nm = D.systems.find(x => x.key === k) || { short: SHORT[k] };
    const stages = (D.pipeline.stages[k] || []);
    const head = `<div class="rl-h">${badge(k)}<div><b>${esc(nm.short)}${k === 'rag' ? xtag() : ''}</b><span class="sub">${esc((nm.universe || []).map(a => PLAIN[a] || a).join(' · '))}</span></div></div>`;
    if (d.pending) {
      const X = D.ap3_exploratory;
      return `<section class="rlane pending" style="--c:var(${VAR[k]})" aria-label="${esc(nm.short)}">
        ${head}
        <div class="rl-badge">${icon('hourglass')}${esc(X.label)}</div>
        <ol class="rl-stages">${stages.map((x, i) => `<li class="idle"><span class="n">${i + 1}</span><span class="t">${esc(RSHORT[x.id])}</span><span class="v">—</span></li>`).join('')}</ol>
        <div class="rl-pend">
          <p>No genuine agent output exists for <b>${esc(monthLabel(m))}</b>, so nothing is replayed in this lane.</p>
          <ul class="sub">
            <li>${X.months_done} of ${X.months_needed} agent months have been run, and they fall in the ${esc(monthLabel(D.windows.training[0]))}–${esc(monthLabel(D.windows.training[1]))} training window, not these development months.</li>
            <li>Both pre-registered reliability gates fail: ${Object.entries(X.gates_failed).map(([g, c]) => `${g} (${Object.entries(c).map(([n, val]) => `${esc(n.replace(/_/g, ' '))} ${typeof val === 'number' ? (val < 1 && val > 0 ? val.toFixed(4) : val) : esc(String(val))}`).join(', ')})`).join('; ')}.</li>
            <li>This lane is built to take a genuine replay the moment those months exist and the gates are re-scored.</li>
          </ul>
          <a class="go" href="#causal-rag">Causal RAG status ${icon('arrow')}</a>
        </div>
      </section>`;
    }
    const v = d.v;
    return `<section class="rlane${d.explor ? ' explor' : ''}" style="--c:var(${VAR[k]})" aria-label="${esc(nm.short)}">
      ${head}
      <ol class="rl-stages">${stages.map((x, i) => {
        const cls = i < st ? 'done' : i === st ? 'live' : 'idle';
        const [val, note] = i <= st ? rpStageValue(k, x.id, v) : ['—', ''];
        return `<li class="${cls}"><span class="n">${i < st ? '✓' : i + 1}</span><span class="t">${esc(RSHORT[x.id])}</span>
          <span class="v">${i <= st ? val : '<em>waiting</em>'}</span>${i <= st && note ? `<small>${note}</small>` : ''}</li>`;
      }).join('')}</ol>
      <div class="rl-out">
        <div class="rl-w"><span class="l">Portfolio${st >= 3 ? '' : ' <em>(pending allocation)</em>'}</span>${rpWeights(k, v, st >= 3)}</div>
        <div class="rl-r"><span class="l">This month's result</span>
          ${st >= 5 ? `<b class="num ${v.net >= 0 ? 'up' : 'down'}">${pct(v.net, 2)}</b><small>held ${esc(v.entry)} → ${esc(v.exit)}</small>`
                    : `<b class="num wait">—</b><small>${st >= 4 ? 'holding period not finished' : 'no trade yet'}</small>`}</div>
      </div>
    </section>`;
  }

  // the committed per-month net excess return series for a lane, in replay order
  const rpExcess = k => { const P = D.pipeline[k];
    return P ? rpMonths().map(m => (P[m] || {}).net) : null; };
  // Causal RAG never joins dev.series: its curve comes only from the labelled exploratory block.
  const rpSeries = k => { if (k !== 'rag') return S(k); return ragSeries(); };

  function rpRunning() {
    const n = RP.i, done = RP.stage >= 5;      // the month's result is known only once the holding period has run
    const upto = done ? n : n - 1;
    const row = k => {
      const S2 = rpSeries(k);
      if (!S2) return `<tr><th scope="row">${badge(k)}${esc(SHORT[k])}</th><td colspan="4" class="na">no results yet</td></tr>`;
      if (upto < 0) return `<tr><th scope="row">${badge(k)}${esc(SHORT[k])}</th><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">—</td></tr>`;
      // growth and drawdown run on the committed total-return wealth; net CER is defined on net EXCESS
      // returns, so it is taken from the pipeline's own per-month net excess series, not from wealth.
      const w = S2.wealth, x = rpExcess(k);
      return `<tr><th scope="row">${badge(k)}${esc(SHORT[k])}${k === 'rag' ? xtag() : ''}</th>
        <td class="num">$${w[upto].toFixed(3)}</td>
        <td class="num">${pct(w[upto] - 1, 1)}</td>
        <td class="num">${upto >= 1 && x ? pct(cerTo(x, upto), 2) : '—'}</td>
        <td class="num">${pct(ddTo(w, upto), 1)}</td></tr>`;
    };
    return `<div class="fas-scroll"><table class="cmp rp-run"><thead><tr><th scope="col">To ${upto >= 0 ? esc(monthLabel(rpMonths()[upto])) : '—'}</th>
        <th scope="col">$1 grew to</th><th scope="col">Cumulative</th><th scope="col">Net CER ${tip('cer')}</th><th scope="col">Worst fall</th></tr></thead>
      <tbody>${LANES.map(row).join('')}</tbody></table></div>
      <p class="sub">Running figures, computed only from months whose holding period has finished. They are <b>to date</b>, not the full-sample result — those appear in the fixed summary below.</p>`;
  }

  function rpFinal() {
    const row = k => { const S2 = rpSeries(k);
      if (!S2) return `<tr><th scope="row">${badge(k)}${esc(SHORT[k])}</th><td colspan="4" class="na">no results yet</td></tr>`;
      const m = S2.metrics;
      return `<tr class="${k === 'rag' ? 'xrow' : ''}"><th scope="row">${badge(k)}${esc(SHORT[k])}${k === 'rag' ? xtag() : ''}</th>
        <td class="num">${pct(m.cer, 2)}</td><td class="num">${pct(m.cumulative ?? m.cumulative_return, 1)}</td>
        <td class="num">${pct(m.volatility, 1)}</td><td class="num">${pct(m.drawdown ?? m.max_drawdown, 1)}</td></tr>`; };
    return `<div class="fas-scroll"><table class="cmp"><thead><tr><th scope="col">Full development sample · ${esc(devSpan())}</th>
        <th scope="col">Net CER</th><th scope="col">Cumulative</th><th scope="col">Volatility</th><th scope="col">Worst fall</th></tr></thead>
      <tbody>${LANES.map(row).join('')}</tbody></table></div>`;
  }

  function viewReplay() {
    if (!D.pipeline) { app.innerHTML = '<div class="wrap"><p class="sub">The replay data is not in this build.</p></div>'; return; }
    const months = rpMonths(), m = rpMonth(), pos = RP.i / Math.max(1, months.length - 1);
    const stageName = (D.pipeline.stages.det[RP.stage] || {}).name || '';
    app.innerHTML = `<div class="wrap rp">
      <section class="rp-head">
        <div><div class="phead"><h1>Historical Backtest Replay</h1><span class="chip plain">${icon('refresh')}Playback of recorded results — no model runs</span></div>
          <p class="lede">Press Play and watch all three approaches work through the same ${months.length} development months, stage by stage, on their own native pipelines.</p></div>
      </section>

      <section class="panel rp-ctl" aria-label="Replay controls">
        <div class="rp-now">
          <div><span class="l">Decision month</span><b id="rp-m">${esc(monthLabel(m))}</b></div>
          <div><span class="l">Stage</span><b id="rp-s">${RP.stage + 1} of 6 · ${esc(stageName)}</b></div>
          <div><span class="l">Progress</span><b id="rp-p">${RP.i + 1} / ${months.length} months</b></div>
        </div>
        <div class="rp-buttons">
          <button type="button" id="rp-play" class="pbtn primary">${icon(RP.playing ? 'pause' : 'arrow')}<span>${RP.playing ? 'Pause' : 'Play Backtest'}</span></button>
          <button type="button" id="rp-restart" class="pbtn">${icon('refresh')}Restart</button>
          <span class="rp-gap"></span>
          <button type="button" class="pbtn" data-rp="pm" title="Previous month">${icon('chev', 'flip')}Month</button>
          <button type="button" class="pbtn" data-rp="ps" title="Previous stage">${icon('chev', 'flip')}Stage</button>
          <button type="button" class="pbtn" data-rp="ns" title="Next stage">Stage${icon('chev')}</button>
          <button type="button" class="pbtn" data-rp="nm" title="Next month">Month${icon('chev')}</button>
        </div>
        <div class="rp-opts">
          <div class="seg" role="group" aria-label="Replay mode">
            <button type="button" data-mode="auto" aria-pressed="${RP.mode === 'auto'}">Automatic</button>
            <button type="button" data-mode="step" aria-pressed="${RP.mode === 'step'}">Step-by-step</button>
          </div>
          <div class="seg" role="group" aria-label="Replay speed">${[0.5, 1, 2, 4].map(x => `<button type="button" data-sp="${x}" aria-pressed="${RP.speed === x}">${x}×</button>`).join('')}</div>
          <label class="rp-rm"><input type="checkbox" id="rp-reduced"${prefersReduced() ? ' checked' : ''}> Reduce motion</label>
        </div>
        <label class="rp-slider"><span class="sr">Timeline</span>
          <input type="range" id="rp-range" min="0" max="${months.length - 1}" value="${RP.i}" step="1" aria-valuetext="${esc(monthLabel(m))}">
          <span class="rp-ends"><span>${esc(monthLabel(months[0]))}</span><span>${esc(monthLabel(months[months.length - 1]))}</span></span>
        </label>
        <div class="rp-prog" aria-hidden="true"><i style="width:${(pos * 100).toFixed(2)}%"></i></div>
      </section>

      <section class="rlanes" id="rp-lanes">${LANES.map(laneHtml).join('')}</section>

      <section class="panel">
        <div class="phead"><h2>Growth of $1, as the replay runs</h2><span class="sub" id="rp-upto"></span></div>
        <div class="legend" id="lg-rp"></div>
        <div class="chartbox sm"><canvas id="c-rp" aria-label="Growth of one dollar for each approach, revealed month by month"></canvas></div>
      </section>

      <section class="grid2">
        <div class="panel"><h2>Running result, to date</h2><div id="rp-running">${rpRunning()}</div></div>
        <div class="panel"><h2>Fixed summary · full development sample</h2>${rpFinal()}
          <p class="sub">These never change during playback. They describe all ${months.length} months, whatever month the replay is on.</p></div>
      </section>

      <section class="panel"><h2>What is being replayed</h2>
        <div class="grid3">
          ${LANES.map(k => { const src = (D.pipeline.sources || {})[k];
            return `<div class="rsrc" style="--c:var(${VAR[k]})"><b>${badge(k)}${esc(SHORT[k])}</b>
              ${src ? `<ul class="sub">${src.map(f => `<li><code>${esc(f)}</code></li>`).join('')}</ul>`
                    : `<p class="sub">Nothing to replay: no genuine development-window output exists. The lane shows its real architecture and the recorded reliability outcome only.</p>`}</div>`; }).join('')}
        </div>
        <p class="sub">Every value in the lanes is read from these committed artifacts. No model is called, no inference happens, and no month is interpolated or inferred.</p>
      </section>
    </div>`;
    rpDrawChart();
    rpWire();
  }

  function rpDrawChart() {
    const months = rpMonths(), upto = RP.stage >= 5 ? RP.i : RP.i - 1;
    const cut = i => i <= upto;
    const lines = D.systems.filter(x => rpSeries(x.key)).map(x => ({
      label: x.key === 'det' ? 'Deterministic (baseline)' : x.key === 'rag' ? x.short + ' (exploratory)' : x.short,
      data: rpSeries(x.key).wealth.map((w, i) => (cut(i) ? w : null)), color: color(x.key),
      spanGaps: false, ...(x.key === 'rag' ? { dash: [5, 4] } : {}) }));
    lineChart('c-rp', 'lg-rp', months, lines, FMT_WEALTH);
    const u = document.getElementById('rp-upto');
    if (u) u.textContent = upto >= 0 ? `revealed to ${monthLabel(months[upto])}` : 'nothing revealed yet';
  }

  function rpApply() {
    // Re-render only what changes, so playback stays smooth and the chart is not rebuilt every stage.
    const months = rpMonths(), m = rpMonth();
    const lanes = document.getElementById('rp-lanes');
    if (lanes) lanes.innerHTML = LANES.map(laneHtml).join('');
    const set = (id, t) => { const e = document.getElementById(id); if (e) e.textContent = t; };
    set('rp-m', monthLabel(m));
    set('rp-s', `${RP.stage + 1} of 6 · ${(D.pipeline.stages.det[RP.stage] || {}).name || ''}`);
    set('rp-p', `${RP.i + 1} / ${months.length} months`);
    const r = document.getElementById('rp-range'); if (r) { r.value = String(RP.i); r.setAttribute('aria-valuetext', monthLabel(m)); }
    const pr = document.querySelector('.rp-prog i'); if (pr) pr.style.width = (RP.i / Math.max(1, months.length - 1) * 100).toFixed(2) + '%';
    const run = document.getElementById('rp-running'); if (run) run.innerHTML = rpRunning();
    rpDrawChart();
  }

  function rpTick() {
    if (!RP.playing) return;
    if (RP.stage < 5) RP.stage++;
    else if (RP.i < rpMonths().length - 1) { RP.i++; RP.stage = 0; }
    else { rpPause(); rpApply(); return; }
    rpApply();
    rpSchedule();
  }
  function rpSchedule() {
    clearTimeout(RP.timer);
    if (!RP.playing) return;
    const base = prefersReduced() ? RP_STAGE_MS * 0.55 : RP_STAGE_MS;
    RP.timer = setTimeout(rpTick, Math.max(90, base / RP.speed));
  }
  function rpPlay() { if (RP.i === rpMonths().length - 1 && RP.stage >= 5) { RP.i = 0; RP.stage = 0; } RP.playing = true; rpPlayBtn(); rpSchedule(); }
  function rpPause() { RP.playing = false; clearTimeout(RP.timer); rpPlayBtn(); }
  function rpPlayBtn() {
    const b = document.getElementById('rp-play');
    if (!b) return;
    b.innerHTML = `${icon(RP.playing ? 'pause' : 'arrow')}<span>${RP.playing ? 'Pause' : 'Play Backtest'}</span>`;
    b.setAttribute('aria-pressed', String(RP.playing));
  }
  const rpStep = d => {
    const n = rpMonths().length;
    let f = RP.i * 6 + RP.stage + d;
    f = Math.max(0, Math.min(n * 6 - 1, f));
    RP.i = Math.floor(f / 6); RP.stage = f % 6;
  };

  function rpWire() {
    const on = (sel, ev, fn) => document.querySelectorAll(sel).forEach(e => e.addEventListener(ev, fn));
    const play = document.getElementById('rp-play');
    if (play) play.addEventListener('click', () => { RP.playing ? rpPause() : rpPlay(); });
    const rs = document.getElementById('rp-restart');
    if (rs) rs.addEventListener('click', () => { rpPause(); RP.i = 0; RP.stage = 0; rpApply(); });
    on('[data-rp]', 'click', e => { rpPause();
      const a = e.currentTarget.dataset.rp;
      if (a === 'ns') rpStep(1); else if (a === 'ps') rpStep(-1);
      else if (a === 'nm') { RP.i = Math.min(rpMonths().length - 1, RP.i + 1); RP.stage = 0; }
      else { RP.i = Math.max(0, RP.i - 1); RP.stage = 0; }
      rpApply(); });
    on('[data-mode]', 'click', e => { RP.mode = e.currentTarget.dataset.mode;
      document.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === RP.mode)));
      if (RP.mode === 'step') rpPause(); });
    on('[data-sp]', 'click', e => { RP.speed = +e.currentTarget.dataset.sp;
      document.querySelectorAll('[data-sp]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.sp === RP.speed)));
      rpSchedule(); });
    const rng = document.getElementById('rp-range');
    if (rng) rng.addEventListener('input', () => { rpPause(); RP.i = +rng.value; RP.stage = 5; rpApply(); });
    const rm = document.getElementById('rp-reduced');
    if (rm) rm.addEventListener('change', () => { RP.reduced = rm.checked; document.body.classList.toggle('reduced', RP.reduced); rpSchedule(); });
    document.body.classList.toggle('reduced', prefersReduced());
    rpPlayBtn();
  }


  function route() {
    if (!D) return;
    if (typeof rpPause === 'function') rpPause();
    killCharts();
    chartDefaults();
    let h = (location.hash || '#overview').slice(1);
    const qi = h.indexOf('?');
    const query = qi >= 0 ? new URLSearchParams(h.slice(qi + 1)) : null;
    if (qi >= 0) h = h.slice(0, qi);
    if (h === 'method' || h === 'timeline' || h === 'methodology') h = 'appendix';
    if (h === 'approaches') h = 'deterministic';
    const key = ROUTES[h];
    const TOP = ['overview', 'replay', 'pipeline', 'comparison', 'signal-value', 'sensitivity', 'experiments', 'causal-rag', 'appendix'];
    // the per-approach detail pages are reached from Comparison; they light its tab
    const view = key ? (key === 'com' ? 'experiments' : key === 'rag' ? 'causal-rag' : 'comparison')
                     : (TOP.includes(h) ? h : 'overview');
    if (query && query.get('c')) apxCat = query.get('c');
    document.querySelectorAll('header nav a').forEach(a => { if (a.dataset.route === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    try {
      if (key) viewApproach(key);
      else if (view === 'replay') viewReplay();
      else if (view === 'pipeline') viewPipeline();
      else if (view === 'comparison') viewComparison();
      else if (view === 'experiments') viewExperiments();
      else if (view === 'signal-value') viewSignalValue();
      else if (view === 'sensitivity') viewSensitivity();
      else if (view === 'appendix') viewAppendix();
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
  const dlBtn = document.getElementById('dl');
  if (dlBtn) dlBtn.addEventListener('click', () => downloadContent(dlBtn));
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
