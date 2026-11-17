/** Independent timetable freshness monitor; never edits timetable data itself.
 * Git-connected Cloudflare production deployment: moi-pary-monitor.
 */
const REPO = 'moi-pary72/moi-pary';
const BASE = `https://api.github.com/repos/${REPO}`;
const STATUS_URL = `https://raw.githubusercontent.com/${REPO}/main/data/sync-status.json`;
const MAX_STALE_MS = 90 * 60_000;
const COOLDOWN_MS = 60 * 60_000;
const FUTURE_TOLERANCE_MS = 5 * 60_000;

function isoAge(timestamp, now) {
  const time = Date.parse(timestamp);
  if (!Number.isFinite(time)) throw new Error('Invalid source status timestamp');
  const age = now.getTime() - time;
  if (age < -FUTURE_TOLERANCE_MS) throw new Error('Source status timestamp is in the future');
  return age;
}
function githubHeaders(token) {
  return {Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version':'2022-11-28','User-Agent':'moi-pary-cloudflare-monitor'};
}
async function getJSON(url, options={}) {
  const response = await fetch(url,{...options,signal:AbortSignal.timeout(15000)});
  if (!response.ok) throw new Error(`Remote HTTP ${response.status}`);
  return response.json();
}
function latestRunAt(runs, now) {
  if (!Array.isArray(runs.workflow_runs)) throw new Error('Invalid GitHub run list');
  return runs.workflow_runs.reduce((best,run)=>{
    const started = Date.parse(run.created_at);
    if (!Number.isFinite(started) || started > now.getTime()+FUTURE_TOLERANCE_MS) return best;
    return Math.max(best,started);
  },0);
}
export async function check(env, now=new Date()) {
  const status = await getJSON(`${STATUS_URL}?t=${now.getTime()}`,{headers:{'Cache-Control':'no-cache'}});
  const age = isoAge(status.checked_at,now);
  if (Array.isArray(status.errors) && status.errors.length) {
    console.error('Official source check reported errors; original timetable remains authoritative');
    return 'source-error';
  }
  if (age <= MAX_STALE_MS) return 'fresh';
  if (!env.GITHUB_TOKEN) throw new Error('Missing GITHUB_TOKEN secret; no dispatch');
  const headers = githubHeaders(env.GITHUB_TOKEN);
  // GitHub workflow history provides a durable rate limit without Cloudflare KV.
  const runs = await getJSON(`${BASE}/actions/workflows/sync.yml/runs?per_page=10`,{headers});
  const mostRecent = latestRunAt(runs,now);
  const busy = runs.workflow_runs.some(run=>['queued','in_progress','waiting','pending','requested'].includes(run.status));
  if (busy) return 'github-run-active';
  if (mostRecent && now.getTime()-mostRecent < COOLDOWN_MS) return 'github-run-cooldown';
  const dispatch = await fetch(`${BASE}/dispatches`,{
    method:'POST', headers:{...headers,'Content-Type':'application/json'},
    body:JSON.stringify({event_type:'refresh-timetables',client_payload:{trigger:'cloudflare',reason:'stale_source_check'}}),
    signal:AbortSignal.timeout(15000)
  });
  if (dispatch.status!==204) throw new Error(`GitHub dispatch rejected: HTTP ${dispatch.status}`);
  return 'github-dispatch-accepted-not-published';
}
export default {
  async fetch(request,env) {
    const url = new URL(request.url);
    if (request.method!=='GET' || !['/','/health'].includes(url.pathname)) return new Response('Not found',{status:404});
    return Response.json({service:'moi-pary72-freshness-monitor',mode:'cloudflare-cron-github-refresh',
      configured:Boolean(env.GITHUB_TOKEN),cadence:'every 30 minutes', max_age_minutes:90,
      note:'Public HTTP endpoint never launches a sync'}, {headers:{'Cache-Control':'no-store'}});
  },
  async scheduled(_event,env,ctx){ctx.waitUntil(check(env).then(x=>console.log('monitor:',x)).catch(e=>{console.error('Monitor check failed:',e.message);throw e;}));}
};
