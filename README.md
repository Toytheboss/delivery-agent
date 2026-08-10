# Delivery Agent

Telegram **Userbot** + Lark workflow automation for project delivery: FAQ replies, group welcome, live-on-mainnet form dispatch, logo fill, wallet notify, and daily reports.

> This is a **Userbot** (personal Telegram account), not a BotFather bot.  
> Secrets stay local: `.env`, `*.session`, and real `config/*.yaml` are never committed.

## Features

| Area | What it does |
|------|----------------|
| Scope | Listen only to configured Telegram folders / pilot groups |
| FAQ | RAG answers from `knowledge/`; stay silent when unsure |
| Welcome | Greet new partner groups; optional auto-folder add |
| Live workflow | Lark webhook/poll → send onboarding form + fill logo |
| Status watch | Track deploy / live transitions for daily ops reports |
| Wallet | Google Form → Lark table sync (Apps Script) |
| Ops commands | Daily/weekly reports, mark-live, send-form |

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

## Layout

```
bot/           Core handlers, RAG, Lark workflows, metrics
config/        *.example templates only
knowledge/     Sample FAQ (add your own privately)
scripts/       Login, Lark sync, webhook docs
deploy/        systemd + bootstrap
docs/          Operator notes
```

## Security

- Do not commit `.env`, sessions, or real config YAML
- Keep product knowledge / brand docs out of public forks if needed
- Follow Telegram ToS for userbots

## License

Private / internal use.
