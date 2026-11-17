// Cloudflare Worker for moi-pary72/moi-pary. Secrets: GITHUB_TOKEN.
// KV binding: STATE (namespace for cooldown). Cron: */30 * * * * (UTC).
const REPO = "moi-pary72/moi-pary";
const STATUS = "https://raw.githubusercontent.com/" + REPO + "/main/data/sync-status.json";
const API = "https://api.github.com/repos/" + REPO + "/dispatches";
const MAX_AGE_MS = 90 * 60 * 1000;
const COOLDOWN_MS = 60 * 60 * 1000;

async function check(env) {
  const response = await fetch(STATUS + "?t=" + Date.now(), { headers: { "Cache-Control": "no-cache" } });
  if (!response.ok) throw new Error("status HTTP " + response.status);
  const status = await response.json();
  const checked = Date.parse(status.checked_at);
  if (!Number.isFinite(checked)) throw new Error("invalid checked_at");
  if (Array.isArray(status.errors) && status.errors.length) {
    console.error("Source errors:", JSON.stringify(status.errors));
    return "source-error";
  }
  const age = Date.now() - checked;
  if (age <= MAX_AGE_MS && age >= -300000) return "fresh";
  if (!env.GITHUB_TOKEN || !env.STATE) throw new Error("Missing GITHUB_TOKEN secret or STATE KV binding");
  // KV provides best-effort throttling; scheduled triggers should have no parallel overlap.
  const previous = Number(await env.STATE.get("last_dispatch_ms") || 0);
  if (Date.now() - previous < COOLDOWN_MS) return "cooldown";
  // Reserve cooldown before dispatch to avoid duplicate triggers if the request is retried.
  await env.STATE.put("last_dispatch_ms", String(Date.now()), { expirationTtl: 86400 });
  const dispatch = await fetch(API, {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + env.GITHUB_TOKEN,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "moi-pary-cloudflare-monitor",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ event_type: "refresh-timetables", client_payload: { reason: "checked_at older than 90 minutes", checked_at: status.checked_at } })
  });
  if (!dispatch.ok) {
    await env.STATE.delete("last_dispatch_ms");
    throw new Error("dispatch HTTP " + dispatch.status + ": " + (await dispatch.text()).slice(0, 200));
  }
  console.log("Dispatched refresh; prior checked_at:", status.checked_at);
  return "dispatched-not-yet-confirmed";
}
export default {
  async scheduled(_event, env, ctx) { ctx.waitUntil(check(env).then(console.log).catch(console.error)); },
  async fetch() { return new Response("moi-pary monitor: cron only", { status: 200 }); }
};
