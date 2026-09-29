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
  const tp = new URL(request.url).searchParams.get('tp');   // third-party probe through the gateway, e.g. ?tp=openai/gpt-4o-mini
  if (tp && env.AI) {
    for (const opt of [env.JEV_GATEWAY ? { gateway: { id: env.JEV_GATEWAY } } : undefined, undefined]) {
      try { const r = await env.AI.run(tp, { messages: [{ role: 'user', content: 'Reply with the word ok.' }], max_tokens: 5 }, opt); (out.tp ||= []).push({ gateway: !!opt, ok: true, r }); }
      catch (e) { (out.tp ||= []).push({ gateway: !!opt, error: String(e.message || e) }); }
    }
    try { const r = await env.AI.run('typesafe/jev', { state: 'The sky is blue.', questions: { q: { type: 'noul', instructions: 'Is the sky described as blue?', criteria: { true: 'yes', false: 'no' } } } }); (out.jev_nogw = r); }
    catch (e) { out.jev_nogw_error = String(e.message || e); }
  }
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
  // limit: runs (not months) per visitor per day. The page sends a run id with every month of a run;
  // a new run id costs one run. Two KV writes per run, none per month.
  const run = typeof body?.run === 'string' && /^[A-Za-z0-9_-]{8,64}$/.test(body.run) ? body.run : null;
  if (!run) return json({ error: 'missing run id' }, 400);
  if (env.RATE) {
    const ip = request.headers.get('cf-connecting-ip') || 'x', day = new Date().toISOString().slice(0, 10);
    const mark = `jevrun:${ip}:${day}:${run}`;
    if (!(await env.RATE.get(mark))) {
      const k = `jevruns:${ip}:${day}`, n = parseInt((await env.RATE.get(k)) || '0', 10) + 1;
      const lim = +env.LIMIT_JEV_RUNS_PER_IP_PER_DAY || 50;
      if (n > lim) return json({ error: `daily limit reached for your address (${lim} runs/day); use Compare or come back tomorrow` }, 429);
      await Promise.all([env.RATE.put(k, String(n), { expirationTtl: 90000 }), env.RATE.put(mark, '1', { expirationTtl: 90000 })]);
    }
  }
  const t = Date.now();
  try {
    const raw = await env.AI.run('typesafe/jev', { state: months[i].payload, questions: QUESTIONS }, env.JEV_GATEWAY ? { gateway: { id: env.JEV_GATEWAY } } : undefined);
    return json({ i, as_of: months[i].as_of, ms: Date.now() - t, raw });
  } catch (e) {
    return json({ error: String(e.message || e) }, 502);
  }
}
