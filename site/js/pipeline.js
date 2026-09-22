// Browser pipeline: signals.json (built by CI) -> configurable model -> parse -> allocate.
// Same prompt, same parser rules and the same allocation math as the Python server.
import { allocate } from './allocation.js';

export const DOWNGRADE = { High: 'Medium', Medium: 'Low', Low: 'Low' };

// ---------- model providers ----------
// settings: { provider: 'byok' | 'site' | 'browser' | 'reference', baseUrl, model, apiKey, browserModel }
export const DEFAULTS = {
  provider: 'reference',
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-4o',
  apiKey: '',
  browserModel: 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC',
};

export function settingsFromUrl(defaults = DEFAULTS) {
  const q = new URLSearchParams(location.search);
  const s = { ...defaults };
  for (const k of ['provider', 'baseUrl', 'model', 'browserModel']) if (q.get(k)) s[k] = q.get(k);
  // the key is accepted only from the fragment (never sent to any server by the browser) or the UI
  const frag = new URLSearchParams(location.hash.replace(/^#/, ''));
  if (frag.get('key')) { s.apiKey = frag.get('key'); s.provider = s.provider === 'reference' ? 'byok' : s.provider; }
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

async function openAiCompatible(prompt, { baseUrl, model, apiKey }, extraHeaders = {}) {
  const r = await fetch(`${baseUrl.replace(/\/$/, '')}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}), ...extraHeaders },
    body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }], temperature: 0, max_tokens: 400 }),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text().catch(() => '')}`.slice(0, 300));
  const j = await r.json();
  return j.choices?.[0]?.message?.content || '';
}

let webllmEngine = null, webllmModelLoaded = null;
async function browserModel(prompt, { browserModel }, onProgress) {
  if (!('gpu' in navigator)) throw new Error('This browser has no WebGPU; the in-browser model needs Chrome or Edge on a machine with a GPU.');
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

export async function callModel(prompt, settings, signals, onProgress) {
  switch (settings.provider) {
    case 'byok':
      if (!settings.apiKey) throw new Error('Enter an API key, or choose another provider.');
      return { raw: await openAiCompatible(prompt, settings), model: settings.model, source: `your key via ${settings.baseUrl}` };
    case 'site':
      return { raw: await openAiCompatible(prompt, { baseUrl: '/api', model: settings.model, apiKey: '' }), model: settings.model, source: 'site proxy (Cloudflare Function)' };
    case 'browser':
      return { raw: await browserModel(prompt, settings, onProgress), model: settings.browserModel, source: 'in-browser (WebLLM, WebGPU)' };
    case 'reference':
    default:
      if (!signals.reference_run) throw new Error('No stored reference run in signals.json; choose a provider.');
      return { raw: signals.reference_run.raw, model: signals.reference_run.model, source: `stored reference run (${signals.reference_run.generated_at})` };
  }
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
export async function runPipeline(signals, settings, onProgress) {
  const { raw, model, source } = await callModel(signals.prompt, settings, signals, onProgress);
  const { fields, problems } = parseReply(raw);
  const ok = problems.length === 0;
  const rf = signals.risk_free;
  const confidenceReported = fields.confidence || 'Low';
  const confidence = signals.uncertainty_regime === 'elevated' ? DOWNGRADE[confidenceReported] : confidenceReported;
  const views = ok ? [fields.spy_q, fields.tlt_q] : null;
  const viewNote = ok ? `views applied as excess return over cash (${rf.toFixed(2)}%)` : `LLM views rejected (${problems.join('; ')}); using equilibrium prior only`;
  const d = allocate(signals.sigma, views, confidence, rf, null);
  const r2 = x => Math.round(x * 100) / 100, r1 = x => Math.round(x * 10) / 10;
  return {
    ...signals,
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
