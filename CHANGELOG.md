# 迭代更新记录

类似应用商店的版本说明：按时间倒序记录 Delivery Agent 的功能新增、优化与修复。  
每次有实质功能推送时，请在本文件顶部追加一条记录。

格式约定：

- **日期**：以推送/上线日为准（UTC+8）
- **标题**：一句话概括本轮重点
- **分类**：新增 / 优化 / 修复

---

## 2026-09-22 · Quote `pr support` 覆盖正式表 KPI 2

### 新增
- 在项目 TG 群 quote PR 消息，回复 `pr support`，把链接覆盖写入正式进度表 `KPI 2 - PR 新闻链接验证`
- 写入成功后通知 Botchain Delivery 群；TG / Lark 文案均为英文
- 不改「新闻验证结果」；群对不上或一对多时不写表

---

## 2026-09-22 · 一对多群名改为能认定就自动发

### 修复
- 短项目名不再因为 `sent`/`dex`/`card` 撞上别的群就整批标成一对多
- 同名重复群（含大小写、迁过的 `-100` 超群）收成一个；`Link Chain` 和 `Linkchain` 不再被当成同一群
- `BOT Chain Pulse` 仍然对不上

---

## 2026-09-21 · 项目名匹配、表单字段与 verify 口径对齐线上

### 优化
- 识别 CloudChain / BOTLatch 这类粘写，以及括号、`.fi`、web3 app、and、复数 Markets
- 「Space → Space Runners」短名防配错保留；不再把 Archon、Nexar Network 等唯一群误判成对不上
- 表单催收 / 钱包回写跟上新谷歌表单：简介、Twitter、`Mainnet Contract Addresss`
- `form_chase_max_reminders` 默认 7 次

### 修复
- `botsea` 不再误配 `botseal`；`Bountyhunter` / `Agent Bazaar` 不再误配 BountyBoard、AgentX
- `check if verified` / 短句 `verified` 也会进 Lark verify 提醒

---

## 2026-09-17 · 表单催收最多 7 次

### 优化
- `form_chase_max_reminders` 由 4 调整为 7，未填完的项目可继续催

---

## 2026-09-17 · Logo 改回原图优先

### 优化
- 先下载 HTML / favicon / manifest / 常见路径里的原图（质量门槛丢掉过小图标）
- 没有可用文件再用 Playwright 截真实渲染
- CSS `.brand-mark` 合成仅作最后兜底

---

## 2026-09-17 · BotFundMe CSS 品牌标可抓取

### 修复
- Logo 抓取支持 CSS `.brand-mark` 渐变圆（无 `<img>` 的站点）
- `data:image/svg` favicon 不再被 href 里的 `>` 截断
- Playwright 失败改为 warning，避免静默跳过

---

## 2026-09-16 · 禁止匹配规则变更后重发历史 live 表单

### 修复
- 短词项目名（如 `Sent`）只要有多个群包含该词，继续视为歧义，不得因过滤后只剩一个群就自动发送
- compact alias 至少要多 3 个字母，避免 `Botsea` 误绑 `Botseal`
- 同一 TG 群已发过上线表单则不再发第二条

---

## 2026-09-16 · 短项目名不得误配更长的 TG 群

### 修复
- `Space` 不再匹配 `BOT Chain | Space Runners`：标题多出独立产品词时拒绝自动绑定
- 表单催收发送前复核群名，错配立即取消；已停掉 Space Runners 上的错误催收

---

## 2026-09-16 · 表单催收勿命中未填完的重名钱包行

### 修复
- 钱包表存在 `Bot Launch` / `BotLaunch` 等同名变体时，催收改为选填写最完整的一行，避免已提交项目仍被催

---

## 2026-09-15 · 防止 config_loader 再丢关键开关

### 优化
- `load_config()` 启动时校验 `verify_alert_*` / `trusted_auto_learn_*` / `tech_support_*`，缺字段直接报错，不再静默当成关闭
- verify 推送若发现字段缺失，日志记 `config_field_missing`（不再误报 `disabled`）
- 新增 `scripts/check_critical_config_fields.py`，部署前可本地跑一遍

---

## 2026-09-15 · 阻断博客与跨主题 fallback

### 修复
- LLM 返回 `NEEDS_HUMAN` 后不再被高检索分强制覆盖
- Blog、News、Whitepaper、Crawl 等自由文本知识源禁止作为 Telegram 回复正文
- LLM 不可用时，备用回答仅允许来自白名单内、结构化且与问题主题一致的 FAQ
- 英文问题增加中文重内容拦截，避免跨语言粘贴知识正文
- 修复 Dungeon Cities 询问链上交易定义时误贴 AI Agent 博客的问题

---

## 2026-09-15 · 修复 Verify 推送 disabled

### 修复
- `config_loader` 丢失 `verify_alert_*` 字段导致识别到 verify 却以 `lark=disabled` 跳过；已恢复并回补 Climalink「please verify again」

---

## 2026-09-15 · 表单追缴改每日午夜

### 优化
- 表单追缴与 Logo 链接同步改为每天 `lark_digest_hour`（默认 00:00）各跑一次，与钱包地址 Lark 日报同刻，不再按小时轮询

---

## 2026-09-15 · 表单 Logo 链接同步到进度表

### 新增
- 钱包表 `Project logo`（表单入库的 URL）→ 进度表 `项目logo （链接）`，仅当链接栏为空时写入
- 表单 chase 轮询旁路定时同步；`scripts/sync_logo_links.py` 可一键补齐存量

---

## 2026-09-15 · Logo 字段改名对齐

### 修复
- Lark 进度表 Logo 列改名为「项目logo（文件）」后，配置 `logo_field` 同步更新，避免 `FieldNameNotFound (1254045)`

---

## 2026-09-15 · Mark Live 状态提示只显示英文

### 修复
- Mark live 成功回复里的 `Status:` 不再带 Lark 选项的中文前缀（例如 `主网部署中 Deploying…` → `Deploying on BOT Chain Mainnet`）
- 写入飞书仍用原选项文案，只改 Telegram 展示

---

## 2026-09-14 · 抑制无主题确认句乱答 FAQ

### 修复
- `are you sure??` / `真的吗` / `really?` 这类无具体主题的追问不再进入 FAQ，避免检索漂到无关 gas / Bridge 文案把群聊弄懵
- 短问题 grounding：答案若与问题本身零词重合，即使错误上下文命中 FAQ 也静默
- Query rewrite：对极短追问跳过改写，并拒绝明显「发明产品词」的改写结果

---

## 2026-09-14 · Mark Live 歧义消解（引用回复选项目）

群名模糊匹配撞上多个 Lark 项目时，可在 TG 里一键确认，不必手改飞书状态。

### 新增
- Mark live 出现 `Ambiguous match` 后，**引用该提示**并回复正确项目名，继续改状态 / 发表单 / 补 logo
- 候选只在本次歧义列表内匹配；写错可再 quote 重试（24h 内有效）
- 若配置了 `workflow.tg_chat_id_field`，成功后自动把当前群 ID 写回进度表

### 优化
- Mark live 优先按 Lark 里已填的 TG chat id 精确匹配，再退回群名模糊匹配

### 修复
- （无）

---

## 2026-09-13 · Verify 与 Tech Support 生产热修同步

本轮将线上已验证的热修完整同步进 GitHub，避免「服务器有、仓库没有」。

### 新增
- （无独立新模块；本轮以修复与对齐为主）

### 优化
- Verify 请求识别更宽：支持 `plz`、`verify again`、`can help to verify`、`Can verify` 等常见写法
- 长项目介绍里夹带 `Verify mainnet` 也能触发 Lark 提醒（长度上限与主网公告对齐）
- Tech Support 推送到 Lark 时保留完整 TG 原文，不再截断到 1200 字
- Verify 同群冷却默认改为关闭（`cooldown_hours: 0`），重复催 verify 会立刻再推

### 修复
- Ignore 名单用户的 verify 不再因「群还没进 folder」而漏推 Lark
- Verify 检测提前到 reply scope 判断之前，避免新群漏报
- 飞书富文本（post / `content_v2`）答疑回复解析失败，导致 Cisco 回复无法回传到 Telegram

---

## 2026-09-10 · Tech Support 答疑升级

交付侧可把项目群技术问题一键升级到飞书答疑群，技术回复后再自动 quote 回 TG。

### 新增
- TG：引用问题后发送 `tech support` / `/tech` 创建工单
- Lark：推送到答疑群并 @ 指定技术同学（如 Cisco-BE、Roy）
- Lark 回复工单 → Bot quote 原 TG 问题回传项目群
- 成功回传后自动写入 `knowledge/learned/`，并同步 Agent 词条库
- 操作手册：`docs/tech-support-handbook.md`

### 优化
- 仅由发起升级的账号回传，避免 Roy / Josh 双端重复发送

---

## 2026-09-09 · Verify / 主网提醒与配置整理

把「请核实主网」从 FAQ 里拆出来，转为人工看板 + 飞书交付部提醒。

### 新增
- `please verify` / 主网核实类消息 → Dashboard 人工队列 + Lark【Verify 提醒】
- `config.yaml.example` 补充 `verify_alert_*` 配置说明

### 优化
- QA 回复路由：减少误走 FAQ；ignore / 测试群行为更清晰
- 仓库不再跟踪真实 `config.yaml`，降低密钥与环境配置误提交风险

### 修复
- （配置与路由整理，减少错误自动回复）

---

## 2026-09-07 · 生产代码回同步仓库

### 优化
- 将生产环境最新 Delivery Agent 代码同步回 Git
- 清理生产镜像同步产生的临时/脏文件

---

## 2026-08-21 · 看板与指标对齐线上

### 优化
- 同步线上部署指标与 Dashboard 展示数据

---

## 2026-08-18 · 分析看板与事件留痕

### 新增
- Lark Track「新项目」分析卡片
- 报表支持新群数量统计
- 项目事件中记录全部 Telegram 出站消息
- 系统架构与接口说明文档

### 优化
- 历史回复气泡展示兼容旧数据
- Lark 知识库仅在内容变化时写入，减少无效同步

---

## 2026-08-16 · Dashboard 登录与工作流面板

### 新增
- Dashboard 管理员登录
- API 鉴权强制校验
- 工作流面板对接实时数据
- 项目名 ↔ TG 群模糊匹配能力增强（随 live dashboard 一并同步）

### 修复
- Dashboard 样式表路径错误

---

## 2026-08-15 · 运营日报与问答面板

### 新增
- 运营日报支持 7 天 / 30 天切换
- 日历缩短为 30 天，并提供 7/30 汇总
- 已回答 / 沉默问答合并为同一 Tab 面板
- 日历日维度展示 Logo / 钱包项目明细
- 统计全量交付号出站 Telegram 消息

### 优化
- QA 默认回溯窗口延长到 30 天
- 统计文案区分「全量出站」与「自动回复」

### 修复
- Dashboard 卡在 loading（JS 语法问题）
- 空图表与 24h 日报展示异常
- 日历颜色过洗、移除冗余 exec 视图

---

## 维护说明

1. **有功能推送就写一条**：与代码同一次 PR / commit 更新本文件顶部。  
2. **写给人看**：少写文件名，多写「用户/运营能感知到的变化」。  
3. **仓库入口**：也可在 README「Features」中保持能力总表；本文件专注时间线迭代。
