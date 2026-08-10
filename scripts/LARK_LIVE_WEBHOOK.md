# 飞书改「主网上线」→ 立刻发 Google 表单 + 抓 Logo

用白话讲：飞书改状态时，飞书会打一个「门铃」到 bot；bot 收到后马上发群、抓 Logo。

**生产（阿里云）**：bot 本机监听 `8787`；因安全组通常只放行 22，公网入口用 Cloudflare 临时隧道  
`delivery-live-tunnel`（`https://*.trycloudflare.com`）。完整 URL 见服务器  
`/opt/delivery-agent/data/live_webhook_public_url.txt`。  
隧道重启后域名可能变，需同步改飞书自动化 URL。长期建议：安全组放行 `8787` 后改用  
`http://<服务器公网IP>:8787/workflow/live?secret=...`。

**本机调试**：飞书打不到 `127.0.0.1`，需另开 `cloudflared` 隧道（见步骤 B）。

---

## 你现在要做的 3 件事

| 步骤 | 做什么 | 做完的标志 |
|------|--------|------------|
| A | 保证 bot 在跑 | 浏览器或终端访问 `http://127.0.0.1:8787/health` 返回 `ok` |
| B | 开一条公网隧道 | 终端里出现 `https://xxxx.trycloudflare.com` |
| C | 在飞书进度表建自动化 | 改一次状态后，项目群立刻收到表单 |

密钥已在项目 `.env` 的 `WORKFLOW_LIVE_WEBHOOK_SECRET`（不要发到群里）。

---

## A. 确认 bot 已开着

在项目目录启动（若已在跑可跳过）：

```bash
cd "/Users/roy/Documents/Delivery/Delivery Agent"
source .venv/bin/activate
python -u -m bot.main
```

另开一个终端测：

```bash
curl http://127.0.0.1:8787/health
```

应看到类似：`{"ok": true, "service": "delivery-live-webhook"}`。

---

## B. 开公网隧道（每次本机调试都要开着）

新开一个终端，执行：

```bash
# 若命令找不到，用完整路径：
~/bin/cloudflared tunnel --url http://127.0.0.1:8787
```

等到类似输出：

```text
Your quick Tunnel has been created! Visit it at:
https://随机一串.trycloudflare.com
```

**复制这个 https 地址**，下面叫它 `公网地址`。  
这个窗口不要关；关掉后飞书就打不通了。

拼出完整回调 URL（把密钥换成 `.env` 里的值）：

```text
https://随机一串.trycloudflare.com/workflow/live?secret=你的WORKFLOW_LIVE_WEBHOOK_SECRET
```

本机先自测（在项目目录）：

```bash
cd "/Users/roy/Documents/Delivery/Delivery Agent"
set -a && source .env && set +a
# 把下面 PUBLIC 换成你的 trycloudflare 地址
PUBLIC="https://随机一串.trycloudflare.com"
curl -sS -X POST "$PUBLIC/workflow/live?secret=$WORKFLOW_LIVE_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"project_name":"AVEC"}'
```

返回 JSON 里有 `form` / `logo` 字段即表示链路通了。

---

## C. 在飞书里建自动化（只配一次）

> 生产环境另有 **live-status-watch**（约每 60s 侦测「新变 live」），即使本步未配也不会再漏单。  
> 自动化配好后可实现秒级触发；URL 见服务器 `data/live_webhook_public_url.txt`。

1. 打开 **生态项目进度表** → 右上角 **自动化 / Automations**。
2. **新建自动化**，名称建议：`主网上线 → 交付表单+Logo`。
3. **触发条件**选：
   - 「当记录中的字段值变更时」/ When a record matches conditions  
   - 表：`Progress Tracker…`（`tbl5wXOwCptng06w`）  
   - 字段：`项目状态`  
   - 变为 / 等于：`Mainnet Live`
4. **添加动作**：**发送 HTTP 请求**（Send HTTP request）。
5. 填：
   - 方法：`POST`
   - URL：复制服务器文件  
     `/opt/delivery-agent/data/live_webhook_public_url.txt`  
     整行粘贴（含 `?secret=...`）
   - Header：`Content-Type: application/json`
   - Body（优先 record_id；编辑器里插入变量）：

```json
{
  "record_id": "{{记录 ID}}",
  "project_name": "{{项目名称 Project Name}}"
}
```

若没有「记录 ID」变量，可只用：

```json
{
  "project_name": "{{项目名称 Project Name}}"
}
```

6. **启用**并保存。

当前进度表已有的自动化（API 可见）不含本 webhook；需新建一条，不要改「恭喜海报 / 主网上线时间」等旧流程。

### 验收

在进度表里把某个测试项目（有对应 TG 群、尚未发过表单的）状态改成主网上线：

- 对应项目群应马上收到 Google 表单文案  
- 飞书「项目logo」会尝试自动填充（官网抓不到图则会失败且不重试）

---

## 不想配飞书时的备用办法（立刻可用）

在项目 TG 群发（需是交付号 / 配置过的操作员）：

```text
项目已上线
```

或：

```text
/mark_live
```

同样会立刻改状态 + 发表单 + 抓 Logo，**不需要隧道和自动化**。

---

## 常见问题

**1. 飞书自动化保存失败 / 请求失败**  
多半是隧道没开，或 URL / secret 抄错。先用步骤 B 的 `curl` 测通。

**2. `trycloudflare.com` 地址每次启动都变**  
临时隧道会变。每次重启 `cloudflared` 后，去飞书自动化里更新 URL。  
长期方案：把 bot 放到有固定域名的服务器，或配置 Cloudflare 命名隧道。

**3. 返回 `no_group`**  
项目名称和 TG 群名对不上。把群名改成带项目名（如 `Delivery Agent x AVEC`），或对齐飞书「项目名称」。

**4. Logo 失败**  
和触发方式无关，是官网抓不到图；需人工上传或换更干净的官网链接。

**5. 想恢复以前的 5 分钟轮询**  
`config/config.yaml` 设 `form_logo_poll_enabled: true` 后重启 bot。
