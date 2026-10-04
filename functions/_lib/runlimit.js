// Shared per-visitor run limit for the model-calling endpoints, stored in D1 (strongly consistent).
// A "run" is one backtest pass; the page sends the same run id with every month of it.
// The first request with a new run id spends one run; later months of that run are free.
// The insert is conditional on the count in the same statement, so concurrent new runs cannot
// overshoot the limit.
export async function checkRunLimit(env, request, run, scope, limit) {
  if (!run || !/^[A-Za-z0-9_-]{8,64}$/.test(run)) return { ok: false, status: 400, error: 'missing run id' };
  if (!env.LIMITS_DB) return { ok: true, remaining: null };
  const ip = request.headers.get('cf-connecting-ip') || 'x', day = new Date().toISOString().slice(0, 10);
  const db = env.LIMITS_DB;
  const known = await db.prepare('SELECT 1 FROM runs WHERE scope=?1 AND ip=?2 AND day=?3 AND run=?4').bind(scope, ip, day, run).first();
  if (!known) {
    const ins = await db.prepare(
      `INSERT INTO runs (scope, ip, day, run)
       SELECT ?1, ?2, ?3, ?4 WHERE (SELECT COUNT(*) FROM runs WHERE scope=?1 AND ip=?2 AND day=?3) < ?5
       ON CONFLICT DO NOTHING`).bind(scope, ip, day, run, limit).run();
    if (!ins.meta.changes) {
      const again = await db.prepare('SELECT 1 FROM runs WHERE scope=?1 AND ip=?2 AND day=?3 AND run=?4').bind(scope, ip, day, run).first();
      if (!again) return { ok: false, status: 429, error: `daily limit reached for your address (${limit} runs/day); come back tomorrow`, remaining: 0 };
    }
  }
  const used = (await db.prepare('SELECT COUNT(*) AS n FROM runs WHERE scope=?1 AND ip=?2 AND day=?3').bind(scope, ip, day).first()).n;
  return { ok: true, remaining: Math.max(0, limit - used) };
}
