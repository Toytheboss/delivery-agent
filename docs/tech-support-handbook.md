# Tech Support 答疑升级 — 功能说明与操作手册

## 一、功能说明

把项目方 TG 群里的技术问题，经交付/QA 一键升级到 Lark 答疑群；技术员回复后，Bot 自动 quote 原问题回传到对应项目群，并可选把 Q&A 写入知识库 / Agent 词条库。

| 环节 | 说明 |
|------|------|
| 触发 | Josh（交付号）或 Roy（QA 号）在项目群 **回复/quote 问题** 后发送 `tech support` |
| 推送 | 发到 Lark「交付 & 技术 & 项目方答疑群」，@ **Cisco-BE**、**Roy** |
| 回传 | 技术员 **回复该工单消息**；Bot 用 ticket 映射到原 TG 群，quote 原问题发出答案 |
| 学习 | 回传成功后，自动学习「原问 + 答案」，写入本地 `learned/`，并同步到 **Agent 词条库** |

精准回群依赖 ticket（`tg_chat_id` + 原消息 `message_id`），不靠群名匹配。

---

## 二、操作手册

### 1. 交付 / QA：升级问题

1. 在项目方 TG 群找到技术问题。  
2. **长按 / 右键 → 回复（quote）** 该消息。  
3. 发送（任选其一）：
   - `tech support`
   - `/tech`
   - `techsupport`  
4. 看到类似提示即成功：  
   `Escalated to Lark tech support as T-YYYYMMDD-XXXX …`  
5. 未 quote 就发指令时，Bot 会提示先回复原问题。

> 仅 **Josh / Roy 本账号**发出的指令会触发（避免双端重复建单）。

### 2. 技术员（Cisco / Roy）：在 Lark 作答

1. 打开 **交付 & 技术 & 项目方答疑群**。  
2. 找到带 `【Tech Support】T-…` 的工单（会 @ 你）。  
3. **直接回复该条消息** 填写答案（不要另开一条无关消息）。  
4. 约数十秒内（已开轮询；若配置了事件订阅则更快），答案会出现在原项目 TG 群，并 quote 原问题。  
5. 回传正文会去掉飞书 `@_user_1` 之类占位符。

### 3. 自动学习（无需操作）

工单回传 TG 成功后自动执行：

- 本地知识库：`knowledge/learned/learned_*.md`
- Lark Agent 词条库：分类「Learned / 自动学习」
- 同一 `ticket_id` 只学一次；答案过短（默认 &lt; 20 字）不学

### 4. 常见问题

| 现象 | 处理 |
|------|------|
| `Failed to escalate…` | 看服务日志；常见为共享目录权限（`/opt/botchain-shared`） |
| Lark 有工单但 TG 不回 | 确认是否 **回复工单本身**；等待一轮轮询（约 45s） |
| 两边都建了单 | 只用 Josh 或 Roy 其中一个号发 `tech support` |
| 想改 @ 人员 | 改配置 `workflow.tech_support.assignees` 后重启 bot |

### 5. 相关配置（运维）

- 配置：`config.yaml` → `workflow.tech_support`
- 工单状态：`/opt/botchain-shared/tech_support_tickets.json`
- 服务：`botchain-qa.service`（Roy）、`delivery-agent.service`（Josh）
- 可选秒级回传：Lark 开放平台给 Roy 应用订阅 `im.message.receive_v1`，请求地址  
  `http://8-222-166-120.sslip.io/workflow/tech-support/event`
