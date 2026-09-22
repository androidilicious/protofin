// Browser pipeline: a saved run (built by scripts/build_signals.py) -> committee -> parse -> allocate.
// Committee = economist and risk manager as INDEPENDENT calls (parallel for saved gpt-4o runs; on one
// local GPU they execute back to back but still never see each other), then a CIO synthesis.
// Providers: 'saved' replays the stored replies (no key, no network); 'browser' runs a small open
// model locally with WebLLM (WebGPU). No API keys anywhere.
import { allocate } from './allocation.js';

export const DOWNGRADE = { High: 'Medium', Medium: 'Low', Low: 'Low' };

export const DEFAULTS = { provider: 'saved', browserModel: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC', run: 'latest' };

export function settingsFromUrl(defaults = DEFAULTS) {
  const q = new URLSearchParams(location.search);
  const s = { ...defaults };
  for (const k of ['provider', 'browserModel', 'run']) if (q.get(k)) s[k] = q.get(k);
  if (!['saved', 'browser'].includes(s.provider)) s.provider = 'saved';
  return s;
}
export function loadSettings() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('protofin.settings') || '{}'); } catch (e) { /* ignore */ }
  return settingsFromUrl({ ...DEFAULTS, ...saved });
}
export function saveSettings(s) { try { localStorage.setItem('protofin.settings', JSON.stringify(s)); } catch (e) { /* ignore */ } }

// ---------- saved runs ----------
export async function listRuns() {
  try { const r = await fetch('./data/runs/index.json', { cache: 'no-store' }); return r.ok ? await r.json() : []; } catch (e) { return []; }
}
export async function loadRun(id) {
  const path = id && id !== 'latest' ? `./data/runs/${id}.json` : './data/signals.json';
  const r = await fetch(path, { cache: 'no-store' });
  if (!r.ok) throw new Error(`could not load run ${id}`);
  return await r.json();
}

// ---------- in-browser model ----------
let webllmEngine = null, webllmModelLoaded = null;
const SYSTEM_STRICT = 'Answer ONLY with the labelled lines requested, in that order, nothing before or after. Lines ending in _Return_Percent contain only a number (example: SPY_Expected_Return_Percent: 6.5). A Confidence line is one word: High, Medium or Low. No markdown.';
export async function ensureEngine(browserModel, onProgress) {
  if (!('gpu' in navigator)) throw new Error('This browser has no WebGPU; the in-browser model needs a recent Chrome or Edge with a GPU.');
  const { CreateMLCEngine } = await import('https://esm.run/@mlc-ai/web-llm');
  if (!webllmEngine || webllmModelLoaded !== browserModel) {
    webllmEngine = await CreateMLCEngine(browserModel, { initProgressCallback: p => onProgress && onProgress(p.text) });
    webllmModelLoaded = browserModel;
  }
  return webllmEngine;
}
export async function browserCall(prompt, settings, onProgress) {
  const engine = await ensureEngine(settings.browserModel, onProgress);
  const r = await engine.chat.completions.create({ messages: [{ role: 'system', content: SYSTEM_STRICT }, { role: 'user', content: prompt }], temperature: 0, max_tokens: 300 });
  return r.choices?.[0]?.message?.content || '';
}

// ---------- parsing (mirrors committee.py) ----------
const clean = t => (t || '').replace(/\*\*|__|`/g, '');
const NUM = '([-+]?\\d+(?:\\.\\d+)?)';
function numberFor(text, stem, asset) {
  const pats = [
    new RegExp(stem + asset + '[_ ]?Return[_ ]?Percent\\s*[:=]?\\s*' + NUM, 'i'),
    new RegExp('^[^\\n]*' + asset + '[^\\n]*?(?:return|expect)[^\\n]*?' + NUM + '\\s*%', 'im'),
    new RegExp('^[^\\n]*' + asset + '[^\\n]*?(?:return|expect)[^\\n]*?[:=]\\s*' + NUM, 'im'),
    new RegExp('^[^\\n]*' + asset + '\\s*[:=]\\s*' + NUM + '\\s*%', 'im'),
  ];
  for (const p of pats) { const m = text.match(p); if (m) return parseFloat(m[1]); }
  return null;
}
export function parseView(raw, role) {
  const text = clean(raw);
  const label = role === 'economist' ? 'Economist[_ ]?View' : 'Risk[_ ]?View';
  const m = text.match(new RegExp(label + '\\s*:\\s*(.*)', 'i'));
  const view = m ? m[1].trim() : text.split('\n').filter(l => l && !/Return[_ ]?Percent/i.test(l)).join(' ').trim();
  const stem = role === 'economist' ? 'Economist[_ ]?' : 'Risk[_ ]?';
  return { text: view || '(no view text parsed)', spy: numberFor(text, stem, 'SPY'), tlt: numberFor(text, stem, 'TLT') };
}
export function parseCio(raw) {
  const text = clean(raw);
  const f = { cio: null, grounding: null, spy_q: null, tlt_q: null, confidence: null };
  for (const [label, key] of [['CIO[_ ]?Decision', 'cio'], ['Grounding[_ ]?Summary', 'grounding']]) {
    const m = text.match(new RegExp(label + '\\s*:\\s*(.*)', 'i')); if (m) f[key] = m[1].trim();
  }
  f.spy_q = numberFor(text, '(?:CIO[_ ]?)?', 'SPY'); f.tlt_q = numberFor(text, '(?:CIO[_ ]?)?', 'TLT');
  const c = text.match(/CIO[_ ]?Confidence\s*[:=]?\s*(High|Medium|Low)/i) || text.match(/confidence[^\n]{0,40}?\b(High|Medium|Low)\b/i);
  if (c) f.confidence = c[1][0].toUpperCase() + c[1].slice(1).toLowerCase();
  const problems = [];
  for (const k of ['spy_q', 'tlt_q']) {
    if (f[k] === null) problems.push(`${k} missing`);
    else if (f[k] < -50 || f[k] > 50) { problems.push(`${k}=${f[k]} outside plausible annual range`); f[k] = null; }
  }
  if (!f.confidence) problems.push('confidence missing or not High/Medium/Low');
  return { fields: f, problems };
}
// legacy single-reply format (older saved runs)
export function parseReply(raw) {
  const text = clean(raw);
  const grab = (label) => { const m = text.match(new RegExp(label + '\\s*(.*)', 'i')); return m ? m[1].trim() : null; };
  const { fields, problems } = parseCio(text);
  return { fields: { economist: grab('Economist:'), risk: grab('Risk[_ ]?Manager:'), ...fields }, problems };
}

// ---------- committee ----------
// onEvent(name, payload): 'stage1-start' | 'economist' | 'risk' | 'cio-start' | 'cio'
export async function runCommittee(run, settings, onEvent, onProgress) {
  const prompts = run.prompts;
  const t0 = performance.now();
  const timings = {};
  let econRaw, riskRaw, cioRaw, cioPrompt, parallel, source, model;
  if (settings.provider === 'browser') {
    model = settings.browserModel; source = 'in-browser (WebLLM); independent views executed back to back on one GPU';
    await ensureEngine(settings.browserModel, onProgress);
    onEvent && onEvent('stage1-start', { parallel: false });
    const call = async role => { const s = performance.now(); const out = await browserCall(prompts[role], settings, onProgress); timings[role + '_ms'] = Math.round(performance.now() - s); onEvent && onEvent(role, { raw: out, view: parseView(out, role) }); return out; };
    // Promise.all keeps the code shape of the parallel version; the engine serialises the two generations.
    [econRaw, riskRaw] = await Promise.all([call('economist'), call('risk')]);
    parallel = false;
  } else {
    const ref = run.reference_run;
    if (!ref) throw new Error('This run has no stored committee replies.');
    model = ref.model; source = `saved run from ${ref.generated_at}` + (ref.parallel ? ' (economist ∥ risk as concurrent API calls, then CIO)' : ' (legacy single reply)');
    if (!ref.economist_raw) {
      // legacy single-reply run
      onEvent && onEvent('stage1-start', { parallel: false, legacy: true });
      const p = parseReply(ref.raw);
      onEvent && onEvent('economist', { raw: ref.raw, view: { text: p.fields.economist || '(legacy run)', spy: null, tlt: null } });
      onEvent && onEvent('risk', { raw: ref.raw, view: { text: p.fields.risk || '(legacy run)', spy: null, tlt: null } });
      onEvent && onEvent('cio-start', {}); onEvent && onEvent('cio', { raw: ref.raw, fields: p.fields, problems: p.problems });
      return { legacy: true, cioRaw: ref.raw, fields: p.fields, problems: p.problems, timings: ref.timings || {}, parallel: false, model, source, econ: null, risk: null, cioPrompt: run.prompt };
    }
    parallel = !!ref.parallel;
    onEvent && onEvent('stage1-start', { parallel });
    Object.assign(timings, ref.timings || {});
    // replay the saved replies with their real relative timing (capped so the demo stays snappy)
    const scale = 0.35, cap = 4000;
    const replay = (role, raw) => new Promise(res => setTimeout(() => { onEvent && onEvent(role, { raw, view: parseView(raw, role) }); res(raw); }, Math.min(cap, (timings[role + '_ms'] || 1500) * scale)));
    [econRaw, riskRaw] = await Promise.all([replay('economist', ref.economist_raw), replay('risk', ref.risk_raw)]);
  }
  const econ = parseView(econRaw, 'economist'), risk = parseView(riskRaw, 'risk');
  cioPrompt = prompts.cio.replace('{ECONOMIST_VIEW}', econRaw.trim()).replace('{RISK_VIEW}', riskRaw.trim());
  onEvent && onEvent('cio-start', {});
  if (settings.provider === 'browser') {
    const s = performance.now(); cioRaw = await browserCall(cioPrompt, settings, onProgress); timings.cio_ms = Math.round(performance.now() - s);
  } else {
    cioRaw = run.reference_run.cio_raw;
    await new Promise(r => setTimeout(r, Math.min(3000, (timings.cio_ms || 2000) * 0.35)));
  }
  const { fields, problems } = parseCio(cioRaw);
  onEvent && onEvent('cio', { raw: cioRaw, fields, problems });
  timings.total_ms = timings.total_ms || Math.round(performance.now() - t0);
  return { econRaw, riskRaw, cioRaw, cioPrompt, econ, risk, fields, problems, timings, parallel, model, source };
}

// ---------- full run ----------
export async function runPipeline(run, settings, onProgress, onEvent) {
  if (!run.prompts && !run.reference_run) throw new Error('Run has no prompts.');
  const c = await runCommittee(run, settings, onEvent, onProgress);
  const ok = c.problems.length === 0;
  const rf = run.risk_free;
  const confidenceReported = c.fields.confidence || 'Low';
  const confidence = run.uncertainty_regime === 'elevated' ? DOWNGRADE[confidenceReported] : confidenceReported;
  const views = ok ? [c.fields.spy_q, c.fields.tlt_q] : null;
  const viewNote = ok ? `views applied as excess return over cash (${rf.toFixed(2)}%)` : `CIO reply rejected (${c.problems.join('; ')}); using equilibrium prior only`;
  const d = allocate(run.sigma, views, confidence, rf, null);
  const r2 = x => Math.round(x * 100) / 100, r1 = x => Math.round(x * 10) / 10;
  return {
    ...run,
    prototype_mode: true, cached: false, timestamp: new Date().toISOString(),
    model_used: c.model, model_source: c.source, llm_raw: c.cioRaw,
    economist_raw: c.econRaw, risk_raw: c.riskRaw, cio_raw: c.cioRaw, cio_prompt: c.cioPrompt,
    economist_q: c.econ ? [c.econ.spy, c.econ.tlt] : null, risk_q: c.risk ? [c.risk.spy, c.risk.tlt] : null,
    committee_timing: { ...c.timings, parallel: c.parallel },
    economist: (c.econ && c.econ.text) || c.fields.economist || '(no economist output parsed)',
    risk: (c.risk && c.risk.text) || c.fields.risk || '(no risk-manager output parsed)',
    cio: c.fields.cio || '(no CIO output parsed)', grounding: c.fields.grounding || '(no grounding summary parsed)',
    spy_q: c.fields.spy_q, tlt_q: c.fields.tlt_q, confidence, confidence_reported: confidenceReported,
    llm_parse_ok: ok, llm_problems: c.problems, view_note: viewNote,
    spy_q_excess: ok ? r2(c.fields.spy_q - rf) : null, tlt_q_excess: ok ? r2(c.fields.tlt_q - rf) : null,
    prior_spy: r2(d.pi[0] * 100), prior_tlt: r2(d.pi[1] * 100),
    posterior_spy: r2(d.er[0] * 100), posterior_tlt: r2(d.er[1] * 100),
    unconstrained_spy: r1(d.unconstrained[0] * 100), unconstrained_tlt: r1(d.unconstrained[1] * 100),
    target_spy: r1(d.target_spy * 100), target_tlt: r1((1 - d.target_spy) * 100),
    previous_spy: null, spy_weight: r1(d.target_spy * 100), tlt_weight: r1((1 - d.target_spy) * 100),
    trade_status: 'prototype mode: optimizer target applied directly',
  };
}
