# Delivery Agent — 服务器 24/7 部署

本目录提供 systemd 单元与 Ubuntu 引导脚本。密钥只放在服务器上的 `.env`，**不要**提交到 Git。

> **切流原则**：同一 Telegram session 不能同时在本机与服务器运行。先在服务器装好并验证，再停本机 bot，最后 `systemctl start`。

---

## 1. VPS 要求

| 项 | 建议 |
|----|------|
| OS | Ubuntu 22.04 / 24.04 LTS |
| CPU / 内存 | 1 vCPU / 1–2 GB（Playwright 抓 logo 时建议 ≥2 GB） |
| 磁盘 | ≥10 GB |
| 网络 | 能访问 Telegram、DeepSeek/OpenAI、飞书 API；若机房拦 TG，需配置 `TELEGRAM_PROXY` |
| 端口 | 对公网开放 **8787/tcp**（或反向代理到该端口），供飞书 Live Webhook |
| 权限 | 有 sudo 的 SSH 用户 |

---

## 2. 需要拷到服务器的文件

目标目录示例：`/opt/delivery-agent`（与 `delivery-agent.service` 一致）。

### 必拷（含密钥 / 会话，勿入 Git）

| 本地路径 | 说明 |
|----------|------|
| `.env` | API Key、Webhook secret 等 |
| `delivery_session.session` | Telethon 登录态（若有 `.session-journal` 一并停 bot 后再拷） |
| `config/config.yaml` | 运行配置 |
| `config/whitelist.yaml` | 白名单 |
| `config/qa_testers.yaml` | QA 测试账号 |
| `config/ignored_groups.yaml` | 忽略群（若本地有） |

### 代码与知识库

| 路径 | 说明 |
|------|------|
| 整个仓库（或 `git clone` 后检出） | `bot/`、`requirements.txt`、`scripts/` 等 |
| `knowledge/` | FAQ / 帮助中心；含 `knowledge/learned/` 若需保留学习结果 |
| `data/`（可选） | 工作流运行时状态；没有可让服务端新建 |

### 不要拷

- `.venv/`（在服务器重建）
- `.git` 可拷可不拷；生产更推荐服务器 `git clone` + 单独 scp 密钥文件
- 任何密钥写进文档或聊天记录

示例（在**本机**执行，先确认已停本地 bot 再拷 session）：

```bash
APP=botuser@YOUR_VPS_IP
DIR=/opt/delivery-agent

# 代码（无密钥）
rsync -avz --exclude '.venv' --exclude '.git' --exclude '.env' \
  --exclude '*.session' --exclude '*.session-journal' \
  "./" "$APP:$DIR/"

# 密钥与会话（权限收紧）
scp .env "$APP:$DIR/.env"
scp delivery_session.session "$APP:$DIR/"
scp config/config.yaml config/whitelist.yaml config/qa_testers.yaml \
  config/ignored_groups.yaml "$APP:$DIR/config/"
```

服务器上：

```bash
sudo chown -R botuser:botuser /opt/delivery-agent
sudo chmod 600 /opt/delivery-agent/.env
sudo chmod 600 /opt/delivery-agent/delivery_session.session
```

---

## 3. 服务器初始化

```bash
cd /opt/delivery-agent   # 或先把仓库放到该路径
sudo bash deploy/bootstrap.sh /opt/delivery-agent

sudo -u botuser bash -lc '
  cd /opt/delivery-agent
  python3 -m venv .venv
  . .venv/bin/activate
  pip install -U pip
  pip install -r requirements.txt
  playwright install chromium
'
# 若缺系统库：
sudo /opt/delivery-agent/.venv/bin/playwright install-deps chromium
```

若服务器上没有 session，用交互登录（需能收验证码）：

```bash
sudo -u botuser bash -lc 'cd /opt/delivery-agent && . .venv/bin/activate && python scripts/login.py'
```

---

## 4. systemd

```bash
sudo cp /opt/delivery-agent/deploy/delivery-agent.service /etc/systemd/system/delivery-agent.service
# 按需改 User / WorkingDirectory / EnvironmentFile
sudo systemctl daemon-reload
sudo systemctl enable delivery-agent
# 先别 start：见下一节切流
```

单元要点（见 `deploy/delivery-agent.service`）：

- `WorkingDirectory=/opt/delivery-agent`
- `EnvironmentFile=/opt/delivery-agent/.env`
- `ExecStart=.../.venv/bin/python -m bot.main`
- `Restart=always`

常用命令：

```bash
sudo systemctl start delivery-agent
sudo systemctl status delivery-agent
sudo journalctl -u delivery-agent -f
```

兼容说明：仓库里仍保留旧名 `deploy/delivery-agent.service`；新部署请用 `delivery-agent.service`。

---

## 5. 停本机 bot（切流，需你确认后再做）

1. 确认服务器依赖、`.env`、config、session、Playwright 都已就绪。
2. **停止本机**正在跑的 `python -m bot.main`（Ctrl+C 或结束对应进程）。
3. 若本机刚写过 session，再 scp 一次最新 `delivery_session.session`。
4. `sudo systemctl start delivery-agent`
5. 看日志无报错，并用测试群/`/health` 验证。

未确认前请保持本机运行，避免双开导致掉线。

---

## 6. Playwright

Logo 抓取使用 Chromium（`bot/project_logo.py`）。服务器上必须：

```bash
playwright install chromium
# 缺库时：
sudo .venv/bin/playwright install-deps chromium
```

无头环境即可；不需要桌面 GUI。

---

## 7. 飞书 Live Webhook URL

Bot 默认监听（见 `config.yaml`）：

- Host: `0.0.0.0`
- Port: `8787`
- Path: `/workflow/live`
- Secret: 环境变量 `WORKFLOW_LIVE_WEBHOOK_SECRET`（写在服务器 `.env`）

健康检查：

```bash
curl -sS http://127.0.0.1:8787/health
```

公网回调（二选一）：

1. **防火墙放行 8787** + 固定 IP/域名：
   ```text
   https://YOUR_DOMAIN_OR_IP:8787/workflow/live?secret=<与.env一致>
   ```
2. **Nginx/Caddy 反代**到 `127.0.0.1:8787`，对外 443，再把飞书自动化 URL 改成新地址。

本机调试用的 `trycloudflare.com` 临时隧道在 24/7 服务器上应换成稳定域名或 IP。详细飞书配置见 `scripts/LARK_LIVE_WEBHOOK.md`。

改 URL 后在飞书自动化里更新，并 POST 自测一次。

---

## 8. 上线检查清单

- [ ] VPS 系统与时区、SSH 密钥登录就绪
- [ ] `bootstrap.sh` + venv + `pip install -r requirements.txt` 成功
- [ ] `playwright install chromium`（及必要时 `install-deps`）成功
- [ ] 服务器存在 `.env`（权限 600），无密钥进 Git
- [ ] `config/*.yaml` 已从本机同步
- [ ] `delivery_session.session` 已就位（或 `login.py` 完成）
- [ ] systemd 单元已 install / enable
- [ ] **本机 bot 已停止**（仅一处在线）
- [ ] `systemctl start delivery-agent` 后 `journalctl` 正常
- [ ] `curl http://127.0.0.1:8787/health` 返回 ok
- [ ] 飞书 Webhook 已改为服务器公网 URL
- [ ] 测试群 @ 或问答一条；可选触发一次「主网上线」流程

---

## 9. 故障速查

| 现象 | 排查 |
|------|------|
| 服务秒退 | `journalctl -u delivery-agent -n 100`；检查 `.env` / session / Python 版本 |
| 连不上 Telegram | 出口网络或 `TELEGRAM_PROXY` |
| Webhook 飞书失败 | 安全组/防火墙、路径与 secret、HTTPS 证书 |
| Logo 抓取失败 | Playwright Chromium 与系统依赖是否安装 |
