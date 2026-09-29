// Cloudflare Pages Function: POST /api/jev  { "i": <month index> }
// Asks Jev (typesafe/jev on Workers AI) typed questions about one masked backtest month.
// Auth is the Workers AI binding (env.AI): no API key exists in code, config, browser or GitHub.
// Only a month index is accepted; the state is built server-side from committed data.
let MONTHS = null;
async function loadMonths(env, request) {
  if (MONTHS) return MONTHS;
  const r = await env.ASSETS.fetch(new Request(new URL('/data/backtest_months.json', request.url).toString()));
  if (!r.ok) throw new Error('month data unavailable');
  MONTHS = (await r.json()).months;
  return MONTHS;
}
const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });

export const QUESTIONS = {
  stocks_beat_bonds: {
    type: 'noul',
    instructions: 'Over the NEXT 12 MONTHS, will SPY (US equities) deliver a higher total return than TLT (long US Treasuries)?',
    criteria: { true: 'SPY outperforms TLT over the next 12 months', false: 'TLT outperforms or matches SPY over the next 12 months' },
  },
  tilt: {
    type: 'choice',
    instructions: 'Relative to a neutral 60% equities / 40% long Treasuries portfolio, how should the equity share be tilted for the next 12 months, given only this data?',
    criteria: {
      strong_equities: 'Clear evidence equities will beat long Treasuries by a wide margin',
      lean_equities: 'Some evidence equities will beat long Treasuries',
      neutral: 'No reliable edge either way; stay at 60/40',
      lean_bonds: 'Some evidence long Treasuries will beat equities',
      strong_bonds: 'Clear evidence long Treasuries will beat equities by a wide margin',
    },
  },
};

export async function onRequestGet({ request, env }) {
  const out = { configured: Boolean(env.AI), model: 'typesafe/jev', questions: QUESTIONS };
  if (new URL(request.url).searchParams.get('probe') === '1' && env.AI) {   // is the binding itself healthy? (native model)
    try { const r = await env.AI.run('@cf/meta/llama-guard-3-8b', { messages: [{ role: 'user', content: 'Reply with the word ok.' }], max_tokens: 5 }); out.native_probe = r; }
    catch (e) { out.native_probe_error = String(e.message || e); }
  }
  return json(out);
}

export async function onRequestPost({ request, env }) {
  if (!env.AI) return json({ error: 'Workers AI binding missing' }, 501);
  let body; try { body = await request.json(); } catch (e) { return json({ error: 'bad json' }, 400); }
  const months = await loadMonths(env, request);
  const i = Number.isInteger(body?.i) ? body.i : -1;
  if (i < 0 || i >= months.length) return json({ error: 'bad month index' }, 400);
  if (env.RATE) {   // light per-IP limit; reuses the KV namespace
    const ip = request.headers.get('cf-connecting-ip') || 'x', day = new Date().toISOString().slice(0, 10);
    const k = `jev:${ip}:${day}`, n = parseInt((await env.RATE.get(k)) || '0', 10) + 1;
    if (n > 400) return json({ error: 'daily Jev limit reached for your address (400 months/day)' }, 429);
    if (n % 5 === 1) await env.RATE.put(k, String(n + 4), { expirationTtl: 90000 });   // write every 5th call to spare KV quota
  }
  const t = Date.now();
  try {
    const raw = await env.AI.run('typesafe/jev', { state: months[i].payload, questions: QUESTIONS }, env.JEV_GATEWAY ? { gateway: { id: env.JEV_GATEWAY } } : undefined);
    return json({ i, as_of: months[i].as_of, ms: Date.now() - t, raw });
  } catch (e) {
    return json({ error: String(e.message || e) }, 502);
  }
}
