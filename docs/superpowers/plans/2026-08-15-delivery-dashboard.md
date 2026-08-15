# Delivery Dashboard + Settings Panel Implementation Plan

> **For agentic workers:** Implement task-by-task. Checkboxes track progress.

**Goal:** Hourly snapshot dashboard (ops/exec + Q&A/silence) and settings panel (safe config + knowledge learn) on Aliyun `:8787`, Botchain fresh-green UI.

**Architecture:** aiohttp on existing port; `data/dashboard_snapshot.json` hourly; `data/runtime_overrides.yaml` for settings; shared token auth.

**Tech Stack:** Python aiohttp, Chart.js, static HTML/CSS, existing `metrics` / `message_log` / `learn` / `knowledge`.

## Global Constraints

- Refresh: 60 minutes; stream JSONL; message_log_retain_days: 60  
- Theme: Botchain fresh green (§6 design); ui-ux-pro-max dense dashboard  
- No secrets in UI; allowlisted settings only  
- Commit + push after ship; deploy `/opt/botchain-qa-tg-bot`

---

### Task 1: Snapshot builder

- [ ] Add `bot/dashboard_snapshot.py` (counters, daily, stock, answered/silent, silence_reasons)
- [ ] Atomic write `data/dashboard_snapshot.json`

### Task 2: Settings + overrides

- [ ] Add `bot/dashboard_settings.py` (allowlist, get/put, learned CRUD, apply to AppConfig)
- [ ] Merge overrides in `load_config`

### Task 3: HTTP routes

- [ ] Add `bot/dashboard_http.py`; register on aiohttp app
- [ ] Refactor webhook start so dashboard works when enabled
- [ ] Hourly loop in `main.py`

### Task 4: Frontend

- [ ] `static/dashboard/index.html` + `settings.html` + shared CSS (fresh green)
- [ ] Ops/exec toggle; Q&A tables; settings forms + learn

### Task 5: Config / docs / deploy

- [ ] `message_log_retain_days: 60`, dashboard config knobs
- [ ] README sync; deploy + `DASHBOARD_TOKEN`; commit/push
