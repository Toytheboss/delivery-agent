# BOT Chain Delivery Ops FAQ (short answers for project groups)

Source: Official help center + integration FAQ + delivery onboarding form flow.
Synced: 2026-09-09.

Short, reusable answers for common project-group questions. Prefer these over free-form learned notes.

---

## Mainnet BOT / gas for deployment / 主网 BOT 部署 Gas

【相关问题】怎么拿到主网 BOT 做部署？ / How do I get mainnet BOT for deployment? / What's the process of getting mainnet BOT for deployment from team? / how do i get bot token for mainnet deployment / 部署需要 gas 怎么办 / where can I get BOT for gas
【关键词】mainnet BOT;bot token;gas;deployment;部署;主网;faucet;bridge;DEX
【参考回答-中文】
主网部署要用原生 BOT 付 Gas（测试网币不能付主网 Gas）。

常用两种方式：
1. 自助：用官方 Bridge 跨入 BOT Chain，或在 B DEX 换成 BOT。
   - Bridge：https://bridge.botchain.ai
   - DEX：https://dex.botchain.ai/#/swap
   - 获取 Gas 说明：https://www.botchain.ai/zh/help-center/docs/getting-started/get-bot-for-gas
2. 交付协作：把**部署钱包地址**发在本群，跟交付同学要少量主网 BOT 做部署。上线后填写 onboarding 表单，用于后续 gas 返还 / grant 跟进。

表单：https://forms.gle/vJtpMpmsYuP8zGAh9
【参考回答-英文】
Mainnet deploys need native BOT for gas (testnet tokens cannot pay mainnet gas).

Two common paths:
1. Self-serve: bridge into BOT Chain or swap for BOT on B DEX.
   - Bridge: https://bridge.botchain.ai
   - DEX: https://dex.botchain.ai/#/swap
   - Gas guide: https://www.botchain.ai/en/help-center/docs/getting-started/get-bot-for-gas
2. Delivery flow: drop your **deployer wallet address** in this group and ask the delivery teammate for a small amount of mainnet BOT for deployment. After you go live, fill the onboarding form for future gas rebate / grant follow-up.

Form: https://forms.gle/vJtpMpmsYuP8zGAh9
【来源】https://www.botchain.ai/en/help-center/docs/getting-started/get-bot-for-gas | delivery onboarding form

---

## After deploy / next steps / 部署后下一步

【相关问题】部署完下一步做什么？ / What should we do after mainnet deployment? / deployed contract next steps / 合约部署完成之后 / after we deploy on mainnet / send contract address
【关键词】deploy;部署后;next steps;contract address;form;onboarding;verify;BOTScan
【参考回答-中文】
合约部署到 BOT Chain Mainnet 后，建议按这个顺序：
1. 在浏览器确认合约：https://scan.botchain.ai
2. 把合约地址 / BOTScan 链接发到本群
3. 填写 onboarding 表单（项目地址、主网合约、Treasury、Fee Collector 等，用于后续 gas 返还 / grant 跟进）：https://forms.gle/vJtpMpmsYuP8zGAh9
4. 如方便，发一条 X/Twitter 上线帖，并把链接贴回本群

人工核验（Please verify @某人）需要交付同学亲自看，机器人不会自动 verify。
【参考回答-英文】
After your contract is on BOT Chain Mainnet:
1. Confirm it on the explorer: https://scan.botchain.ai
2. Share the contract address / BOTScan link in this group
3. Fill the onboarding form (project addresses, mainnet contract, treasury, fee collector — for future gas rebate / grant follow-up): https://forms.gle/vJtpMpmsYuP8zGAh9
4. If you can, post an X/Twitter announcement and drop the link here

“Please verify @someone” still needs a human from the delivery side — the bot will not auto-verify.
【来源】delivery onboarding form flow | https://scan.botchain.ai

---

## Mainnet params / RPC / Chain ID / explorer / 主网参数

【相关问题】BOT Chain 主网参数是什么？ / What are BOT Chain mainnet parameters? / RPC URL / Chain ID / explorer / WSS / 怎么加主网 / MetaMask BOT Chain
【关键词】RPC;Chain ID;677;explorer;WSS;scan;rpc.botchain.ai;主网参数
【参考回答-中文】
BOT Chain Mainnet：
- Network Name: BOT Chain Mainnet
- RPC: https://rpc.botchain.ai
- Chain ID: **677**
- Currency: BOT
- Explorer: https://scan.botchain.ai
- WSS: wss://ws-rpc.botchain.ai
- JSON-RPC 说明：https://dev-docs.botchain.ai/docs/Developers/json-rpc-endpoint/
- Quick Guide：https://dev-docs.botchain.ai/docs/Developers/quick-guide/

测试网水龙头（仅测试）：https://faucet.botchain.ai
【参考回答-英文】
BOT Chain Mainnet:
- Network Name: BOT Chain Mainnet
- RPC: https://rpc.botchain.ai
- Chain ID: **677**
- Currency: BOT
- Explorer: https://scan.botchain.ai
- WSS: wss://ws-rpc.botchain.ai
- JSON-RPC docs: https://dev-docs.botchain.ai/docs/Developers/json-rpc-endpoint/
- Quick Guide: https://dev-docs.botchain.ai/docs/Developers/quick-guide/

Testnet faucet (testing only): https://faucet.botchain.ai
【来源】https://www.botchain.ai/en/help-center | BDQA-004/005/006/007/008

---

## Oracle / Chainlink / 预言机

【相关问题】BOT Chain 有没有 Chainlink？ / Do we have Botchain Mainnet settings on chainlink / Is Pyth or Chainlink live on BOT Chain? / 预言机支持吗 / oracle on BOT Chain
【关键词】Chainlink;Pyth;oracle;预言机;mainnet settings
【参考回答-中文】
BOT Chain **目前还没有上线** Chainlink / Pyth 等预言机。Oracle 支持在沟通 / 规划中，对外不承诺已完成某个 Oracle 集成。

如果项目有明确的预言机需求，把用例发在本群，我们帮转给生态 / 技术同学评估。
【参考回答-英文】
BOT Chain does **not** currently have Chainlink / Pyth (or another oracle) live on mainnet. Oracle support is under discussion / planning — we do not claim a finished Chainlink integration.

If you have a concrete oracle requirement, share the use case in this group and we’ll route it to the ecosystem / tech team.
【来源】botchain_complete_faq_builder_guide | BDQA-022/023

---

## Social / X announcement / 社交账号与发帖

【相关问题】社交账号要发哪些？ / what all social accounts do we have to make x is fine right / Do we need Twitter / Is X enough for the announcement? / 只要发 Twitter 可以吗 / PR announcement
【关键词】social;twitter;X;公告;发帖;announce;tweet
【参考回答-中文】
上线对外同步，**发 X（Twitter）通常就够**，除非交付同学另外说明还要别的渠道。

发完后把帖子链接贴回本群即可。
【参考回答-英文】
For the go-live shoutout, **posting on X (Twitter) is usually enough**, unless the delivery teammate asked for extra channels.

After you post, drop the link back in this group.
【来源】delivery announcement practice
