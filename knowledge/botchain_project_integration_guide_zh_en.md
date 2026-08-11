# BOT Chain Project Integration Guide / 项目集成指南

Source: Official Project Integration Guide (EN + ZH paste, synced 2026-08-09).
Use this as the canonical FAQ source for mainnet params, contracts, routers, bundlers, audits, and integration steps.

---

## Overview / 概述

【相关问题】什么是 BOT Chain 项目集成指南？ / What is the BOT Chain Project Integration Guide？ / 如何接入 BOT Chain？
【关键词】integration guide;项目集成;接入指南;EVM;L1;AI Agent;DePIN
【参考回答-中文】
BOT Chain 是专为 AI Agent、DePIN、可验证计算和协议经济设计的高性能、EVM 兼容 Layer 1。本指南为项目方提供从接入到上线的完整操作指引，帮助快速、安全、高效完成主网集成。
【参考回答-英文】
BOT Chain is a high-performance, EVM-compatible Layer 1 designed for AI Agents, DePIN, verifiable computing, and the protocol economy. This guide gives project teams complete step-by-step instructions to integrate and launch on BOT Chain Mainnet quickly, securely, and efficiently.
【来源】BOT Chain Project Integration Guide

---

## Official Links / 官方链接

【相关问题】BOT Chain 官方链接有哪些？ / What are the official BOT Chain links？ / 官网 faucet DEX bridge 钱包 浏览器
【关键词】website;faucet;DEX;bridge;wallet;explorer;docs;github;官方链接
【参考回答-中文】
- 官网：https://www.botchain.ai
- 测试网水龙头：https://faucet.botchain.ai
- DEX：https://dex.botchain.ai/#/swap ；文档 https://dev-docs.botchain.ai/zh-Hans/docs/DEX/
- 跨链桥：https://bridge.botchain.ai/
- 官方钱包：https://wallet.botchain.ai/
- 区块链浏览器：https://scan.botchain.ai/
- 开发者文档：https://dev-docs.botchain.ai/docs/Developers/quick-guide/
- GitHub：https://github.com/BOTChain-bot
- 品牌 Kit：https://drive.google.com/drive/folders/1AYVj_gvnffA4T-QyXN3opgWNG5M7oD_1
官方入口：https://www.botchain.ai/ · 文档：https://dev-docs.botchain.ai/
【参考回答-英文】
- Website: https://www.botchain.ai
- Testnet Faucet: https://faucet.botchain.ai
- DEX: https://dex.botchain.ai/#/swap ; Docs: https://dev-docs.botchain.ai/docs/DEX/
- Bridge: https://bridge.botchain.ai
- Official Wallet: https://wallet.botchain.ai
- Explorer: https://scan.botchain.ai
- Developer Docs: https://dev-docs.botchain.ai/docs/Developers/quick-guide/
- GitHub: https://github.com/BOTChain-bot
- Brand Kit: https://drive.google.com/drive/folders/1AYVj_gvnffA4T-QyXN3opgWNG5M7oD_1
【来源】BOT Chain Project Integration Guide

---

## BOT / WBOT / USDT / Price APIs

【相关问题】BOT 有合约地址吗？WBOT USDT 地址？价格 API？ / BOT contract address WBOT USDT price API CoinGecko
【关键词】BOT;WBOT;USDT;price API;Coinstore;CoinGecko;CMC;原生代币
【参考回答-中文】
- BOT：原生币，无合约地址。
- BOT 价格 API（Coinstore）：https://api.coinstore.com/api/v1/ticker/price;symbol=BOTUSDT
- Orderbook：https://api.coinstore.com/v3/public/orderbook/market_pair?market_pair=BOT_USDT&depth=100
- CoinGecko：https://www.coingecko.com/en/coins/bot
- CoinMarketCap：https://coinmarketcap.com/currencies/bot-chain/
- WBOT：`0xD5452816194a3784dBa983426cCe7c122F4abd30`
  - Scan：https://scan.botchain.ai/token/0xD5452816194a3784dBa983426cCe7c122F4abd30
  - WBOT Price API：https://dex-wallet.botchain.ai/api/graph/price?token=0xD5452816194a3784dBa983426cCe7c122F4abd30
- USDT（BOT Chain）：`0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C`
  - Scan：https://scan.botchain.ai/token/0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C
价格 API 仅作行情参考，不构成收益或上币承诺。
【参考回答-英文】
- BOT: native coin, no contract address.
- BOT Price API (Coinstore): https://api.coinstore.com/api/v1/ticker/price;symbol=BOTUSDT
- Orderbook: https://api.coinstore.com/v3/public/orderbook/market_pair?market_pair=BOT_USDT&depth=100
- CoinGecko: https://www.coingecko.com/en/coins/bot
- CoinMarketCap: https://coinmarketcap.com/currencies/bot-chain/
- WBOT: `0xD5452816194a3784dBa983426cCe7c122F4abd30`
  - Scan: https://scan.botchain.ai/token/0xD5452816194a3784dBa983426cCe7c122F4abd30
  - WBOT Price API: https://dex-wallet.botchain.ai/api/graph/price?token=0xD5452816194a3784dBa983426cCe7c122F4abd30
- USDT on BOT Chain: `0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C`
  - Scan: https://scan.botchain.ai/token/0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C
Price APIs are for market reference only.
【来源】BOT Chain Project Integration Guide

---

## ERC-4337 Bundler

【相关问题】ERC4337 bundler 端点是什么？ / What are the ERC-4337 bundler endpoints？
【关键词】ERC4337;bundler;账户抽象;AA;4337
【参考回答-中文】
- Testnet：https://bundler.bohr.life/rpc
- Mainnet：https://bundler.botchain.ai/rpc
请按网络选用对应端点。
【参考回答-英文】
- Testnet: https://bundler.bohr.life/rpc
- Mainnet: https://bundler.botchain.ai/rpc
Use the endpoint that matches your network.
【来源】BOT Chain Project Integration Guide

---

## BDEX Universal Router

【相关问题】BDEX Universal Router 地址是什么？ / What is the BDEX Universal Router address？
【关键词】Universal Router;BDEX;router;677;968
【参考回答-中文】
- Mainnet，Chain ID 677：`0xaE6ae8630f7A888dEc0B9195C85F7515d5887655`
- Testnet，Chain ID 968：`0x73Be0A1d8011B335A7aBeF6c45544E8ca4448AB5`
对接时务必核对网络与 Chain ID，不要混用主网/测试网地址。
【参考回答-英文】
- Mainnet, Chain ID 677: `0xaE6ae8630f7A888dEc0B9195C85F7515d5887655`
- Testnet, Chain ID 968: `0x73Be0A1d8011B335A7aBeF6c45544E8ca4448AB5`
Always match the address to the correct network/Chain ID.
【来源】BOT Chain Project Integration Guide

---

## Add BOT Chain to Wallet / 加链

【相关问题】如何把 BOT Chain 加到钱包？主网参数？ / How to add BOT Chain to wallet？ mainnet RPC Chain ID
【关键词】主网参数;RPC;Chain ID;677;Chainlist;MetaMask;Bitget;TokenPocket;OKX
【参考回答-中文】
支持常见 EVM 钱包：Bitget Wallet https://web3.bitget.com/ ；TokenPocket https://www.tokenpocket.pro ；OKX Wallet https://web3.okx.com ；MetaMask。

通过 Chainlist：https://chainlist.org/?search=bot+chain&testnets=true → 连接钱包 → Add BOT Chain。

手动添加主网：
| 项目 | 参数 |
|---|---|
| Network Name | BOT Chain |
| RPC URL | https://rpc.botchain.ai |
| Chain ID | 677 |
| Native Token | BOT |
| Explorer | https://scan.botchain.ai/ |

网络参数：Chain ID 677；RPC https://rpc.botchain.ai
【参考回答-英文】
Supported EVM wallets: Bitget Wallet https://web3.bitget.com/ ; TokenPocket https://www.tokenpocket.pro ; OKX Wallet https://web3.okx.com ; MetaMask.

Via Chainlist: https://chainlist.org/?search=bot+chain&testnets=true → Connect wallet → Add BOT Chain.

Manual Mainnet:
| Item | Parameter |
|---|---|
| Network Name | BOT Chain |
| Default RPC URL | https://rpc.botchain.ai |
| Chain ID | 677 |
| Currency symbol | BOT |
| Block Explorer URL | https://scan.botchain.ai/ |

Verify Chain ID 677 and the official RPC.
【来源】BOT Chain Project Integration Guide

---

## Project Integration Steps / 接入流程

【相关问题】项目接入 BOT Chain 的步骤？ / Project integration steps on BOT Chain
【关键词】接入流程;部署;Hardhat;Foundry;Remix;integration steps
【参考回答-中文】
1. 将 BOT Chain 主网添加到钱包  
2. 通过水龙头获取测试币：https://faucet.botchain.ai  
3. 使用 Hardhat / Foundry / Remix，经官方 RPC 部署智能合约  
4. 在区块浏览器验证合约并测试产品  
如需交易/跨链/钱包：DEX https://dex.botchain.ai/#/swap ；Bridge https://bridge.botchain.ai ；Wallet https://wallet.botchain.ai
【参考回答-英文】
1. Add BOT Chain Mainnet to your wallet  
2. Obtain test tokens from the faucet: https://faucet.botchain.ai  
3. Deploy contracts with Hardhat / Foundry / Remix via the official RPC  
4. Verify contracts on the explorer and test your product  
For trading/bridging/wallet: DEX https://dex.botchain.ai/#/swap ; Bridge https://bridge.botchain.ai ; Wallet https://wallet.botchain.ai
【来源】BOT Chain Project Integration Guide

---

## Security & Audits / 安全与审计

【相关问题】BOT Chain 审计报告在哪里？CertiK？ / Audit reports CertiK Skynet
【关键词】审计;CertiK;安全;audit;Skynet
【参考回答-中文】
核心合约均经 CertiK 专业审计：
- Chain：https://www.botchain.ai/docs/Chain.pdf
- DEX：https://dex.botchain.ai/docs/Dex-Audit-Report.pdf
- Bridge：https://bridge.botchain.ai/docs/Bridge-Audit-Report.pdf
- CertiK Skynet：https://skynet.certik.com/projects/botchain
【参考回答-英文】
Core contracts audited by CertiK:
- Chain: https://www.botchain.ai/docs/Chain.pdf
- DEX: https://dex.botchain.ai/docs/Dex-Audit-Report.pdf
- Bridge: https://bridge.botchain.ai/docs/Bridge-Audit-Report.pdf
- CertiK Skynet: https://skynet.certik.com/projects/botchain
【来源】BOT Chain Project Integration Guide

---

## Inform details / 补充技术信息

【相关问题】CA token WSS BDEX 合约地址？ / CA token WSS endpoint BDEX contract addresses mainnet
【关键词】CA token;WSS;WebSocket;BDEX;factory;swapRouter;quoter;nftPositionManager;deployer
【参考回答-中文】
- 主网 CA Token：https://scan.botchain.ai/token/0x546307af427902A75771434Df831d88219784E19
- WSS：`wss://ws-rpc.botchain.ai` ；Debug：`wss://ws-rpc-debug.botchain.ai/`
- BDEX mainnet（chainId 677）合约：
  - deployer: `0xf0A2f56505f0dfea980567DA88830146B6b5c0b2`
  - tokens.wbot: `0xD5452816194a3784dBa983426cCe7c122F4abd30`
  - tokens.usdt: `0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C`
  - v3.factory: `0x1C51c173323ec11BB4e3C4fD2314c225Dc4b5419`
  - v3.swapRouter: `0x07032d47A1b9f8460cBeE9dC17c1d3E438693929`
  - v3.quoter: `0x1e8bb093ade678ABAa49623D4c3a1a7F37716DEd`
  - v3.quoterV2: `0x034A705b36067cff99ABf5C662Be881cBd8d0176`
  - v3.botdexMulticall: `0x5FC578616301E56137dc3872593d496668525362`
  - v3.nftDescriptor: `0x829D215662e89881adE3C7b15a0af812c4364dA4`
  - v3.nftPositionDescriptor: `0x89b084964AF60BeE7bEc324Ea62267C97f6656E3`
  - v3.nftPositionManager: `0xDAc3FcFF004d8a8675b94E44941A1a2e3b240090`
完整列表见官方集成指南。
【参考回答-英文】
- Mainnet CA token: https://scan.botchain.ai/token/0x546307af427902A75771434Df831d88219784E19
- WSS: `wss://ws-rpc.botchain.ai` ; Debug: `wss://ws-rpc-debug.botchain.ai/`
- BDEX mainnet (chainId 677) contracts:
  - deployer: `0xf0A2f56505f0dfea980567DA88830146B6b5c0b2`
  - tokens.wbot: `0xD5452816194a3784dBa983426cCe7c122F4abd30`
  - tokens.usdt: `0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C`
  - v3.factory: `0x1C51c173323ec11BB4e3C4fD2314c225Dc4b5419`
  - v3.swapRouter: `0x07032d47A1b9f8460cBeE9dC17c1d3E438693929`
  - v3.quoter: `0x1e8bb093ade678ABAa49623D4c3a1a7F37716DEd`
  - v3.quoterV2: `0x034A705b36067cff99ABf5C662Be881cBd8d0176`
  - v3.botdexMulticall: `0x5FC578616301E56137dc3872593d496668525362`
  - v3.nftDescriptor: `0x829D215662e89881adE3C7b15a0af812c4364dA4`
  - v3.nftPositionDescriptor: `0x89b084964AF60BeE7bEc324Ea62267C97f6656E3`
  - v3.nftPositionManager: `0xDAc3FcFF004d8a8675b94E44941A1a2e3b240090`
Full list: official integration guide.
【来源】BOT Chain Project Integration Guide

---

## BDEX mainnet JSON (raw)

```json
{
  "mainnet": {
    "chainId": 677,
    "deployer": "0xf0A2f56505f0dfea980567DA88830146B6b5c0b2",
    "tokens": {
      "wbot": "0xD5452816194a3784dBa983426cCe7c122F4abd30",
      "usdt": "0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C"
    },
    "v3": {
      "deployedAt": "2026-02-26T05:57:53.573Z",
      "factory": "0x1C51c173323ec11BB4e3C4fD2314c225Dc4b5419",
      "swapRouter": "0x07032d47A1b9f8460cBeE9dC17c1d3E438693929",
      "quoter": "0x1e8bb093ade678ABAa49623D4c3a1a7F37716DEd",
      "quoterV2": "0x034A705b36067cff99ABf5C662Be881cBd8d0176",
      "botdexMulticall": "0x5FC578616301E56137dc3872593d496668525362",
      "nftDescriptor": "0x829D215662e89881adE3C7b15a0af812c4364dA4",
      "nftPositionDescriptor": "0x89b084964AF60BeE7bEc324Ea62267C97f6656E3",
      "nftPositionManager": "0xDAc3FcFF004d8a8675b94E44941A1a2e3b240090"
    }
  }
}
```
