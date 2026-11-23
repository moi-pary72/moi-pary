# Moi Pary timetable — Codex and ChatGPT team instructions

Read the repository README, `.github/workflows/sync.yml` and current task before editing. Work ONLY on the timetable project in this repository. Do not touch Wonder Hop, MAX, Avito or Hytale.

## Actions budget & safe sync — owner directive 2026-11-23
- GitHub-hosted Actions minutes are finite in private repos and repeated cloud tests waste resources. This public repo's standard GitHub-hosted minutes are ordinarily free, but still minimize redundant runs.
- Make coherent local batches. Test scripts/logic locally before pushing. Never use empty commits, repeated workflow reruns or repeated hourly manual syncs as a substitute for debugging.
- Preserve the active scheduled Yandex Disk timetable synchronization, `data/schedules.json`, `data/sync-status.json`, site rendering and current GitHub Pages publishing. No fake data or destructive schedule rewrites.
- Avoid changing the 30-minute cron or self-committing data to "save minutes" without first measuring staleness and agreeing to any reduced freshness. Treat sync success and data correctness as more important than small cost savings.
- On code change use one coherent PR with tests; diagnose failures from first logs before retrying. Record PR, SHA, CI and live verification accurately.
- New agents/chats should read this file at task start; do not presume unrelated repos share settings or billing ownership.
