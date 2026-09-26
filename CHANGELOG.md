# 迭代更新记录

类似应用商店的版本说明：按时间倒序记录 Delivery Agent 的功能新增、优化与修复。  
每次有实质功能推送时，请在本文件顶部追加一条记录。

格式约定：

- **日期**：以推送/上线日为准（UTC+8）
- **标题**：一句话概括本轮重点
- **分类**：新增 / 优化 / 修复

---

## 2026-09-26 · 关掉表单收到推群

### 优化
- Project verification push 不再发 Google Onboarding form received
- 开关默认关，要开再把 `form_received_notify_enabled` 设回 true

---

## 2026-09-26 · project diag 回复去掉 KPI 字样和中文

### 修复
- TG `project diag` 项名改为 Twitter / News/PR / Website 等，不再出现 KPI
- 「满足审核要求」改为英文 `Meets the audit requirement`，进度表和群回复一致

---

## 2026-09-26 · KPI 3 认 BOT Chain 名字

### 优化
- 官网检查看页面有没有 Botchain / BOT Chain，不再对进度表里的项目名
- 项目 logo 不能顶替这条；官链 botchain.ai 和 scan.botchain.ai 仍要可点

---

## 2026-09-26 · 群名粘着 X 也能匹配项目

### 修复
- `traveltochianX botchain` 这种标题不再因为中间的 X 对不上进度表项目名
- 短名如 Space / ArcadeX 仍分开，避免误绑


## 2026-09-26 · KPI 1 / 6 文案列出核验链接和哈希

### 优化
- KPI 1：近 30 天原发不足 5 条时列出全部推文链接；达到 5 条只列最近 5 条，并标注「满足审核要求」
- KPI 6：未达标列出全部钱包和交易哈希；达标列出 3 个钱包和 5 条哈希，并标注「满足审核要求」

---

## 2026-09-26 · KPI 1 文案附最近 5 条原发链接

### 新增
- `twitter diag` / `project diag` 写入「KPI 1 - Twitter运营验证」时，在原有通过/不通过说明下面贴最近 5 条原发推特链接
- 链接用已经拉到的推文 id 拼接，不额外打 X API

---

## 2026-09-26 · KPI 1 用官方 X API 数近 30 天原发

### 新增
- `twitter diag` / `project diag` 在配了 `X_BEARER_TOKEN`（或 API Key + Secret）后走官方时间线，阈值仍是 30 天 ≥5 条原发
- 有 Key 时不再回退 Nitter / syndication；接口失败记未读，不拿第三方数凑通过

### 修复
- `start_time` 改成真正的 UTC。原先把上海时间标成 `Z`，窗口会偏 8 小时

---

## 2026-09-26 · 品宣/前端周报表每天刷新，周日夜里发群

### 优化
- 「项目推送至前端」和「项目方PR链接推送」改为每天 00:00 写入当周数据
- 群通知改到周一 00:00（周日夜里凌晨），周日白天上线的也能进这一期

## 2026-09-26 · KPI 判定时间按飞书日期字段写入

### 修复
- `KPI 判定时间` 改为写入毫秒时间戳。原先的 `YYYY-MM-DD HH:MM` 文字会被日期字段拒绝，格子一直空着

---

## 2026-09-26 · 上线飞书通知立刻发，进群不再重发

### 修复
- 主网上线当时直接推 Project verification push，不再等 90 秒
- 进群只补表单，不再发「Live on mainnet」
- 停在 `scheduled` 的会补发（含 BotDAO）

---

## 2026-09-26 · KPI 判定只在 project diag，扫表不再补 2 / 4 / 5 / 7

### 修复
- 进度表轮询不再写 KPI 2、4、5、7、统筹、判定时间
- `project diag`：有 PR 链接写通过，没链接写不通过（缺 PR 新闻链接）；已通过不降级
- 上线检测、表单回收推群、部署日报仍走原来的扫表

---

## 2026-09-26 · 有 PR 链接就写新闻验证通过

### 修复
- `project diag` 和扫表：`KPI 2 - PR 新闻链接验证` 有链接、新闻验证结果还空着，直接写通过

---

## 2026-09-26 · 主网上线项目空着的 KPI 4 / 5 会补通过

### 修复
- `project diag` 先补 KPI 4 / 5，不再因为统筹已通过就整单跳过
- 状态文件记过一次但格子仍空时也会再写；扫表同样补空着的 4 / 5

---

## 2026-09-26 · 1–6 通过后自动写 KPI 7、统筹和判定时间

### 新增
- Roy号扫进度表：1–6 都通过就写 KPI 7 和统筹，统筹已通过则立刻补 `KPI 判定时间`
- 手改格子约一分钟内生效；`project diag` 遇到统筹已通过、时间空着也会补时间

---

## 2026-09-26 · Mark live 的恭喜和表单改由另一个号发

### 新增
- 两个号都在群里时，谁 Mark live，谁只改上线状态；恭喜和表单由另一个号发。只有一个号在群里时，仍由那个号连状态带话术一起做

### 修复
- 上线话术发出前先占位。进度表轮询不会在三条气泡的间隔里再发一套，避免 BotVault 这种同号连发两遍

---

## 2026-09-26 · 全盘 KPI 口令：跳过已通过、英文稿、上线门槛

### 优化
- `project diag` 先读 7 格：已通过的不重审；1–6 过则自动 KPI 7 通过、统筹通过并写判定时间
- 群回和表内说明改英文；复审追加 `Recheck`；统筹在回复里叫 Final evaluation
- 口令只跑已主网上线且上线日 ≥ 2026-09-01 的项目；KPI 4 / 5 空着就补通过
- `@Josh_0zh` 可在项目群发 diag（仍只由 Roy号执行）

---

## 2026-09-26 · 项目群 `project diag` 全量检查

### 新增
- 群里直接发 `project diag`：连跑推特、官网、链上，并读表里的 PR / 产品 / 独立性
- 六条都过才写 KPI 统筹为通过；有没过的用英文列出，推特条数和链上钱包/笔数分开写

---

## 2026-09-26 · 修复 KPI 6 窗口与官网口令写状态失败

### 修复
- `onchain diag` 只按钱包表合约地址数成功核心交易，不再用项目上线日切窗口
- 官网状态文件写失败不再把整次 `website diag` 打掉；部署时把该文件属主改回 botuser

---

## 2026-09-26 · Roy号群口令审 KPI 1 / 3 / 6

### 新增
- 项目群直接发 `onchain diag` / `twitter diag` / `website diag` 即审对应 KPI 并写回进度表，不用 quote
- 只接 Roy号；没合约写「没有检测到合约」不通过；复审追加记录，过了才把结果改成通过

---

## 2026-09-26 · 谷歌表单回收后推 Project verification push

### 新增
- 主网上线项目的 Twitter、合约、logo、简介进钱包表后，Roy号在 Project verification push @ BD
- 文案按定稿：Google Onboarding form received；已齐的项目先打基线，不刷历史

---

## 2026-09-26 · 主网上线自动通过 KPI 4 / 5

### 新增
- 状态改成主网上线时，产品可用和项目独立性写成固定通过文案，结果格写「通过」
- 已填的格子不覆盖；不写统筹、不推群、不扫历史项目

---

## 2026-09-26 · 主网上线自动审 KPI 3 官网展示

### 新增
- 状态改成主网上线时自动打开官网：能打开、优先认项目名否则认 Logo、页面可点 botchain.ai 和 scan.botchain.ai 才通过
- 未提交官网链接直接不通过；只写「官网验证结果」和 KPI 3 文案，不写统筹、不推群
- 官链只认页面 `<a href>`，源码/配置里出现不算

---

## 2026-09-26 · 修复 KPI 2 新闻验证结果单选写入失败

### 修复
- `新闻验证结果` 按单选字段写成字符串「通过」，不再用读取时的数组格式，避免 `SingleSelectFieldConvFail`

---

## 2026-09-26 · PR 链接同步 KPI 2 新闻验证结果

### 新增
- `pr support` 写入 KPI 2 PR 链接时，同步将「新闻验证结果」写为通过
- 新增手动、默认 dry-run 的 KPI 2 批量同步脚本：默认只将已有链接校正为通过；空链接判不通过需显式开启，避免在审核范围未定时误写历史项目

---

## 2026-09-26 · 群里有交付号或 Roy号 都算已拉群

### 优化
- 项目群匹配改用 Roy号和交付号两边的群缓存，只要其中一个在群里就算绑定
- `BOTCHAIN/mettelia` 这类标题，交付号在群里也算正式群，不再排除

---

## 2026-09-26 · BOTCHAIN/项目名 小群不再算已拉群

### 修复
- 标题是 `BOTCHAIN/mettelia` 这类斜杠标签的，不再当成项目对接群
- 没有正式群时，卡片不再显示 Telegram 已绑定、表单已发送

---

## 2026-09-26 · 没拉群不再显示表单已发送

### 修复
- 项目卡片的 Google 表单状态改为：必须唯一匹配到 TG 群，并且有真实发送事件 / 催收记录，才算已发送
- 只出现在处理名单、或当天 skip 没发出去的，显示尚未发送

---

## 2026-09-25 · pr support 写回推特后群内文案改为 Twitter profile Filled

### 优化
- 钱包表推特栏真正写入后，群里只多一句 `Twitter profile Filled`

---

## 2026-09-25 · pr support 空着才回写钱包表推特主页

### 新增
- `pr support` 从推文链接拆出 X 主页；钱包表推特栏为空才写入，已有内容不覆盖

---

## 2026-09-25 · 项目事件不再显示 Unknown time

### 修复
- 有 unix 时间的表单/状态会转成正常时间；没有时间的历史补记不再进卡片，避免全局 Unknown time

---

## 2026-09-25 · 项目事件加回 TG/QA，钱包日报补上时间

### 修复
- 项目卡片重新显示自动回复、沉默和 Telegram 发出的消息；仍最新在上、不截 30 条
- 午夜钱包日报重新写入流水，并把 9 月 19 日之后缺的发送记录补上，不再显示 Unknown time

---

## 2026-09-25 · 项目事件全盘最新在上，不再截 30 条

### 优化
- 撤回 OpenLC 正序；全部项目都从最新事件往下看
- 去掉每项目 30 条上限，只展示交付自动化（拉群、问候、表单、PR 写表、上线等），不含群聊闲聊

---

## 2026-09-25 · OpenLC 项目事件改成从拉群正序往下看

### 修复
- 卡片不再倒序；第一条是 19:02 交付号进群拉群，拉群之前的「主网部署中」不进这条时间线

---

## 2026-09-25 · OpenLC 项目事件从拉群起完整复盘

### 优化
- OpenLC 卡片去掉 30 条上限和群聊闲聊，按交付周期展示自动化事件
- 补上拉文件夹、问候、`pr support` 写回 KPI 2、mark live；PR 链接：`https://x.com/OpenLCdev/status/2103260520187064709`

---

## 2026-09-25 · 上线群表单拆三条，催收盯四项

### 优化
- 主网上线群消息拆成 3 条，间隔 10 秒：填表、Twitter PR、DeFiLlama
- 催收只盯主网合约、推特主页、logo、项目介绍；缺了每天催，最多 10 天。Roy号先开，交付号仍关着避免双催

---

## 2026-09-25 · 上线推群改成分项 Markdown，突出项目和待办

### 优化
- Project verification push 的上线提醒改为 Markdown post：第一行 @ BD，下面分项写出项目、状态、TG 群、进群情况和表单
- 待办单独列出；Botex 已发的那条不撤回，之后新上线按新格式发

---

## 2026-09-25 · 主网上线后检查进群、发表单并推 Project verification push

### 新增
- 进度表改成主网上线后，按 Roy / Josh 是否在对应 TG 群发表单（Onboarding Google Form），再用飞书 @ 对应 BD 推四种英文稿

### 修复
- 交付号 webhook 不接受 kb 参数时也能启动；飞书群填入 Project verification push
- Project verification push 只由 Roy号发；交付号只写进群状态和 TG 表单

---

## 2026-09-25 · 进夹扫描跳过升级后留下的旧群 ID

### 修复
- 群升级成超级群后，对话列表里的已停用旧 ID 不再当「没进 Folder」去写入；只处理还活着的群

---

## 2026-09-24 · Roy号同步上线群表单文案

### 优化
- Roy号主网上线群消息改成与 Josh 同一份：祝贺、填表单、可选 DeFiLlama

---

## 2026-09-24 · 上线群表单改成表单 + DeFiLlama

### 优化
- Josh 主网上线群消息改为：祝贺上线、请填表单（官网展示 / gas 返还 / 潜在 grant）、可选提交 DeFiLlama

---

## 2026-09-24 · 交付面板可切换中文和英文

### 新增
- 交付控制台右上角可在中文和 English 之间切换，选择会记住
- 导航、页面标题、图表图例和后来刷出来的状态文案一起切换

---

## 2026-09-24 · PR 保存成功改通知 social media team

### 优化
- `pr support` 写入成功后，TG 回复从 Notified Botchain Delivery 改为 Notified Botchain social media team；通知失败时同样改口

---

## 2026-09-23 · send to 之后对方的回复会推回私聊

### 新增
- `send to` 成功后开 24 小时会话：对方私聊智能体，或在群里回复智能体那条，会推到你和智能体的私聊，例如 `Lighter：……`
- 你回复这条推送，正文会发回给对方，并尽量 quote 对方原话
- 24 小时没来回就关；过期后再聊需要重新 `send to`。已在 Roy号打开

---

## 2026-09-23 · recall 能撤掉 send to 发出去的私聊

### 修复
- `send to` 成功后记下发出去的消息 id；再 recall 同一段原文，会撤发给那个人的私聊，不再只在群里翻

---

## 2026-09-23 · 私聊智能体用 recall 撤回消息

### 新增
- 私聊 roy's lark agent：上面贴原文，最后一行写 `recall`（或一行 `recall 原文`），只撤回智能体自己发过、且能唯一对上的那条
- 群里回复智能体消息并只发 `recall` 也会撤；若智能体是管理员，会把这条指令一起撤掉
- 只接受 Roy。飞书事件口即使关掉主网上线 webhook 也会开着。已在 Roy号打开

---

## 2026-09-23 · 周日品宣周报：PR 链接汇总并发群

### 新增
- `pr support` 写入进度表 KPI 2 时记下时间；每周日 00:00 把这一周的项目名、官网、PR 链接写入「项目方PR链接推送」
- 有新链接时，roy's lark agent 在「运营&品宣＆BD对接群」@ Lighter、Jasper，请品宣做社媒和社群支持
- 这一周没有新链接就不发。回链格子不改。已在 Roy号打开

---

## 2026-09-23 · 回链发送前不再把群列表当成函数

### 修复
- 回链触发已经到了 Roy号，取项目群列表时多写了一对括号，消息还没发出去就报错。已按现有写法改正

---

## 2026-09-23 · 回链填入后发到项目 Telegram 群

### 新增
- 「项目方PR链接推送」表的回链格子写入一条链接后，发到该项目方的 Telegram 群
- 同一行同一条链接不重复发；改成另一条再发。不同项目行即使链接相同，也各自发到各自的群
- 由这张表的 Lark 自动化触发，不轮询。已在 Roy号打开

---

## 2026-09-23 · send to 认 @人

### 修复
- 最后一行写 `@某人` 时，Lark 传来的是 `@_user_1`。现在按这条提及里的人直接发，不再拿占位符去搜名字

---

## 2026-09-23 · 私聊智能体用 send to 转发

### 新增
- 在 Lark 里私聊 roy's lark agent，最后一行写 `send to 名字`，上面的内容会发给这个人或这个智能体已加入的群
- 重名、人和群同名时不发送，并把候选回在这条私聊里
- 只有 Roy 能用这条指令；答疑群里的工单回复不变

---

## 2026-09-23 · 寒暄改为表情，并错开两个号

### 优化
- Awesome、thanks、收到、好的优先在原消息上点 👍 或 🔥，不再回那几句固定客套
- 问候、分享、收尾改用分类词库，同一群记住最近 15 句，避开「Works for me!」这类万能句
- 同一群两分钟内只由一个号接话；Roy号已经点过或回过，交付号不再跟着回

---

## 2026-09-23 · 周日官网素材周报，钱包日报 @ 财务

### 新增
- 每周日 00:00 从进度表收集本周主网上线项目（名、官网、中英简介、logo），写入「官网项目收集-每周更新」，并在「项目方信息整理&推送」@ Blake 上传官网
- 每天 00:00 钱包地址日报正文不变，额外 @ Angela-财务

### 修复
- 谷歌表单 Twitter 列改名后，回写对齐钱包表 `Link of Project X ( Formerly Twitter) Profile Page`

---

## 2026-09-22 · Quote `pr support` 覆盖正式表 KPI 2

### 新增
- 在项目 TG 群 quote PR 消息，回复 `pr support`，把链接覆盖写入正式进度表 `KPI 2 - PR 新闻链接验证`
- 写入成功后通知 Botchain Delivery 群；TG 回复不出现 KPI 字样，Lark 内部通知保留
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
