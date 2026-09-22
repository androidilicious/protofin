// Cloudflare Pages Function: POST /api/committee  { "i": <month index> }
// Runs one month of the three-persona committee with the site's own key, rate-limited per visitor.
//   - prompts are built server-side from the committed site/data/backtest_months.json, so a
//     visitor can never send arbitrary text to the key; only a month index is accepted
//   - economist and risk manager run concurrently, then the CIO with both replies inserted
//   - limits (KV counters): months per IP per day, months per IP per minute, months globally per day
// The key lives only in the Pages secret OPENAI_API_KEY and is never returned.
let MONTHS = null;   // isolate-level cache of the month file

async function loadMonths(env, request) {
  if (MONTHS) return MONTHS;
  const url = new URL('/data/backtest_months.json', request.url);
  const r = await env.ASSETS.fetch(new Request(url.toString()));
  if (!r.ok) throw new Error('month data unavailable');
  MONTHS = (await r.json()).months;
  return MONTHS;
}

async function bump(env, key, ttl) {
  const cur = parseInt((await env.RATE.get(key)) || '0', 10) + 1;
  await env.RATE.put(key, String(cur), { expirationTtl: ttl });
  return cur;
}

async function chat(env, prompt) {
  const t = Date.now();
  const r = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.OPENAI_API_KEY}` },
    body: JSON.stringify({ model: env.LLM_MODEL || 'gpt-4o', messages: [{ role: 'user', content: prompt }], temperature: 0, seed: 42, max_tokens: 300 }),
  });
  if (!r.ok) throw new Error(`upstream ${r.status}`);
  const j = await r.json();
  return { raw: j.choices?.[0]?.message?.content || '', ms: Date.now() - t };
}

const json = (obj, status = 200, extra = {}) => new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...extra } });

export async function onRequestGet({ env }) {
  return json({ configured: Boolean(env.OPENAI_API_KEY), model: env.LLM_MODEL || 'gpt-4o',
    limits: { per_ip_per_day: +env.LIMIT_MONTHS_PER_IP_PER_DAY || 60, per_ip_per_minute: +env.LIMIT_MONTHS_PER_IP_PER_MINUTE || 12, global_per_day: +env.LIMIT_MONTHS_GLOBAL_PER_DAY || 1500 } });
}

export async function onRequestPost({ request, env }) {
  if (!env.OPENAI_API_KEY) return json({ error: 'site committee not configured' }, 501);
  let body;
  try { body = await request.json(); } catch (e) { return json({ error: 'bad json' }, 400); }
  const i = Number.isInteger(body?.i) ? body.i : -1;
  const months = await loadMonths(env, request);
  if (i < 0 || i >= months.length) return json({ error: 'bad month index' }, 400);

  // ---- rate limits
  const ip = request.headers.get('cf-connecting-ip') || 'unknown';
  const day = new Date().toISOString().slice(0, 10), minute = Math.floor(Date.now() / 60000);
  const perDay = +env.LIMIT_MONTHS_PER_IP_PER_DAY || 60, perMin = +env.LIMIT_MONTHS_PER_IP_PER_MINUTE || 12, globalDay = +env.LIMIT_MONTHS_GLOBAL_PER_DAY || 1500;
  const [d, m, g] = await Promise.all([bump(env, `ip:${ip}:${day}`, 90000), bump(env, `ip:${ip}:m:${minute}`, 120), bump(env, `global:${day}`, 90000)]);
  const remaining = { today: Math.max(0, perDay - d), this_minute: Math.max(0, perMin - m) };
  if (g > globalDay) return json({ error: 'the site-wide daily budget for live gpt-4o backtests is used up; try tomorrow or replay the saved views', remaining }, 429, { 'Retry-After': '3600' });
  if (d > perDay) return json({ error: `daily limit reached for your address (${perDay} months/day); replay the saved views or continue tomorrow`, remaining }, 429, { 'Retry-After': '3600' });
  if (m > perMin) return json({ error: `slow down: ${perMin} months per minute per address`, remaining }, 429, { 'Retry-After': '30' });

  // ---- committee: economist || risk -> CIO, prompts from the committed month data only
  const p = months[i].prompts;
  const t0 = Date.now();
  try {
    const [e, r] = await Promise.all([chat(env, p.economist), chat(env, p.risk)]);
    const stage1 = Date.now() - t0;
    const cioPrompt = p.cio.replace('{ECONOMIST_VIEW}', e.raw.trim().slice(0, 2000)).replace('{RISK_VIEW}', r.raw.trim().slice(0, 2000));
    const c = await chat(env, cioPrompt);
    return json({ i, as_of: months[i].as_of, model: env.LLM_MODEL || 'gpt-4o', parallel: true,
      economist_raw: e.raw, risk_raw: r.raw, cio_raw: c.raw,
      timings: { economist_ms: e.ms, risk_ms: r.ms, stage1_wall_ms: stage1, cio_ms: c.ms, total_ms: Date.now() - t0 },
      remaining });
  } catch (err) {
    return json({ error: String(err.message || err) }, 502);
  }
}
