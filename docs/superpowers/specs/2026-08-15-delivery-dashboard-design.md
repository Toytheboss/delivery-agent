# Delivery Agent live dashboard (design)

**Date:** 2026-08-15  
**Status:** draft — awaiting user review  
**Repo:** Botchain QA TG Bot / Delivery Agent  
**Decision:** Approach A — host on Aliyun alongside `botchain-qa`

## 1. Goal

Personal ops dashboard on the production Aliyun host that shows **all Delivery Agent metrics**, with a **single page** that switches between:

- **Ops view** — FAQ / welcome / form / logo / mark-live / webhook, trends  
- **Exec view** — 24h + 7d reach, live/form/logo/wallet stock, learn (aligned with daily + weekly TG reports)

Plus **answered Q&A** and **silent questions with reasons**, aggregated from message logs.

Refresh cadence: **once per hour** (low server load). Not sub-minute realtime.

## 2. Non-goals

- Public unauthenticated access  
- Browser polling that re-scans Lark or full JSONL every request  
- Keeping full 90-day Q&A text inside the dashboard payload  
- Replacing TG `/daily` / `/report` / `/stats` commands

## 3. Architecture

```
┌─────────────────────────────────────────────┐
│ botchain-qa (same process / same host)      │
│  hourly job → build snapshot → write disk   │
│  aiohttp :8787                              │
│    GET /health          (existing)          │
│    GET /dashboard/api   (token) → snapshot  │
│    GET /dashboard/      (token) → HTML      │
└─────────────────────────────────────────────┘
         ▲
         │ Cloudflare tunnel (optional, existing)
         │
    Operator browser (ops ↔ exec toggle)
```

**Snapshot file:** `data/dashboard_snapshot.json` (atomic rewrite each hour).

**Request path:** serve the last snapshot only. If missing/stale beyond a grace window, optionally kick a rebuild in a background thread (at most one concurrent build) — never block the event loop with Lark + full log scan on every hit.

## 4. Auth

- Shared secret: env `DASHBOARD_TOKEN` (or reuse a dedicated config key; do **not** reuse the Lark live webhook secret in URLs if avoidable).  
- Accept `Authorization: Bearer <token>` or `?token=`.  
- HTML and JSON both require the token.  
- No CORS open to arbitrary origins required for same-origin page+API.

## 5. Snapshot contents

### 5.1 Meta

- `generated_at` (Asia/Shanghai ISO)  
- `window`: `{ "qa_days": 7, "list_limit": 150 }` (configurable)  
- `source_updated_at` from `delivery_metrics.json`

### 5.2 Counters / reports (reuse existing builders)

- Full `delivery_metrics` counters (totals + `by_day`)  
- Output of `snapshot(config, include_lark=…)` for week/today style fields used by exec view — **Lark-heavy parts only inside the hourly job**, cached into the file  
- Output of `build_daily_report` for 24h exec panel  
- Workflow stock from state files (form / logo / welcome / chase / deploy / live_seen / wallet digest) — read JSON from disk, no Telegram API in the job

### 5.3 Q&A and silence (from `data/message_logs/messages-YYYY-MM-DD.jsonl`)

Stream day files for the configured lookback (default **7 days** for lists; reason histogram may use same window).

| Bucket | Filter | Fields kept in snapshot |
|--------|--------|-------------------------|
| `answered` | `outcome == "replied"` (prefer FAQ/inbound kinds; include casual if useful — tag `reason`) | `ts`, `chat_title`, `text`, `reply_text`, `reason`, `score` |
| `silent` | `outcome == "silent"` | `ts`, `chat_title`, `text`, `reason`, `score` |
| `silence_reasons` | count by `reason` over the window | `{ reason: count }` |

**Caps:** each of `answered` / `silent` keeps at most **`list_limit`** newest rows (default 150). Older rows stay only on disk in JSONL.

**Memory rule:** never `Path.read_text()` an entire multi-day corpus. Open each day file, iterate lines, keep a bounded deque / heap of newest matching rows and a reason counter dict.

### 5.4 Retention (user decision 2026-08-15)

| Store | Retain |
|-------|--------|
| `metrics.message_log_retain_days` | **60** (was 90) |
| Metrics `by_day` prune | keep aligned ~60–90d (prefer match 60 when touching prune logic, or leave metrics prune as-is if already ~90 — document actual code behavior in implementation) |
| Snapshot file | single file, overwritten hourly |

Update `config.yaml.example` default to `60`; apply the same on production `config.yaml` at deploy time.

## 6. UI & visual design

**Skills / sources:** follow **ui-ux-pro-max** (Data-Dense Dashboard pattern + checklist). Brand color: **Botchain fresh green** (light “清新”, not the dark neon deck theme).

### 6.1 Layout pattern (Pro Max)

- Style: **Data-Dense Dashboard** — KPI cards, compact grid, charts + tables, space-efficient  
- Stack for implementation: single static **HTML + CSS** (Chart.js OK; Tailwind optional via CDN)  
- Toggle **运营 | 管理层** in the top bar (one page, one composition per view)  
- Brand: Botchain wordmark / logo in header (reuse `docs/assets/botchain-logo.png` if available)  
- Effects: 150–300ms hover on clickable controls; row highlight on table hover; loading state while fetching snapshot  
- Charts: line/area for day trends; doughnut/bar for silence reasons; keep legend readable, no chart junk  
- Anti-patterns: no emoji-as-icons; no ornate chrome; no purple-on-white AI cliché; respect `prefers-reduced-motion`

### 6.2 Botchain fresh-green tokens

Light “清新绿” surface (Climate/ESG-adjacent greens from Pro Max color search, aligned to Botchain accent):

| Token | Hex | Use |
|-------|-----|-----|
| `--bg` | `#ECFDF5` | Page background |
| `--surface` | `#FFFFFF` | Cards / panels |
| `--surface-2` | `#D1FAE5` | Subtle strips / active tab |
| `--text` | `#064E3B` | Primary text |
| `--muted` | `#047857` | Secondary text (ensure ≥4.5:1 on bg) |
| `--primary` | `#059669` | Primary actions / KPI accents |
| `--primary-2` | `#10B981` | Charts / secondary accent |
| `--brand-mint` | `#79FFB8` | Botchain mint highlight (sparingly: focus ring, active toggle) |
| `--warn` | `#FBBF24` | Warnings / low-score buckets |
| `--danger` | `#DC2626` | Fail / silent-heavy callouts |
| `--border` | `#A7F3D0` | Hairline borders |

Typography (Pro Max dashboard mood): **Fira Sans** (UI) + **Fira Code** (numbers / monospace timestamps). Load via Google Fonts.

### 6.3 Views

- **Ops:** KPI row (FAQ / welcome / form / logo / mark-live / webhook), day trends, silence-reason chart, answered + silent tables  
- **Exec:** 24h + 7d summary cards mirroring daily + weekly report narrative  
- Footer: `generated_at` + note that data refreshes hourly (soft auto-reload of JSON every 60 minutes)

### 6.4 Pre-delivery checklist (from Pro Max)

- [ ] No emoji icons (SVG / text labels only)  
- [ ] `cursor: pointer` on clickable elements  
- [ ] Light-mode contrast ≥ 4.5:1  
- [ ] Visible focus states (mint ring OK)  
- [ ] Responsive: 375 / 768 / 1024 / 1440  
- [ ] `prefers-reduced-motion` respected  


## 7. Config knobs

```yaml
dashboard:
  enabled: true
  token_env: "DASHBOARD_TOKEN"   # or inline only via env
  refresh_minutes: 60
  qa_lookback_days: 7
  list_limit: 150
  path_prefix: "/dashboard"
```

`metrics.message_log_retain_days: 60`

## 8. Implementation sketch (for later plan)

1. `bot/dashboard_snapshot.py` — build + atomic write  
2. Wire hourly `asyncio` task in `bot/main.py` (same pattern as other loops)  
3. Extend aiohttp app in webhook module (or small `bot/dashboard_http.py`) with `/dashboard` + `/dashboard/api`  
4. Static HTML under `static/dashboard/` (or `docs/`) served by aiohttp — **Botchain fresh-green + ui-ux-pro-max dense dashboard** (see §6); do not copy the dark neon analytics deck as the default theme  
5. README + config example + `message_log_retain_days: 60`  
6. Deploy to `/opt/botchain-qa-tg-bot`, set `DASHBOARD_TOKEN`, restart `botchain-qa`  
7. Commit + push to GitHub per project rule  

## 9. Risks / mitigations

| Risk | Mitigation |
|------|------------|
| Hourly job CPU spike | Stream JSONL; skip Lark if last Lark section < N minutes old optional; hard timeout |
| Memory growth | Bounded lists; 60d log retention; one in-memory snapshot |
| Token in URL leaks via Referer | Prefer Bearer / localStorage after first entry; document tunnel Access if available |
| Stale snapshot | Show `generated_at`; browser reload hourly |

## 10. Success criteria

- Operator opens `/dashboard?token=…` (or tunnel URL), switches ops/exec without reload of two sites  
- Answered and silent tables show recent items with reasons; silence histogram matches logs  
- Hourly job completes without material RSS growth over days  
- Message logs older than 60 days are purged  
- TG report commands still work unchanged  

## 12. Settings panel (approved 2026-08-15)

Second surface on the same host/auth/theme: **配置面板** for safe runtime knobs + knowledge learn ops.

### 12.1 Storage

- Persist operator edits to `data/runtime_overrides.yaml` (deep-merge over `config/config.yaml` at load and on save).
- Do **not** rewrite secrets in `.env` from the UI.
- Companion YAML edits allowed for: ignore users / ignored groups / qa testers (with backup `.bak`).

### 12.2 Allowlisted editable fields (v1)

Reply/scope/learn/knowledge/welcome/workflow toggles + templates listed in the inventory (safe set). Advanced IDs (Lark tokens, table ids) read-only or hidden.

### 12.3 Knowledge learn UI

- Toggle learn + trigger word + scopes + min_chars + agent_kb.enabled  
- List recent `knowledge/learned/*.md`  
- Create note (title + body) → write learned file + optional KB reload + optional Lark upsert  
- Delete/disable a learned file + reload  
- Button: reload knowledge now  

### 12.4 API

- `GET /dashboard/api/settings` — current allowlisted values  
- `PUT /dashboard/api/settings` — validate + write overrides + mutate live `AppConfig`  
- `GET/POST/DELETE /dashboard/api/learned` — list / create / delete  
- `POST /dashboard/api/knowledge/reload`  

### 12.5 UI

Same Botchain fresh-green + Pro Max dense forms; nav between **数据** and **设置**.
