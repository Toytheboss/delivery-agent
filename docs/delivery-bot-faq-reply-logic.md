# 交付 Bot：FAQ 自动回复逻辑说明

面向交付 / 运维：说明项目群里「什么时候会自动答、什么时候沉默」。  
依据当前代码（`bot/handlers.py`、`bot/triggers.py`、`bot/rag.py`）与生产配置（约 2026-08-10）。

生产交付号：`@Roy4by4` · 服务：`delivery-agent`

---

## 1. 总览（一条消息会经过哪些门）

```text
新消息
  │
  ├─ 忽略群？ → 静默
  ├─ BD 忽略名单（且非操作员口令）？ → 静默
  ├─ 操作员口令 / 周报 / absorb？ → 走对应工作流（非 FAQ）
  │
  ├─ 是否在 FAQ 回复范围内？
  │     · Delivery Folder 内群 + group_replies_enabled
  │     · 或 QA 私聊 / QA 测试群
  │     · 试点开启时还需在 pilot 名单内（当前试点已关 = Folder 内全量）
  │
  ├─ 是否该处理这条消息？（触发条件）
  │     · 空消息 / 仅 @人 / 应和句（Will do、收到…）→ 不处理
  │     · QA 测试号：非应和即可处理
  │     · 普通用户：@交付号 或 像问句 或 命中 hint 关键词
  │
  ├─ 同群同用户冷却中？ → 静默（生产约 120 秒）
  │
  └─ generate_reply（检索 + LLM）
        · 敏感话题？ → 静默
        · 检索最高分 < 0.28？ → 静默
        · LLM 输出 NEEDS_HUMAN / 空 / 只剩反问？ → 静默
        · 否则：延迟约 10 秒后发气泡，再发 FAQ 页脚
```

要点：**先过触发门，再过相关度门，再过 LLM 门。** 任一门不过 = 不回。

---

## 2. 哪些路径不是 FAQ

以下命令由操作员 / 交付号 / QA 触发，**不走**相关度与 FAQ 页脚逻辑：

| 类型 | 示例口令 |
|------|----------|
| 主网上线 | `项目已上线`、`/mark_live`… |
| 仅发表单 | `发送上线表单`、`/send_form`… |
| 数据报告 | `交付周报`、`/stats`… |
| 知识写入 | 消息含 `absorb` / 学习触发词（权限另有限制） |

详见：`docs/delivery-operator-whitelist.md`

---

## 3. FAQ 回复范围（在哪才能答）

同时满足（普通项目方）：

1. `group_replies_enabled: true`
2. 群在 Delivery Folder 内（`FolderScope`）
3. 试点：`pilot_enabled: false` 时 Folder 内全量；为 `true` 时仅 `pilot_groups`

额外始终可答：

- QA 测试号私聊交付号
- 配置的 QA 测试群

不在范围内 → **完全不进 FAQ**。

---

## 4. 触发条件（会不会进检索）

配置：`trigger.require_mention_or_question: true`（生产开启）

### 4.1 一律不进 FAQ

- 空文本
- 只有 `@某人`、没有实质内容
- **应和 / 寒暄**（`is_ack_or_chitchat`），例如：  
  `Will do!`、`Got it`、`Thanks`、`好的`、`收到`、`明白`、`没问题` 等  
  （即使被 @、即使是 QA 号，也不进 FAQ）

### 4.2 普通用户：满足任一即处理

| 条件 | 说明 |
|------|------|
| @交付号 / 回复交付号的消息 | `mentions_me` |
| 像问句 | `looks_like_question` |
| 命中 hint 关键词 | 如报价、价格、pricing、deadline…（仅触发，不直接当答案） |

**像问句**大致规则：

- 长度 ≥ 8
- 非应和句
- 含 `?` / `？`，或英文以 what/how/… 等起问，或 `will/do/is…` + 主语（避免 `Will do!` 误判）
- 或含中文疑问成分：吗、怎么、如何、什么、哪、是否…

### 4.3 QA 测试号

非「仅 @ / 应和」时，在 FAQ 范围内可直接处理（不必 @）。

---

## 5. 冷却与发送节奏（生产值）

| 项 | 配置键 | 生产值 | 作用 |
|----|--------|--------|------|
| 同群同用户冷却 | `reply.rate_limit_seconds` | **120** | 上次成功回复后 120 秒内不再答 |
| 首条延迟 | `reply.reply_delay_seconds` | **10** | 算完后约等 10 秒再发（不像秒回机器人） |
| 多气泡间隔 | `reply.bubble_gap_seconds` | **30** | 用 `---` 拆成多段时，段间隔约 30 秒 |
| FAQ 页脚 | `reply.footer_enabled` | **true** | 成功自动回复后追加中/英页脚 |

QA 模式（测试号 / 测试群）：**无冷却延迟、无气泡间隔**（便于联调）。

---

## 6. 检索与相关度（核心阈值）

配置：`reply.min_relevance_score: **0.28**`

流程：

1. 判定回复语言（`auto`：跟提问走中/英）
2. 若问题命中 `blocked_topics`（若配置）→ 静默
3. （有 LLM 时）可先把口语问题改写成检索关键词
4. 本地知识库 `knowledge/` 检索，取 `top_k`（默认 4）
5. 钱包 SDK 等专题会做 on-topic 过滤，减少跑题
6. 若改写后结果偏弱，会再搜一遍原文并合并
7. **最高分 `< 0.28` → 静默**（日志：`below min relevance`）
8. 无可用 on-topic 命中 → 静默（`no on-topic knowledge`）

分数大致为检索相似度（0～1）。**0.28 是「能不能拿资料去问 LLM」的门槛，不是「一定会回」。**

---

## 7. LLM 生成与静默

有 API Key 时（生产用 DeepSeek 等）：

1. 用命中资料拼上下文 + 系统提示（口语、禁反问、禁编造、资料不够只输出 `NEEDS_HUMAN`）
2. 再叠加 `config.yaml` 的 `rules`
3. 结果处理：
   - 含 `NEEDS_HUMAN` 或空 → **静默**
   - 去掉反问尾巴后变空 → **静默**
   - 否则：尽量补上资料里有、回复漏掉的链接 → **发送**

无 API Key 或 LLM 失败：走检索 fallback（贴标签答案片段），仍受相关度门槛约束。

---

## 8. 发出去长什么样

1. 按 `---` 拆成 1～多条短气泡  
2. 第一条 `reply` 原消息；后续为独立消息  
3. FAQ 成功后追加页脚（欢迎 / mark-live / 发表单不加页脚）  
4. 记一次冷却；埋点：`faq_reply_sessions` / `faq_bubbles_sent` / `faq_footer_sent`

---

## 9. 常见「为什么没回 / 乱回」对照

| 现象 | 常见原因 |
|------|----------|
| 完全没反应 | 不在 Folder；被 ignore；不是问句也没 @；应和句；冷却中；相关度 &lt; 0.28；LLM 选 NEEDS_HUMAN |
| 不该回却回了 | 曾被误判为问句（如旧逻辑把 `Will do!` 当 will 问句）——已收紧 |
| 答非所问 | 检索擦边命中但仍 ≥ 0.28，LLM 未输出 NEEDS_HUMAN；需改知识库或再收紧提示 |
| 话术奇怪 | 知识库原句 + 口语化提示叠加；应改 KB / 系统提示，而不是只调阈值 |

---

## 10. 生产关键参数速查（FAQ）

| 参数 | 当前值 |
|------|--------|
| `pilot_enabled` | `false`（Folder 内全量） |
| `require_mention_or_question` | `true` |
| `min_relevance_score` | **0.28** |
| `rate_limit_seconds` | 120 |
| `reply_delay_seconds` | 10 |
| `bubble_gap_seconds` | 30 |
| `footer_enabled` | true |
| `language` | auto |

配置文件：服务器 `/opt/delivery-agent/config/config.yaml`  
改完需：`systemctl restart delivery-agent`

---

## 11. 相关代码入口

| 模块 | 职责 |
|------|------|
| `bot/handlers.py` | 范围、冷却、延迟、发气泡与页脚 |
| `bot/triggers.py` | 问句 / @ / 应和 / hint 触发 |
| `bot/rag.py` | 检索、相关度、LLM、NEEDS_HUMAN |
| `bot/knowledge.py` | 本地知识库检索打分 |

操作员口令与白名单：`docs/delivery-operator-whitelist.md`  
整体交付链路演示：`docs/delivery-automation-demo.html`
