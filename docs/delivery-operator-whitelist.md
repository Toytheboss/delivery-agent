# 交付 Bot 操作员白名单：权限与使用说明

面向交付同学：谁能触发交付动作、发什么口令、和「BD 忽略名单」有何区别。

生产交付号：`@Roy4by4`（服务器 systemd 服务 `delivery-agent`）。

---

## 1. 「白名单」指什么

这里说的白名单 = **workflow 操作员（operators）**，配置在服务器：

`/opt/delivery-agent/config/config.yaml` → `workflow.operators`

当前操作员（2026-08-10）：

| Telegram | 说明 |
|----------|------|
| `@Josh_0zh` | 交付操作员 |
| `@Xuanxi_zhao` | 交付操作员 |
| `@Roy4by4` | 交付号本人（始终可用，无需写进 operators） |
| `@Trent_one` | QA 测试号（`qa_testers.yaml`，权限与操作员类似） |

普通项目方、未列入上表的同事：**发口令无效**。

---

## 2. 操作员能做什么

| 能力 | 说明 |
|------|------|
| 标记主网上线 | 改飞书进度表「项目状态」→ 主网上线，并触发 Google 表单 + Logo 抓取 |
| 仅发上线表单 | 不改飞书状态，只在当前群发 Google 表单 |
| 交付周报 / 统计 | 拉管理层短版周报或运维明细 |
| 不受「必须在 Delivery Folder」限制 | 任意群发口令即可（群名需能对上飞书项目名） |

操作员发口令时，即使曾在 BD 忽略名单里，**上线/发表单口令仍会生效**（已从忽略名单移除的操作员则完全按正常账号处理）。

---

## 3. 口令一览（须整句完全一致）

### 3.1 主网上线（改状态 + 发表单 + 抓 Logo）

在**对应项目群**发下面任一整句：

```text
项目已上线
```

```text
上线完成
```

```text
/mark_live
```

```text
mark live
```

行为：

1. 按**当前群名**匹配飞书「项目名称 Project Name」
2. 将「项目状态」设为：`Mainnet Live`
3. 立即在该群发送 Google 上线表单
4. 尝试根据「已上线链接 / 项目链接」抓 Logo 写入飞书（失败不重试）

注意：

- 不会自动「抓钱包地址」；地址由项目方填表单后同步进钱包表
- 群名与飞书项目名对不上会回复匹配失败，不会乱改别的行
- 多出来的字（如「请项目已上线」）**不会触发**

### 3.2 仅发送上线表单（不改飞书状态）

```text
/send_form
```

```text
发送上线表单
```

```text
send form
```

### 3.3 数据报告

私聊交付号，或在交付号所在群，由操作员/交付号/QA 发送：

| 口令 | 内容 |
|------|------|
| `交付周报` / `交付报告` / `/report` | 管理层短版（触达 / 表单 Logo / 知识 / 钱包存量）；统计窗口为**过去7天** |
| `交付日报` / `/daily_report` | 短版日报；统计窗口为**过去24小时** |
| `交付统计` / `/stats` | 运维明细长版（含过去7天 / 过去24小时） |

周报 / 日报**不会定时自动推**，只有发口令才回。

---

## 4. 和另外几条「上线触发」的关系

同一套结果（状态 live → 表单 + Logo），有多条入口，可并存、互相去重：

| 入口 | 谁触发 | 延迟 |
|------|--------|------|
| **群口令（本文）** | 操作员在项目群发关键词 | 立刻 |
| 飞书改状态 → Webhook | 有人在进度表改成主网上线 | 秒级（自动化配好时） |
| 状态侦测 | 表上已是 live，但 webhook 未打到 | 约 1 分钟内 |

交付侧日常可以**只在 Telegram 发口令**，不必再手动改飞书；口令会改表。

---

## 5. 和「BD 忽略名单」的区别

文件：`config/whitelist.yaml` → `ignore_users`  
（文件名含 whitelist，实际是 **忽略名单 / 黑名单**：这些人发言，Bot **不做 FAQ 自动回复**。）

- BD / 内部拉群账号通常在此列表，避免刷屏式自动答疑
- **操作员白名单**在 `config.yaml` 的 `operators`，管的是交付口令权限
- 某人若既要交付口令、又曾在忽略名单：应加入 `operators`，并视需要从 `ignore_users` 移除（如 `@Xuanxi_zhao`）

---

## 6. 如何新增 / 移除操作员

在服务器编辑（需有权限）：

```text
/opt/delivery-agent/config/config.yaml
```

示例：

```yaml
workflow:
  operators:
    - username: Josh_0zh
    - user_id: 1359647881   # 可选但更稳
      username: Xuanxi_zhao
    - username: NewPerson
```

然后：

```bash
systemctl restart delivery-agent
```

启动日志中应出现类似：

```text
Workflow operator @xxx -> user_id=...
```

若此人还在 `whitelist.yaml` 的 `ignore_users` 且希望其发言可被 FAQ 处理，请同时从忽略名单删除对应条目后重启。

---

## 7. 给交付同学的最短说明（可转发）

1. 用你的号进**项目对接群**（群名尽量带项目名，与飞书一致）  
2. 需要上线收尾时，单独发一行：`项目已上线`  
3. Bot 会改飞书状态、发表单、尝试填 Logo  
4. 只要表单时发：`发送上线表单`  
5. 看周数据时私聊 `@Roy4by4` 发：`交付周报`  

当前可操作账号：`@Josh_0zh`、`@Xuanxi_zhao`，以及交付号本人。

---

## 8. 相关配置位置（运维）

| 项 | 路径 |
|----|------|
| 操作员 / 口令列表 | `config/config.yaml` → `workflow.operators` / `mark_live_commands` / `manual_commands` |
| BD 忽略名单 | `config/whitelist.yaml` → `ignore_users` |
| QA 测试号 | `config/qa_testers.yaml` |
| 飞书 Webhook 说明 | `scripts/LARK_LIVE_WEBHOOK.md` |
| 服务 | `systemctl status delivery-agent` |
