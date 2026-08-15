# Delivery Agent

Telegram **Userbot** + Lark (Feishu) workflow automation for project delivery.

It answers partner FAQs in Telegram groups, greets new project chats, runs the **mainnet-live → Google Form → logo → wallet** pipeline with Lark, and gives operators daily/weekly ops reports.

> This is a **Userbot** (Telethon personal account), **not** a BotFather bot.  
> Secrets stay local: `.env`, `*.session`, and real `config/*.yaml` are **never** committed.

> **Maintaining this doc:** every new / changed / removed bot capability must be reflected in **Features** (and Config / Env / Ops tables if needed) in the same change set. See `.cursor/rules/readme-feature-sync.mdc`.

---

## Features (full list)

### 1. Scope & access control

| Feature | What it does |
|---------|----------------|
| **Folder scope** | Only listens / auto-replies inside configured Telegram *Projects* folders (e.g. multiple folders with a shared name prefix). |
| **Pilot mode** | Optional: FAQ auto-reply limited to listed pilot groups while testing. |
| **Group replies toggle** | Can disable group FAQ replies while keeping DMs / ops commands. |
| **Ignored groups** | Hard skip list (`config/ignored_groups.yaml`). |
| **BD / ignore blacklist** | Listed users never get auto-replies (`config/whitelist.yaml` → `ignore_users`), except workflow operators on mark-live / send-form. |
| **QA testers** | Configured accounts/groups can ask without `@mention`, skip reply delay, and use ops commands (`config/qa_testers.yaml`). |
| **Workflow operators** | Username allowlist for mark-live / send-form / reports. |
| **Rate limit** | Per (chat, user) cooldown between auto-replies. |

---

### 2. FAQ / RAG auto-reply

| Feature | What it does |
|---------|----------------|
| **Knowledge RAG** | Retrieves chunks from `knowledge/` (markdown FAQ packs, help docs, learned notes). |
| **LLM compose** | DeepSeek / OpenAI-compatible chat; answers in the asker’s language (`auto` ZH/EN). |
| **Trigger rules** | `@bot` / reply-to-bot, question-like text, or `trigger.hint_keywords` (e.g. pricing / 报价). |
| **Stay silent when unsure** | Below `min_relevance_score`, blocked commercial topics, or model `NEEDS_HUMAN` → no reply. |
| **Multi-bubble replies** | Splits long answers on `---`; optional delay before first reply + gap between bubbles (more “human”). |
| **FAQ footer** | Optional bold/italic disclaimer after a successful FAQ reply only. |
| **URL hygiene** | Can scrub blocked URLs so they never appear in answers. |
| **Periodic KB reload** | Reloads knowledge on the same interval as folder refresh. |

---

### 3. Social chitchat

| Feature | What it does |
|---------|----------------|
| **Greetings** | Short emoji replies to `gm` / `gn` / `早上好` / `晚安` / etc. (not FAQ). |
| **X / Twitter shares** | Casual thanks when partners share short posts (links + “发了” style captions). |
| **Short acks** | `收到` / `好的` / `thanks` / `got it` / `ok` / `will do` → short casual reply (not FAQ, not silence). |
| **FAQ fallback** | If RAG silences a social/ack-shaped message, still send the casual reply. |

---

### 4. Group welcome

| Feature | What it does |
|---------|----------------|
| **Join greeting** | When the account is added to a group whose title matches keywords (e.g. brand / partner tokens). |
| **Language detection** | Samples recent non-bot messages → title hint → English fallback. |
| **Timed sequence** | Configurable ZH/EN multi-step welcome (`delay_seconds`: e.g. 0 / 30 / 60). |
| **Min-message gate** | `0` = greet immediately; `>0` = wait for N non-bot messages. |
| **Baseline (no spam)** | Existing matching groups are marked “already greeted” on first enable / pilot expand — scans never backfill-greet old chats. |
| **Pilot kickoff** | Can greet configured pilot groups at startup. |
| **Backup scan** | Periodic scan only processes pending joins; does not spam baselined groups. |

---

### 5. Folder auto-add

| Feature | What it does |
|---------|----------------|
| **Auto-file new chats** | On join (and periodic scan), puts matching-title groups into the first free Projects folder. |
| **Keyword match** | Uses `scope.auto_add_keywords` (or welcome keywords). |
| **Capacity** | Respects ~100 chats per Telegram folder; optional auto-create `prefix #N` folders. |
| **Title cache** | Remembers chat titles for later form matching (avoids heavy `get_entity` storms). |
| **TG rate limiting** | Serializes / paces heavy Telegram calls as folders grow. |

---

### 6. Live delivery workflow (Lark ↔ Telegram)

End-to-end path when a project goes **Mainnet Live**:

1. Detect live (webhook / status watch / TG mark-live)  
2. Match Lark project ↔ Telegram group  
3. Send Google onboarding form  
4. Fill project logo into Lark (best-effort, once)  
5. Partner submits form → Apps Script → Lark wallet table  
6. Optional: chase incomplete forms, notify internal groups, daily Lark digest  

| Feature | What it does |
|---------|----------------|
| **Lark live webhook** | HTTP endpoint (default `/workflow/live`) when Progress status flips to live. |
| **Live status watch** | Polls Progress Tracker; only **new** live rows trigger form + logo (webhook backup). |
| **Deploy status watch** | Tracks enter/leave mainnet-live / mainnet-deploying / testnet-deploying for daily report. |
| **Startup live catch-up** | Optional one-shot process of live rows missing form/logo. |
| **Form dispatch** | Fuzzy-match project name to folder group title (or Lark TG chat id field); send templated message + form URL. |
| **Manual send form** | Ops command in current group as fallback. |
| **Mark live** | Ops keyword sets Lark status to live and can also run form + logo. |
| **Logo fill** | Fetches site logo from live/project URL into Lark attachment field: HTTP scrape first, then Playwright header/element screenshot if that fails (still one record attempt; no poller retry on hard fail). |
| **Form / logo poll** | Optional expensive poller (off by default; prefer webhook + watch + mark-live). |
| **Form chase (24h)** | After form sent: if wallet table still has &lt; N of required fields after 24h, resend reminder listing **missing fields** (capped reminders). |
| **Wallet notify (TG)** | When required wallet fields are complete, notify finance/ops/tech chats (optional). |
| **Lark wallet digest** | Daily Lark IM digest of newly collected wallet projects (Asia/Shanghai hour). |
| **Baseline existing live** | First run can mark already-live rows as handled to avoid spam. |

**Workflow command aliases** (configurable; defaults in `config.yaml.example`):

| Action | Keywords |
|--------|----------|
| Mark live | `项目已上线`, `/mark_live`, `mark live`, `上线完成` |
| Send form | `/send_form`, `发送上线表单`, `send form` |

---

### 7. Operator reports & metrics

| Feature | What it does |
|---------|----------------|
| **Persistent counters** | FAQ sessions/bubbles/footer, social, welcome, folder add, form/logo outcomes, mark-live, webhooks, wallet digest, messages processed, etc. |
| **Stats (detail)** | Full Chinese ops breakdown. |
| **Weekly / exec report** | Management-facing summary for the **past 7 days**; also writes `data/delivery_agent_report.txt`. |
| **Daily report** | Rolling **past 24 hours**: new mainnet live, deploy transitions, new folder groups, new wallets, logos, bot message mix (processed / replied / FAQ / social / welcome / form). |
| **Message detail log** | Append-only JSONL under `data/message_logs/messages-YYYY-MM-DD.jsonl`: inbound text + reply text + outcome/reason/score (retain N days, default **60**). |
| **Web dashboard** | Hourly snapshot on Aliyun `:8787/dashboard` (24h daily report, 30-day calendar with 7/30-day range summaries, 14-day charts, day-level logo/wallet/Q&A). Token via `DASHBOARD_TOKEN`. |
| **Settings panel** | Same host `/dashboard/settings`: allowlisted runtime knobs + knowledge learn CRUD / KB reload → `data/runtime_overrides.yaml`. |

**Report command aliases:**

| Report | Commands |
|--------|----------|
| Stats | `/stats`, `交付统计` |
| Weekly | `/report`, `交付周报`, `交付报告` |
| Daily | `/daily`, `/daily_report`, `交付日报`, `今日交付日报`, and compact colon variants |

Reports are **on-demand** (no scheduled TG push unless you add one).

---

### 8. Learn / absorb knowledge

| Feature | What it does |
|---------|----------------|
| **In-chat learn** | Message contains trigger word (default `学习`) → write a knowledge note under `knowledge/learned/`. |
| **Reply-learn** | Reply to a partner message with the trigger to absorb that content. |
| **Scope rules** | QA groups / QA testers / project folders (configurable). In project groups, typically **QA testers only**. |
| **KB reload** | Reloads chunks after a successful learn. |
| **Agent KB upsert** | Optional sync of learned Q&A into a Lark Bitable “Agent glossary” (create/update by id; no full-table wipe). |

---

### 9. Lark knowledge sync

| Feature | What it does |
|---------|----------------|
| **Wiki → markdown** | Optional sync of a Lark wiki doc into `knowledge/lark_*.md` (startup + interval). |
| **Credentials** | `LARK_APP_ID` / `LARK_APP_SECRET` (+ wiki token when used). |

---

### 10. External companion (documented, not Python)

| Feature | What it does |
|---------|----------------|
| **Google Form → Lark wallet** | Apps Script (`scripts/google_form_to_lark.gs`) writes form submissions into the wallet bitable on submit. |

---

## Architecture (high level)

```text
Telegram folders / groups
        │
        ▼
 Telethon Userbot (bot.main)
        │
        ├─ FAQ RAG (knowledge/ + LLM)
        ├─ Social / Welcome / Folder auto-add
        ├─ Ops commands (stats / daily / weekly)
        ├─ Learn → knowledge/learned (+ optional Lark Agent KB)
        │
        └─ Workflow
              ├─ Lark webhook / status watch / mark-live
              ├─ Send Google Form → partner group
              ├─ Logo fill → Progress Tracker
              ├─ Form chase (24h missing fields)
              └─ Wallet table → notify / daily digest
```

---

## Quick start

```bash
git clone https://github.com/Toytheboss/delivery-agent.git
cd delivery-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp config/config.yaml.example config/config.yaml
cp config/whitelist.yaml.example config/whitelist.yaml
cp config/qa_testers.yaml.example config/qa_testers.yaml
cp config/ignored_groups.yaml.example config/ignored_groups.yaml
```

Fill `.env` and `config/config.yaml`, then:

```bash
python scripts/login.py
python -m bot.main
```

Production: see [`deploy/README.md`](deploy/README.md) (`delivery-agent.service`).

---

## Layout

```
bot/           Handlers, RAG, welcome, folder auto-add, Lark workflows, metrics, message log
config/        *.example templates only (real YAML is gitignored)
knowledge/     FAQ / docs packs (add private packs locally if needed)
scripts/       Login, Lark KB upsert, Google Form → Lark Apps Script, webhook docs
deploy/        systemd + bootstrap
docs/          Operator notes (whitelist, workflows)
assets/        Optional brand assets for decks / docs
```

---

## Configuration map

Primary file: `config/config.yaml.example`.

| Block | Controls |
|-------|----------|
| `scope` | Folders, pilot, auto-add, refresh interval, group replies |
| `trigger` | Mention/question gate, hint keywords |
| `reply` | Delays, bubbles, relevance threshold, language, FAQ footer |
| `rules` / `safety` | System rules, blocked commercial topics |
| `learn` | Trigger word, scopes, Agent KB table |
| `knowledge` | Directory, chunk size, `top_k` |
| `lark` | Wiki sync on/off + interval |
| `workflow` | Live webhook/watch, form, logo, chase, wallet notify, digest, operators, command aliases |
| `llm` | Provider, model, temperature |
| `telegram` | Session name |
| `metrics` | Counters + message JSONL log retention |
| `welcome` | Keywords, sequences ZH/EN, min messages, scan |

Companion YAML: `whitelist.yaml`, `qa_testers.yaml`, `ignored_groups.yaml`.

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Telethon login |
| `TELEGRAM_PROXY` | Optional `socks5://` / `http://` proxy |
| `LOG_LEVEL` | Logging verbosity |
| `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` | LLM |
| `LARK_APP_ID` / `LARK_APP_SECRET` | Bitable / wiki / digest |
| `LARK_WIKI_TOKEN` | Optional wiki sync |
| `WORKFLOW_LIVE_WEBHOOK_SECRET` | Optional override for live webhook auth |

---

## Ops cheat sheet

| You want… | Do this |
|-----------|---------|
| FAQ in a partner group | Ensure group is in a scoped folder; ask with `@` or a clear question |
| Greet a new partner group | Title matches welcome keywords; add the delivery account to the group |
| Mark project live + send form | Operator sends `项目已上线` (or alias) in the group |
| Resend form manually | `/send_form` / `发送上线表单` |
| See last 24h ops | `交付日报` / `/daily` |
| See last 7 days summary | `交付周报` / `/report` |
| Full counters | `交付统计` / `/stats` |
| Web dashboard / settings | `http://HOST:8787/dashboard?token=…` and `/dashboard/settings?token=…` |
| Teach the bot a fact | QA tester: `学习 …` (or configured trigger) |
| Audit ask/reply text | Read `data/message_logs/messages-YYYY-MM-DD.jsonl` on the server |

More operator detail: [`docs/delivery-operator-whitelist.md`](docs/delivery-operator-whitelist.md).

---

## Security

- Do **not** commit `.env`, Telegram sessions, or real `config/*.yaml`
- Keep private product/brand knowledge out of public forks if needed
- Follow Telegram ToS for userbots
- Prefer webhook + status watch over folder-wide form polling on large estates (avoids Telegram flood waits)

---

## License

Private / internal use.
