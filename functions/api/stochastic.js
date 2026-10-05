// Cloudflare Pages Function: POST /api/stochastic  { run, r, temperature }
// One committee run (economist ∥ risk -> CIO) on the latest committed signals, sampled at a
// temperature above 0. The page calls it N times with the same run id to measure how much the
// committee disagrees with itself on identical input (Farnoosh Memari's empirical view uncertainty,
// docs/EMPIRICAL_UNCERTAINTY.md). Prompts come from site/data/signals.json; the visitor sends no text.
// Limits: 10 runs per visitor per day (a run = up to 8 samples), plus the site-wide daily cap.
import { checkRunLimit } from '../_lib/runlimit.js';

const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
const MAX_SAMPLES = 8;

async function chat(env, prompt, temperature, seed) {
  const t = Date.now();
  const r = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.OPENAI_API_KEY}` },
    body: JSON.stringify({ model: env.LLM_MODEL || 'gpt-4o', messages: [{ role: 'user', content: prompt }], temperature, seed, max_tokens: 300 }),
  });
  if (!r.ok) throw new Error(`upstream ${r.status}`);
  const j = await r.json();
  return { raw: j.choices?.[0]?.message?.content || '', ms: Date.now() - t };
}

export async function onRequestGet({ env }) {
  return json({ configured: Boolean(env.OPENAI_API_KEY), model: env.LLM_MODEL || 'gpt-4o', max_samples: MAX_SAMPLES, runs_per_ip_per_day: +env.LIMIT_RUNS_PER_IP_PER_DAY || 10 });
}

export async function onRequestPost({ request, env }) {
  if (!env.OPENAI_API_KEY) return json({ error: 'not configured' }, 501);
  let body; try { body = await request.json(); } catch (e) { return json({ error: 'bad json' }, 400); }
  const r = Number.isInteger(body?.r) ? body.r : -1;
  if (r < 0 || r >= MAX_SAMPLES) return json({ error: `sample index must be 0..${MAX_SAMPLES - 1}` }, 400);
  const temperature = Math.min(1, Math.max(0, Number(body?.temperature ?? 0.2)));
  const rl = await checkRunLimit(env, request, body?.run, 'stochastic', +env.LIMIT_RUNS_PER_IP_PER_DAY || 10);
  if (!rl.ok) return json({ error: rl.error }, rl.status);
  if (env.RATE) {   // site-wide spend cap shared with the live backtest (each sample = one committee run)
    const day = new Date().toISOString().slice(0, 10), k = `global:${day}`;
    const n = parseInt((await env.RATE.get(k)) || '0', 10) + 1;
    if (n > (+env.LIMIT_MONTHS_GLOBAL_PER_DAY || 300)) return json({ error: 'the site-wide daily budget for live gpt-4o runs is used up; try tomorrow' }, 429);
    await env.RATE.put(k, String(n), { expirationTtl: 90000 });
  }
  const sr = await env.ASSETS.fetch(new Request(new URL('/data/signals.json', request.url).toString()));
  if (!sr.ok) return json({ error: 'signals unavailable' }, 502);
  const sig = await sr.json();
  const p = sig.prompts;
  if (!p) return json({ error: 'signals carry no committee prompts' }, 502);
  const seed = 1000 + r;   // best effort only; OpenAI does not guarantee determinism
  const t0 = Date.now();
  try {
    const [e, k] = await Promise.all([chat(env, p.economist, temperature, seed), chat(env, p.risk, temperature, seed)]);
    const cioPrompt = p.cio.replace('{ECONOMIST_VIEW}', e.raw.trim().slice(0, 2000)).replace('{RISK_VIEW}', k.raw.trim().slice(0, 2000));
    const c = await chat(env, cioPrompt, temperature, seed);
    return json({ r, temperature, seed, model: env.LLM_MODEL || 'gpt-4o', as_of: sig.as_of, fingerprint: sig.fingerprint,
      economist_raw: e.raw, risk_raw: k.raw, cio_raw: c.raw, ms: Date.now() - t0, runs_left_today: rl.remaining });
  } catch (err) { return json({ error: String(err.message || err) }, 502); }
}
