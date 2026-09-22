// Cloudflare Pages Function: optional site-wide model proxy at POST /api/chat/completions.
// The key lives ONLY in the Pages project's environment variables (OPENAI_API_KEY, optional
// LLM_BASE_URL, LLM_MODEL). It is never sent to the browser. If no key is configured the
// endpoint answers 501 and the page hides the "site key" option.
export async function onRequestPost({ request, env }) {
  const key = env.OPENAI_API_KEY;
  if (!key) return new Response(JSON.stringify({ error: 'site proxy not configured' }), { status: 501, headers: { 'Content-Type': 'application/json' } });
  let body;
  try { body = await request.json(); } catch (e) { return new Response('bad json', { status: 400 }); }
  // Only the committee prompt is forwarded; the caller cannot choose arbitrary parameters.
  const prompt = body?.messages?.[0]?.content;
  if (typeof prompt !== 'string' || prompt.length > 8000) return new Response('bad prompt', { status: 400 });
  const upstream = await fetch(`${(env.LLM_BASE_URL || 'https://api.openai.com/v1').replace(/\/$/, '')}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body: JSON.stringify({ model: env.LLM_MODEL || body.model || 'gpt-4o', messages: [{ role: 'user', content: prompt }], temperature: 0, max_tokens: 400 }),
  });
  const text = await upstream.text();
  return new Response(text, { status: upstream.status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
}

// GET tells the page whether the site key is configured (never what it is)
export async function onRequestGet({ env }) {
  return new Response(JSON.stringify({ configured: Boolean(env.OPENAI_API_KEY), model: env.LLM_MODEL || 'gpt-4o' }),
    { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
}
