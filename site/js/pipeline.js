// Browser pipeline: a saved run (built by scripts/build_signals.py) -> model reply -> parse -> allocate.
// Providers: 'saved' replays the committee reply stored with the run (no key, no network);
// 'browser' runs a small open model locally with WebLLM (WebGPU). No API keys anywhere.
import { allocate } from './allocation.js';

export const DOWNGRADE = { High: 'Medium', Medium: 'Low', Low: 'Low' };

export const DEFAULTS = {
  provider: 'saved',
  browserModel: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC',
  run: 'latest',
};

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
export function saveSettings(s) {
  try { localStorage.setItem('protofin.settings', JSON.stringify(s)); } catch (e) { /* ignore */ }
}

// ---------- saved runs ----------
export async function listRuns() {
  try {
    const r = await fetch('./data/runs/index.json', { cache: 'no-store' });
    if (!r.ok) return [];
    return await r.json();
  } catch (e) { return []; }
}
export async function loadRun(id) {
  const path = id && id !== 'latest' ? `./data/runs/${id}.json` : './data/signals.json';
  const r = await fetch(path, { cache: 'no-store' });
  if (!r.ok) throw new Error(`could not load run ${id}`);
  return await r.json();
}

// ---------- in-browser model ----------
let webllmEngine = null, webllmModelLoaded = null;
async function browserModel(prompt, { browserModel }, onProgress) {
  if (!('gpu' in navigator)) throw new Error('This browser has no WebGPU; the in-browser model needs a recent Chrome or Edge with a GPU.');
  const { CreateMLCEngine } = await import('https://esm.run/@mlc-ai/web-llm');
  if (!webllmEngine || webllmModelLoaded !== browserModel) {
    webllmEngine = await CreateMLCEngine(browserModel, { initProgressCallback: p => onProgress && onProgress(p.text) });
    webllmModelLoaded = browserModel;
  }
  const r = await webllmEngine.chat.completions.create({
    messages: [{ role: 'user', content: prompt }], temperature: 0, max_tokens: 400,
  });
  return r.choices?.[0]?.message?.content || '';
}

export async function callModel(run, settings, onProgress) {
  if (settings.provider === 'browser') {
    return { raw: await browserModel(run.prompt, settings, onProgress), model: settings.browserModel, source: 'in-browser (WebLLM, WebGPU), nothing leaves your machine' };
  }
  if (!run.reference_run) throw new Error('This run has no stored committee reply.');
  return { raw: run.reference_run.raw, model: run.reference_run.model, source: `saved run from ${run.reference_run.generated_at}` };
}

// ---------- parsing (mirrors server.parse_llm) ----------
export function parseReply(text) {
  const f = { economist: null, risk: null, cio: null, grounding: null, spy_q: null, tlt_q: null, confidence: null };
  const grab = (label, key) => { const m = text.match(new RegExp(label + '\\s*(.*)')); if (m) f[key] = m[1].trim(); };
  grab('Economist:', 'economist'); grab('Risk_Manager:', 'risk'); grab('CIO_Decision:', 'cio'); grab('Grounding_Summary:', 'grounding');
  for (const [label, key] of [['SPY_Expected_Return_Percent:', 'spy_q'], ['TLT_Expected_Return_Percent:', 'tlt_q']]) {
    const m = text.match(new RegExp(label + '\\s*([-+]?\\d+(?:\\.\\d+)?)'));
    if (m) f[key] = parseFloat(m[1]);
  }
  const c = text.match(/CIO_Confidence:\s*(High|Medium|Low)/i);
  if (c) f.confidence = c[1][0].toUpperCase() + c[1].slice(1).toLowerCase();
  const problems = [];
  for (const k of ['spy_q', 'tlt_q']) {
    if (f[k] === null) problems.push(`${k} missing`);
    else if (f[k] < -50 || f[k] > 50) { problems.push(`${k}=${f[k]} outside plausible annual range`); f[k] = null; }
  }
  if (!f.confidence) problems.push('confidence missing or not High/Medium/Low');
  return { fields: f, problems };
}

// ---------- full run ----------
export async function runPipeline(run, settings, onProgress) {
  const { raw, model, source } = await callModel(run, settings, onProgress);
  const { fields, problems } = parseReply(raw);
  const ok = problems.length === 0;
  const rf = run.risk_free;
  const confidenceReported = fields.confidence || 'Low';
  const confidence = run.uncertainty_regime === 'elevated' ? DOWNGRADE[confidenceReported] : confidenceReported;
  const views = ok ? [fields.spy_q, fields.tlt_q] : null;
  const viewNote = ok ? `views applied as excess return over cash (${rf.toFixed(2)}%)` : `LLM views rejected (${problems.join('; ')}); using equilibrium prior only`;
  const d = allocate(run.sigma, views, confidence, rf, null);
  const r2 = x => Math.round(x * 100) / 100, r1 = x => Math.round(x * 10) / 10;
  return {
    ...run,
    prototype_mode: true, cached: false, timestamp: new Date().toISOString(),
    model_used: model, model_source: source, llm_raw: raw,
    economist: fields.economist || '(no economist output parsed)', risk: fields.risk || '(no risk-manager output parsed)',
    cio: fields.cio || '(no CIO output parsed)', grounding: fields.grounding || '(no grounding summary parsed)',
    spy_q: fields.spy_q, tlt_q: fields.tlt_q, confidence, confidence_reported: confidenceReported,
    llm_parse_ok: ok, llm_problems: problems, view_note: viewNote,
    spy_q_excess: ok ? r2(fields.spy_q - rf) : null, tlt_q_excess: ok ? r2(fields.tlt_q - rf) : null,
    prior_spy: r2(d.pi[0] * 100), prior_tlt: r2(d.pi[1] * 100),
    posterior_spy: r2(d.er[0] * 100), posterior_tlt: r2(d.er[1] * 100),
    unconstrained_spy: r1(d.unconstrained[0] * 100), unconstrained_tlt: r1(d.unconstrained[1] * 100),
    target_spy: r1(d.target_spy * 100), target_tlt: r1((1 - d.target_spy) * 100),
    previous_spy: null, spy_weight: r1(d.target_spy * 100), tlt_weight: r1((1 - d.target_spy) * 100),
    trade_status: 'prototype mode: optimizer target applied directly',
  };
}
