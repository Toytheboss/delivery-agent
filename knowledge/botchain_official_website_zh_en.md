# BOT Chain 官网内容（www.botchain.ai）

Source:
- https://www.botchain.ai/zh
- https://www.botchain.ai/en

抓取日期：2026-08-09。用于替代已删除的 botchain.dev / 旧 GitBook 资料。仅收录官网公开首页定位与产品叙述；主网参数、Help Center、开发者接入等仍以其他官方文档为准。

---

## 项目定位

【相关问题】什么是 BOT Chain？ / What is BOT Chain？ / BOT Chain 是什么链？
【关键词】BOT Chain; Layer 1; AI Agent; DePIN; POS; L1
【参考回答-中文】
BOT Chain 是面向 AI Agent 的 AI 原生 Layer 1 区块链。官网定位为领先的 DePIN + POS 双驱动 Layer 1，专为大规模采用和 AI 生态系统设计，强调亚秒级延迟、近零费用和原生 MEV 抗性。
【参考回答-英文】
BOT Chain is an AI-native Layer 1 blockchain for AI Agents. The official site positions it as a premier DePIN + POS dual-driven L1 engineered for mass adoption and AI ecosystems, with sub-second latency, near-zero fees, and native MEV resistance.
【来源】https://www.botchain.ai/zh | https://www.botchain.ai/en

---

## 核心架构

【相关问题】BOT Chain 核心架构是什么？ / What is BOT Core Architecture？ / SPoA 是什么？
【关键词】架构; SPoA; 混合共识; BFT; 最终性; 治理
【参考回答-中文】
官网描述 BOT 核心架构为「AI 与算力经济的结构化信任堆叠」，要点包括：
1. **混合共识 SPoA**：双轨混合共识，结合物理算力支持的权威机制与高性能质押共识；并行共识执行，解耦性能与最终安全性，针对 AI 工作负载优化。
2. **机构级安全性**：严格执行 BFT；对双签或停机有惩罚，使恶意干预在经济与计算上难以成立。
3. **物理锚定最终性**：性能层提供毫秒级确定性确认；安全层做物理锚定最终结算，抵御长程/共识级攻击。
4. **去中心化治理**：验证者通过绑定质押与动态委托参与；协议级解绑期与自动化治理保证透明与长期激励一致。
【参考回答-英文】
Official BOT Core Architecture highlights: Hybrid Consensus (SPoA) combining compute-backed authority with high-performance staking; institutional-grade BFT security with slashing; physically anchored finality (fast confirmation vs physical settlement); and mechanism-driven decentralized governance via bonded staking/delegation and unbonding periods.
【来源】https://www.botchain.ai/zh | https://www.botchain.ai/en

---

## 技术与双重挖矿

【相关问题】BOT Chain 出块时间多少？ / 双重挖矿是什么？ / PoSA 是什么？ / 有没有通胀？
【关键词】PoSA; 双重挖矿; DePIN; POS; 出块; 最终性; 零通胀; 0.75
【参考回答-中文】
官网技术要点：
- **PoSA 共识与双重收益**：整合 POS 质押挖矿与 DePIN 硬件挖矿；验证者质押 BOT 保护 L1，DePIN 节点贡献 GPU/CPU 算力获得收益。
- **出块时间**：0.75 秒。
- **快速最终性**：约 2 秒内达到不可逆；平均最终性约 ~0.9 秒。
- **惩罚**：双签或停机可被 slash。
- **零通胀经济**：双重挖矿奖励来自交易费与物理算力服务收入，而非通胀增发。
- **并行执行**：64 笔交易 / 批次。
【参考回答-英文】
Official tech notes: PoSA integrates POS staking mining with DePIN hardware mining; 0.75s block time; fast finality within ~2s (~0.9s avg); slashing for double-sign/downtime; zero-inflation model with rewards from fees and compute service revenue; 64 tx/batch parallel execution.
【来源】https://www.botchain.ai/zh | https://www.botchain.ai/en

---

## 生态门户产品

【相关问题】有哪些官方产品？ / BO 钱包是什么？ / BOT 跨链桥？ / B DEX 是什么？
【关键词】BO钱包; Bridge; BDEX; 钱包; 跨链桥; DEX
【参考回答-中文】
官网生态门户包括：
1. **BO 钱包**：DePIN 与 POS 网关；支持 EOA 与 MPC，可监控 DePIN 算力与 POS 质押奖励。
2. **BOT 跨链桥**：连接主要 L1 的跨链通道，统一资产流转。
3. **B DEX**：生态核心去中心化交易基础设施，支持代币交易、提供流动性与流动性挖矿。
另有链上浏览器用于查看交易、地址、合约与网络活动；BOT 为原生 Gas 代币。
【参考回答-英文】
Ecosystem portals on the official site: BO Wallet (EOA/MPC; DePIN & POS gateway), BOT Bridge (cross-chain to major L1s), and B DEX (swap, liquidity, mining). BOT Explorer shows on-chain activity; BOT is the native gas token.
【来源】https://www.botchain.ai/zh | https://www.botchain.ai/en

---

## 路线图（官网公开版）

【相关问题】BOT Chain 路线图？ / roadmap？ / 接下来要上线什么？
【关键词】路线图; roadmap; CaryPact; MPL; vCompute; BDex; Bo钱包
【参考回答-中文】
官网公开路线图（L1 更新）摘要：
- **2025 Q3 – 2026 Q1**：主网强化；模块化协议层（MPL）；vCompute 可验证计算层 v1.0；全球计算节点激活 1.0；旗舰协议 CaryPact；发布 BOT 跨链桥。
- **2026 Q2 – 2026 Q3**：生态激励 / 基础设施资助；机构级数据中心节点；启动 BDex；发布 Bo 钱包。
- **2027 Q1 – 2027 Q2**：治理激励与结构化治理；BOT Layer-0 标准（BIP）；与数据中心/云/AI 企业合作；BOT 企业套件。
- **2027 Q2 – 2028 Q2**：推动成为 AI/DePIN 计算协作标准；全球分布式节点；跨链带宽与验证速度提升；BOT 中继网络（BRN）；超半数生态项目基于 BOT 模块化组件。
具体进度以官网与项目群最新公告为准。
【参考回答-英文】
Official roadmap highlights include mainnet hardening, MPL, vCompute v1.0, CaryPact, BOT Bridge, ecosystem grants, BDex, Bo Wallet, governance/BIP, enterprise suite, global nodes, and BOT Relay Network (BRN). Treat the website as the source of truth for timing.
【来源】https://www.botchain.ai/zh | https://www.botchain.ai/en

---

## 官方入口（首页导向）

【相关问题】官网地址？ / 官方网站？ / official website？
【关键词】官网; website; botchain.ai
【参考回答-中文】
中文官网：https://www.botchain.ai/zh  
英文官网：https://www.botchain.ai/en  
（请勿再使用已废弃的 botchain.dev 旧站信息。）
【参考回答-英文】
Chinese site: https://www.botchain.ai/zh  
English site: https://www.botchain.ai/en  
Do not use deprecated botchain.dev content.
【来源】https://www.botchain.ai/zh | https://www.botchain.ai/en
