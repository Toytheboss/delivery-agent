# BOT Chain Developer Docs (full crawl)

Source hub: https://dev-docs.botchain.ai/
Crawled: 2026-08-09; pages=58; fails=0
Scope: intro, introduction/*, Developers/*, staking/*, DEX/*, Bridge/* (EN + zh-Hans).

---

## Bridge

Source: https://dev-docs.botchain.ai/docs/Bridge/

📄️ Introduction to Bridge on BOT Chain
BOT Chain Bridge is the official cross-chain infrastructure that lets users move USDT between BOT Chain and other supported networks. It connects BOT Chain with Ethereum, BNB Smart Chain, and Tron, so USDT can flow in and out of the BOT Chain ecosystem quickly and securely.

---

## Contract Addresses

Source: https://dev-docs.botchain.ai/docs/Bridge/contract-addresses/

Bridge
Contract Addresses
Bridge contracts are deployed on BOT Chain Mainnet (Chain ID: 677) and Testnet (Chain ID: 968). Counterpart contracts are deployed on each supported external network.
Bridge — BOT Chain Mainnet​
ContractAddressDescription
BridgeRouter0xef8DC669ECa13E612b67Ff09478352E85bD6CC53Entry point for bridge-in / bridge-out requests
USDT (BOT Chain)0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3CUSDT token contract on BOT Chain
Multicall30x47FA21f684bBAD707A53a0f9BE59F1422F46C265Batch contract calls
Bridge — External Networks​
NetworkContractAddress
Ethereum (1)BridgeGateway0x2945d3aF6f012e49f7421252b5fB57D1bb7E6Edd
Ethereum (1)USDT (ERC-20)0xdAC17F958D2ee523a2206206994597C13D831ec7
BNB Smart Chain (56)BridgeGateway0x3cd6fB6b0CDdD3610f0f4769AA7Bb686Cd4a4b55
BNB Smart Chain (56)USDT (BEP-20)0x55d398326f99059fF775485246999027B3197955
TronBridgeGatewayTGhXbQpjBgC6bDp5jAexzeQPHEXXsx5f35
TronUSDT (TRC-20)TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
Bridge — BOT Chain Testnet​
ContractAddress
BridgeRouter0x6239404Aa276ba68486E2Fa40E90CDd36ff8ec3A
USDT (BOT Chain Testnet)0x75edC9335175Fc0552D51D48439F229c10420fe3
Bridge — External Test Networks​
Ethereum Sepolia (11155111)BridgeGateway0xc83AE6F73e8918750b87DD001E36093A1AB7b272
Ethereum Sepolia (11155111)USDT (ERC-20)0x7B1e05a39adF207a759EAf89E867dBcC1C615130
BNB Smart Chain Testnet (97)BridgeGateway0xbCAA929FdB16f5a7185C96A4Ed0CC4F25ab86E40
BNB Smart Chain Testnet (97)USDT (BEP-20)0x5d012516D129Ab3aE7673FE32E5ABFCD9be4d086
Tron NileBridgeGatewayTMGhDtUkEhARjd1uYDVssubqH4ivnarfv7
Tron NileUSDT (TRC-20)TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf
The resource_id of the USDT token is the same across all test networks and the mainnet:
0xac589789ed8c9d2c61f17b13369864b5f181e58eba230a6ee4ec4c3e7750cd1d
Bridge Contract Function Example​
EntranceSceneTarget chain has been credited
deposit(...)Ordinary cross-chainOnly transfer the target chain token, such as USDT
depositWithBotGas(...)Switch to BOT Chain and wish to include the native BOT currency as GasReceive USDT + BOT; the BOT cost will be deducted from the net amount of this USDT deposit.

---

## Core Concepts

Source: https://dev-docs.botchain.ai/docs/Bridge/core-concepts/

Bridge
Core Concepts
Lock & Release (Liquidity Model)​
Because USDT exists natively on every supported network, the Bridge uses a Lock & Release model backed by USDT liquidity vaults on each chain, rather than minting wrapped tokens.
Bridge In: USDT is locked in the TokenVault on the source chain, and an equal amount of USDT is released from the BOT Chain vault to the recipient.
Bridge Out: USDT is locked in the BOT Chain vault, and an equal amount (minus the withdrawal fee) is released from the vault on the destination chain.
Validators / Relayers​
Cross-chain transfers are secured by a decentralized set of validators. When a deposit is detected on the source chain, validators independently observe the event and produce signed attestations. Once the required signature threshold is reached, a relayer submits the aggregated proof to the destination chain to release the USDT.
Validators never take custody of user funds; they only attest to observed events.
The BridgeValidator contract enforces the signature threshold before releasing USDT.
Confirmations & Finality​
To protect against chain reorganizations, the Bridge waits for a minimum number of block confirmations on the source chain before validators attest to a transfer.
BOT Chain: Physical Finality — a transaction is final once included, so confirmations are near-instant.
External chains (Ethereum, BSC, Tron): the Bridge waits for a network-specific confirmation count before processing.
Security Model​
Every transfer is uniquely identified by a transferId and can only be claimed once (replay protected).
Release requires a valid quorum of validator signatures verified on-chain.
Vault balances are fully backed 1:1 by locked USDT.
Pausable: the BridgeRouter can be paused by governance in an emergency to protect user funds.

---

## Fees

Source: https://dev-docs.botchain.ai/docs/Bridge/fees/

Bridge
Fees
The BOT Chain Bridge uses a simple, fixed fee structure for USDT transfers.
DirectionBridge FeeNotes
Bridge In (into BOT Chain)Free (0 USDT)No bridge fee is charged for deposits into BOT Chain
Bridge Out (out of BOT Chain)0.1% (min 1 USDT)A 0.1% fee (minimum 1 USDT) is deducted from the transfer amount
Bridge In: the recipient receives the full deposited USDT amount (network gas on the source chain still applies).
Bridge Out: the recipient receives the transfer amount minus the withdrawal fee (0.1%, minimum 1 USDT). The transfer amount must be greater than 10 USDT.

---

## Introduction to Bridge on BOT Chain

Source: https://dev-docs.botchain.ai/docs/Bridge/introduction/

Bridge
Introduction to Bridge on BOT Chain
BOT Chain Bridge is the official cross-chain infrastructure that lets users move USDT between BOT Chain and other supported networks. It connects BOT Chain with Ethereum, BNB Smart Chain, and Tron, so USDT can flow in and out of the BOT Chain ecosystem quickly and securely.
BOT Chain is a high-performance EVM-compatible Layer 1 with 0.75-second block times, Physical Finality, and extremely low gas fees, making bridged funds available fast once a transfer is confirmed.
Why Use the BOT Chain Bridge?​
Free deposits — Bridging USDT into BOT Chain (bridge in) charges no bridge fee
Simple, predictable withdrawal fee — Bridging USDT out of BOT Chain charges 0.1% (minimum 1 USDT)
Fast settlement — 0.75s block time and Physical Finality on the BOT Chain side
Secure by design — Validator / multi-signature verification with on-chain proof of every transfer
Multi-chain coverage — Ethereum (ERC-20), BNB Smart Chain (BEP-20), and Tron (TRC-20) USDT
Quick Start Path​
Supported Chains & Assets
Contract Addresses
Core Concepts
Fees
Ready to connect BOT Chain to the multichain world? Let's get started!

---

## Supported Chains & Assets

Source: https://dev-docs.botchain.ai/docs/Bridge/supported-chains/

Bridge
Supported Chains & Assets
The BOT Chain Bridge currently supports USDT transfers only, between BOT Chain and the following networks.
NetworkChain IDUSDT Standard
BOT Chain677USDT (BOT Chain)
Ethereum1ERC-20 USDT
BNB Smart Chain56BEP-20 USDT
TronTron Mainnet (non-EVM)
Cross-chain bridge scenario usage: 728126428TRC-20 USDT

---

## DEX

Source: https://dev-docs.botchain.ai/docs/DEX/

📄️ Introduction to DEX on BOT Chain
BOT Chain is a high-performance EVM-compatible Layer 1 blockchain featuring 0.75-second block times, Physical Finality, and extremely low gas fees — making it an ideal platform for building fast and efficient Decentralized Exchanges (DEXs).

---

## API Reference

Source: https://dev-docs.botchain.ai/docs/DEX/api-reference/

DEX
API Reference
BOT Chain DEX provides official APIs for developers.
All DEX APIs are documented in our Apifox workspace. You can view detailed endpoints, request/response examples, and test directly in the browser.
View API Documentation:
Testnet: https://s.apifox.cn/78c89a55-76be-4d27-9efe-35626bd465f2
Mainnet: https://s.apifox.cn/139b78fd-a57f-470a-ac74-b7246d32f2e6

---

## BDEX V2

Source: https://dev-docs.botchain.ai/docs/DEX/bdex-v2/

DEX
BDEX V2
BDEX V2 is a Constant Product AMM (x × y = k) deployed on BOT Chain, based on the battle-tested Uniswap V2 architecture. It provides a simple and reliable DEX infrastructure for token creators and developers.
Creating Trading Pairs​
BDEX V2 trading pairs are created through the V2 Factory contract. A pair is uniquely identified by two token addresses, and each token pair can only have one V2 pair contract.
Factory method:
function createPair(address tokenA, address tokenB) external returns (address pair);
function getPair(address tokenA, address tokenB) external view returns (address pair);
Basic rules:
tokenA and tokenB must be different tokens.
Neither token address can be the zero address.
If the pair already exists, createPair will revert.
After creation, developers can read the pair address through getPair(tokenA, tokenB) or listen to the PairCreated event.
Example flow:
const pair = await factory.getPair(tokenA, tokenB)
if (pair === ZERO_ADDRESS) {
const tx = await factory.createPair(tokenA, tokenB)
await tx.wait()
}
For most frontend integrations, developers do not need to manually create the pair first. Adding initial liquidity through the router can create the pair when needed.
Adding / Removing Liquidity​
BDEX V2 liquidity is managed through the V2 Router02 contract. Liquidity providers deposit both tokens into a pair and receive V2 LP tokens. The LP token is the pair contract's ERC-20 token and represents the provider's share of the pool.
Common methods:
function addLiquidity(
address tokenA,
address tokenB,
uint amountADesired,
uint amountBDesired,
uint amountAMin,
uint amountBMin,
address to,
uint deadline
) external returns (uint amountA, uint amountB, uint liquidity);
function removeLiquidity(
uint liquidity,
) external returns (uint amountA, uint amountB);
Integration notes:
Users must approve the V2 Router02 to spend both ERC-20 tokens before adding liquidity.
For an existing pool, liquidity should be added according to the current reserve ratio.
For a new pool, the first liquidity provider defines the initial price by choosing the deposit ratio.
amountAMin and amountBMin should be set to protect users from slippage.
Removing liquidity burns LP tokens and returns the underlying token pair according to the user's pool share.
Native BOT liquidity:
For pools involving native BOT, use the ETH-style router methods such as addLiquidityETH / removeLiquidityETH. Internally, native BOT is wrapped as WBOT.
Token Swap Guide​
BDEX V2 swaps can be executed directly through Router02, but frontend applications are recommended to use the official Routing API to get the best route and executable calldata.
Recommended integration path:
Call the Routing API GET /quote.
Read methodParameters.to, methodParameters.calldata, and methodParameters.value from the response.
Submit these fields with eth_sendTransaction.
Routing API example:
GET /quote?chainId=677
&tokenInAddress=0x...
&tokenOutAddress=0x...
&amount=1000000000000000000
&type=exactIn
&protocols=v2
&recipient=0x...
&slippageTolerance=0.5
Direct Router02 methods:
function swapExactTokensForTokens(
uint amountIn,
uint amountOutMin,
address[] calldata path,
) external returns (uint[] memory amounts);
function swapTokensForExactTokens(
uint amountOut,
uint amountInMax,
Swap fee:
BDEX V2 uses a fixed 0.30% swap fee.
The fee is taken from the input token amount.
The output token is not charged by the pool separately.
Fees remain in the pool and are distributed to LPs through the pool reserve growth.
Fee-on-transfer tokens:
Fee-on-transfer tokens should only use V2 routes. V3 liquidity and swap flows may revert for tax tokens. The Routing API automatically detects supported fee-on-transfer cases and restricts routing when needed.

---

## BDEX V3

Source: https://dev-docs.botchain.ai/docs/DEX/bdex-v3/

DEX
BDEX V3
BDEX V3 introduces Concentrated Liquidity, allowing LPs to allocate capital within custom price ranges for significantly improved capital efficiency. Based on the Uniswap V3 architecture, adapted for BOT Chain's 0.75s block time and low gas environment.
Concentrated Liquidity Guide​
BDEX V3 uses a concentrated liquidity model. Unlike V2, liquidity is not always distributed across the full price range. Liquidity providers choose a custom price range where their capital is active.
When the market price is inside the selected range, the position earns swap fees. When the market price moves outside the range, the position becomes inactive and no longer earns fees until the price re-enters the range.
Core contracts:
ContractPurpose
V3 FactoryCreates and manages V3 pools
NonfungiblePositionManagerCreates and manages LP positions as NFTs
QuoterV2Simulates swap output off-chain
Universal RouterExecutes swaps across supported protocols
Supported fee tiers:
Fee TierFee ValueTick SpacingTypical Use Case
0.05%50010Stable or highly correlated pairs
0.30%300060Most standard pairs
1.00%10000200High volatility or long-tail assets
Creating a V3 pool:
function createPool(
address tokenA,
address tokenB,
uint24 fee
) external returns (address pool);
After a pool is created, it must be initialized with the initial price before liquidity can be added.
function initialize(uint160 sqrtPriceX96) external;
Adding concentrated liquidity:
Developers should use NonfungiblePositionManager.mint to create a position. The position is represented as an ERC-721 NFT.
struct MintParams {
address token0;
address token1;
uint24 fee;
int24 tickLower;
int24 tickUpper;
uint256 amount0Desired;
uint256 amount1Desired;
uint256 amount0Min;
uint256 amount1Min;
address recipient;
uint256 deadline;
}
function mint(MintParams calldata params)
external
payable
returns (
uint256 tokenId,
uint128 liquidity,
uint256 amount0,
uint256 amount1
);
Integration notes:
Users must approve NonfungiblePositionManager to spend both tokens before minting a position.
tickLower and tickUpper must match the pool's tick spacing.
amount0Min and amount1Min should be set to protect users from slippage.
The narrower the price range, the higher the capital efficiency, but the higher the chance the position becomes inactive.
Position Management​
BDEX V3 LP positions are managed by NonfungiblePositionManager. Each position is an NFT with its own token pair, fee tier, price range, liquidity amount, and accumulated fees.
Common position operations:
function increaseLiquidity(IncreaseLiquidityParams calldata params)
returns (uint128 liquidity, uint256 amount0, uint256 amount1);
function decreaseLiquidity(DecreaseLiquidityParams calldata params)
returns (uint256 amount0, uint256 amount1);
function collect(CollectParams calldata params)
function burn(uint256 tokenId) external payable;
Position lifecycle:
Mint — Create a new concentrated liquidity position NFT.
Increase Liquidity — Add more liquidity to an existing position.
Decrease Liquidity — Remove part or all of the liquidity from the position.
Collect Fees — Claim accumulated swap fees.
Burn — Destroy the NFT after all liquidity and fees have been removed.
Fee collection notes:
V3 fees are not automatically transferred to the LP's wallet.
LPs must call collect to claim accumulated fees.
Fees only accrue while the position is active, meaning the current pool price is within the selected tick range.
Removing liquidity does not automatically collect all fees; applications should call collect when needed.

---

## Contract Addresses

Source: https://dev-docs.botchain.ai/docs/DEX/contract-addresses/

DEX
Contract Addresses
All BDEX smart contracts are deployed on BOT Chain Mainnet (Chain ID: 677) and Testnet (Chain ID: 968).
Mainnet​
Shared Infrastructure — Mainnet​
ContractAddressDescription
WBOT0xD5452816194a3784dBa983426cCe7c122F4abd30Wrapped BOT (ERC-20 representation of native BOT)
Multicall30x47FA21f684bBAD707A53a0f9BE59F1422F46C265Batch contract calls
Permit20x8366170f09a04f715a13549D616a06aED16Db7c3Signature-based token approvals
Universal Router0xaE6ae8630f7A888dEc0B9195C85F7515d5887655Unified swap entry for V2 & V3
BDEX V2 — Mainnet​
V2 Factory0x117115f3B72C8d1989178089A67D0C26f8EE0AA3Creates and manages all V2 trading pairs
V2 Router020x1414eD29FdFD322c3c0a830330ed982E2D629e76Routes swaps and manages liquidity operations
pairInitCodeHash0xa075aa7c03cb5559a4c6202459721232c21e18148152410f6beec063e8499e6cCREATE2 init code hash for V2 pairs
BDEX V3 — Mainnet​
V3 Factory0x1C51c173323ec11BB4e3C4fD2314c225Dc4b5419Creates and manages all V3 pools
SwapRouter0x07032d47A1b9f8460cBeE9dC17c1d3E438693929Executes V3 swaps (single & multi-hop)
QuoterV20x034A705b36067cff99ABf5C662Be881cBd8d0176Off-chain quote simulation
NonfungiblePositionManager0xDAc3FcFF004d8a8675b94E44941A1a2e3b240090Manages LP positions as ERC-721 NFTs
Common Tokens (Mainnet)​
TokenSymbolDecimalsAddress
Wrapped BOTWBOT180xD5452816194a3784dBa983426cCe7c122F4abd30
Tether USDUSDT60xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C
Testnet​
Shared Infrastructure — Testnet​
WBOT0xD5452816194a3784dBa983426cCe7c122F4abd30Wrapped BOT (ERC-20 representation of native BOT)
Multicall30x47FA21f684bBAD707A53a0f9BE59F1422F46C265Batch contract calls
Permit20xaE85b2bc7578F8Ca9217900a2D548151F96447deSignature-based token approvals
Universal Router0x73Be0A1d8011B335A7aBeF6c45544E8ca4448AB5Unified swap entry for V2 & V3
BDEX V2 — Testnet​
V2 Factory0x65b8e98ceA190d8c28B3e4716402027f634d15a3Creates and manages all V2 trading pairs
V2 Router020xD6425a02f0845B8D99e349C34D2E7A576E177345Routes swaps and manages liquidity operations
pairInitCodeHash0x9d2cc5d1f5560e2a4119c794e0fa625b8c50af562e72436c234ec1addb77de47CREATE2 init code hash for V2 pairs
BDEX V3 — Testnet​
V3 Factory0x1C51c173323ec11BB4e3C4fD2314c225Dc4b5419Creates and manages all V3 pools
SwapRouter0x07032d47A1b9f8460cBeE9dC17c1d3E438693929Executes V3 swaps (single & multi-hop)
QuoterV20x034A705b36067cff99ABf5C662Be881cBd8d0176Off-chain quote simulation
NonfungiblePositionManager0xDAc3FcFF004d8a8675b94E44941A1a2e3b240090Manages LP positions as ERC-721 NFTs
Common Tokens (Testnet)​
Wrapped BOTWBOT180xD5452816194a3784dBa983426cCe7c122F4abd30
Tether USDUSDT60x75edC9335175Fc0552D51D48439F229c10420fe3

---

## Core Concepts

Source: https://dev-docs.botchain.ai/docs/DEX/core-concepts/

DEX
Core Concepts
AMM (Automated Market Maker)​
BDEX uses the AMM model to enable permissionless token trading without order books. Liquidity providers deposit token pairs into pools, and traders swap against these pools using deterministic pricing algorithms.
Two AMM Models Supported:
ModelProtocolFormulaUse Case
Constant ProductBDEX V2x × y = kSimple, universal, lower gas cost
Concentrated LiquidityBDEX V3Liquidity within price rangesCapital efficient, advanced LP strategies
Liquidity Pools​
A liquidity pool holds reserves of two tokens. Anyone can provide liquidity by depositing both tokens in the correct ratio and receive LP tokens (V2) or an NFT position (V3) representing their share.
V2 Pools: Each pair has exactly one pool with a flat 0.30% fee
V3 Pools: Each pair can have multiple pools at different fee tiers (0.05%, 0.30%, 1.00%)
Fee Structure​
ItemV2V3
Swap Fee0.30% (fixed)0.05% / 0.30% / 1.00%
LP Fee Share100% to LPs100% to LPs (in active range)
Slippage & Price Impact​
Slippage is the difference between the expected output and actual output of a swap. Price impact increases with trade size relative to pool liquidity.
Always set amountOutMin for V2 or amountOutMinimum for V3 and Universal Router flows to protect against excessive slippage
Recommended slippage tolerance: 0.1% - 1.0% for major pairs, up to 5% for low-liquidity tokens
Use the Routing API, V3 QuoterV2, or V2 getAmountsOut to preview swap results before submitting transactions
Tick & Tick Spacing (V3 Only)​
In V3, liquidity is placed within price ranges defined by ticks. Available tick spacing depends on the selected fee tier. See the BDEX V3 section for details.

---

## Introduction to DEX on BOT Chain

Source: https://dev-docs.botchain.ai/docs/DEX/introduction/

DEX
Introduction to DEX on BOT Chain
BOT Chain is a high-performance EVM-compatible Layer 1 blockchain featuring 0.75-second block times, Physical Finality, and extremely low gas fees — making it an ideal platform for building fast and efficient Decentralized Exchanges (DEXs).
Why Build a DEX on BOT Chain?​
Ultra-low gas fees — Significantly reduce costs for swaps and liquidity provision
Fast Finality — Minimize Impermanent Loss risk for liquidity providers
MEV Resistance — Create a fairer trading environment
Full EVM Compatibility — Easily fork Uniswap V2, PancakeSwap, or Uniswap V3
Quick Start Path​
Contract Addresses
Token Swap Guide
Ready to build the next leading DEX on BOT Chain? Let's get started!

---

## Developers

Source: https://dev-docs.botchain.ai/docs/Developers/

📄️ Quick Guide
If you are a developer looking to build applications on the BOT Chain, this document provides all the essential information you need.

---

## Blob API

Source: https://dev-docs.botchain.ai/docs/Developers/blob-api/

Developers
Blob API
eth_getBlobSidecarByTxHash​
Parameters​
Hash String (REQUIRED)
HEX String - the hash of the transaction
full_blob_flag Boolean (OPTIONAL)
Default is true. If true it returns the full blob info, if false only return first 32 bytes of blobs.
curl -X POST "http://localhost:8545/" -H "Content-Type: application/json"  --data '{"jsonrpc":"2.0","method":"eth_getBlobSidecarByTxHash","params":["0x377d3615d2e76f4dcc0c9a1674d2f5487cba7644192e7a4a5af9fe5f08b60a63"],"id":1}'
curl -X POST "http://localhost:8545/" -H "Content-Type: application/json"  --data '{"jsonrpc":"2.0","method":"eth_getBlobSidecarByTxHash","params":["0x377d3615d2e76f4dcc0c9a1674d2f5487cba7644192e7a4a5af9fe5f08b60a63", false],"id":1}'
eth_getBlobSidecars​
BlockNumber QUANTITY|TAG
HEX String - an integer block number
HEX String - the hash of the block
String "earliest" for the earliest/genesis block
String "latest" - for the latest mined block
String "safe" - for the latest justified head block
String "finalized" - for the latest finalized block
Default is true. If true it returns the full blob info, if false only return first 32 bytes of blobs.
curl -X POST "http://localhost:8545/" -H "Content-Type: application/json"  --data '{"jsonrpc":"2.0","method":"eth_getBlobSidecars","params":["latest"],"id":1}'
curl -X POST "http://localhost:8545/" -H "Content-Type: application/json"  --data '{"jsonrpc":"2.0","method":"eth_getBlobSidecars","params":["0xc5043f", false],"id":1}'

---

## BOT Chain Node Configuration: Best Practices

Source: https://dev-docs.botchain.ai/docs/Developers/bot-chain-node-configuration-best-practices/

Developers
BOT Chain Node Configuration: Best Practices
Hardware Specifications​
To ensure optimal performance and reliability, it is crucial to select the appropriate node type based on your specific requirements for transaction processing and state querying on the BOT Chain.
Archive & Full Node Deployment Guide ​
Clone the repository and enter the directory
bash
git clone https://github.com/bl-BOHR/node-deploy.git && cd node-deploy
Grant execution permissions (only required the first time on Linux)
chmod +x BOHR_full_node.sh BOHR_archive_node.sh bin/geth*
Initialize and start the node
Full node:
./BOHR_full_node.sh reset
Archive node:
./BOHR_archive_node.sh reset
View logs
Node logs are located at:
.local/fullnode/node/BOHR-node.log
Recommended Configuration​
For users requiring access to the latest world state in a lightweight mode, the fast node is the ideal choice. It demands less from your system's CPU and disk space.
Processor: Minimum 2-core CPU.
Memory: At least 4 GB RAM.
Storage: Solid State Drive (SSD) with a minimum capacity of 128GB.
Network: Stable and high-speed internet connection, minimum 1 MBps.
Archive Node​
For comprehensive access to the entire historical world state of the BOT  mainnet, consider deploying an Archive Node. Detailed instructions are available at BOT Chain GitHub repository.（An external link to our repository is required here.）
Processor: Minimum 4-core CPU.
Memory: At least 8 GB RAM.
Storage: SSD with a minimum capacity of 1TB (NVME SSDs are recommended for optimal performance).
Network: Stable and high-speed internet connection, minimum 2 MBps.
Full Node​
To obtain the latest world state and verify the validity of the state or to generate data proofs, a standard Full Node is suitable.
Storage: Solid State Drive (SSD) with a minimum capacity of 1TB.
Network: Stable and high-speed internet connection, minimum 2 MBps.
Peers Configuration​
Mainnet​
There is no need to specify static nodes, only Bootnodes are required for mainnet which are already configured in the code. Also, make sure to use the config.toml file from the latest release.
Testnet​
Testnet still need to configure the StaticNodes manually and hence, the StaticNodes list is contained in the latest release's config.toml.
Troubleshooting for no peers on testnet​
Check for configuration issues like wrong chain id, wrong config file/dir.
Make sure to update the config.toml file as per the latest release
Don't use bootnodes on testnet, it's not required.
Deleting the geth/nodes and geth/nodekey file/dir might help
Re-download the snapshot and try again.
Store Your BOT with a Hardware Wallet​
The most valuable assets of a validator are two keys: one for signing transactions and another for signing blocks
Securing Your Full Node RPC from Hackers​
Please do not expose your RPC endpoints to public networks.
Account Private keys​
To protect your BOT, do not share your 24 words with anyone. The only person who should ever need to know them is you. In short, HSMs are affordable, performant and portable pieces of hardware that help to securely generate, store and manage your private keys. Malware attacks and remote extraction of private keys are much more difficult when an HSM is configured properly.
Software Vulnerabilities​
To protect your BOT, you should only download software directly from official sources, and make sure that you're always using the latest, most secure version
Running Server as a Daemon​
It is important to keep geth running at all times. There are several ways to achieve this, and the simplest solution we recommend is to register geth as a systemd service so that it will automatically get started upon system reboots and other events.
Set up a Backup Node​
Run validator node in archive mode
Shut down nodes gracefully
Active monitoring with tools
Steps to Run a Backup Node​
Install the latest version of geth
Sync to the latest height using fast sync mode. You can either download the latest snapshot or start fast sync once your node is fully synced
Shut down your node gracefully kill -HUP $(pgrep geth)
Restart your node.
Why Node will be Offline for a While After Restart? or What will Happen If the Client is Force Killed?​
After running (synchronized) for a long period of time and being abruptly terminated, only archived nodes are expected to quickly re-synchronize upon restart.
Steps to reproduce:
Run the node synchronized for a period of time.
Abruptly kill the node (kill -9 or system crash).
Restart the node, observe where it resynchronizes from block height 1 hour ago.
Reasons
If Geth crashes (or is not shut down gracefully), the recent state held in memory is lost and needs to be regenerated. It takes Geth a long time to restore the states.
The root reason is that geth does flush the state trie periodically. The period is defined as trieTimeout in config.toml.
How to Upgrade a Backup Node to Become a Validator Node?​
You can stop mining new blocks by sending commands to geth console
Connect to your validator node with geth attach ipc:path/to/geth.ipc
miner.stop()
Then, let backup node resume validating ,
miner.start()
Securing the Validators​
Each validator candidate is encouraged to run its operations independently, as diverse setups increase the resilience of the network. Due to the high amount invested by validators, it is highly essential to protect them against different DoS and DDoS attacks. In this section, we discuss the security mechanism adopted by BOT Chain for its validators.
Sentry Nodes (DDOS Protection)​
Validators are responsible for ensuring that the network can sustain denial of service attacks. One recommended way to mitigate these risks is for validators to carefully structure their network topology in a so-called sentry node architecture. Sentry nodes can be quickly spun up or change their IP addresses. Because the links to the sentry nodes are in private IP space, an internet-based attacked cannot disturb them directly. This will ensure validators block proposals and votes always make it to the rest of the network.
To setup your sentry node architecture, you can follow the instructions below:
Build a private network and setup trusted private connections between the validator node and its sentry
Please do not expose your validator fullnode RPC endpoints to the public network.
Install your fullnode
Set sentry as peers for the validator node
On the console of the sentry node, run admin.nodeInfo.enode You should get something similar to this.
enode://f2da64f49c30a0038bba3391f40805d531510c473ec2bcc7c201631ba003c6f16fa09e03308e48f87d21c0fed1e4e0bc53428047f6dcf34da344d3f5bb69373b@[::]:30306?discport=0
!!! Note: [::] will be parsed as localhost (127.0.0.1). If your nodes are on a local network, check each individual host machine and find your IP with ifconfig If your peers are not on the local network, you need to know your external IP address (use a service) to construct the enode URL. Copy this value and in the console of the first node run,
Update config.toml file of validator node
# make node invisible
NoDiscovery = true
# connect only to sentry
StaticNodes = ["enode://f2da64f49c30a0038bba3391f40805d531510c473ec2bcc7c201631ba003c6f16fa09e03308e48f87d21c0fed1e4e0bc53428047f6dcf34da344d3f5bb69373b@[10.1.1.1]:30306"]
This will return true if successful, but that doesn't mean the node was added successfully.
To confirm run admin.peers and you should see the details of the node you just added.
That way, your validator node will try to peer with your provided sentry nodes only.
Confirm the connection
To confirm run admin.peers and you should see the details of the node you just added.
Firewall Configuration​
geth uses several TCP ports for different purposes.
geth uses a listener (TCP) port and a discovery (UDP) port, both on 31000 by default.
If you need to run JSON-RPC, you'll also need TCP port 8545. Note that JSON-RPC port should not be opened to the outside world, because from there you can do admin operations.

---

## Claim test tBOT Tokens

Source: https://dev-docs.botchain.ai/docs/Developers/claim-test-tbot-tokens/

Developers
Claim test tBOT Tokens
Claim tBOT from Online Faucet​
Follow these steps to claim test tBOT on BOT Chain Testnet:
Switch your wallet to BOT Chain Testnet (Chain ID: 968).
Open https://faucet.botchain.ai/basic.
Enter your wallet address and complete verification.
After claiming, click the returned tx hash to view the transaction on https://scan.bohr.life/.
Limits: Each address can claim up to 10 tBOT every 24 hours. tBOT has no real-world value.

---

## EOA Paymaster

Source: https://dev-docs.botchain.ai/docs/Developers/eoa-paymaster/

Developers
EOA Paymaster
Overview​
EOA Based Paymaster​
This document introduces a paymaster solution specifically designed for Externally Owned Account (EOA) wallets, differing from the paymaster defined in EIP-4337. With minimal modifications, wallets can integrate this solution to support gas fee sponsorship, significantly enhancing user experience.
What is EOA-based Paymaster​
The paymaster in EIP-4337 (Account Abstraction via Entry Point Contract Specification) is a crucial component designed to enhance the flexibility and user experience of Ethereum transactions. It allows a third party to pay for a user's transaction fees, removing the need for users to hold ETH to pay for gas.
While EIP-4337 introduced the revolutionary concept of paymasters for smart contract wallets, a significant portion of the Ethereum ecosystem still relies on EOAs. Recognizing this, this presents a groundbreaking paymaster solution specifically designed for EOA wallets. This innovation brings the benefits of transaction sponsorship and enhanced user experience to the broader BOT Chain user base, without requiring a shift to smart contract wallets. The EOA paymaster solution aims to democratize access to sponsored transactions, making blockchain interactions more user-friendly and cost-effective for millions of existing EOA wallet users.
How does it Work​
A significant shift occurs in transaction processing:
Validator Role: Validators no longer verify individual transaction gas prices within a block.
Transaction Bundling: Private transactions are grouped into bundles and submitted to builders.
Prioritization: Builders prioritize based on the aggregate gas price of each bundle.
Intra-Bundle Flexibility: Within a single bundle, gas prices can vary, allowing for zero-fee and higher-fee transactions to coexist.
This flexibility enables innovative features such as sponsored gas fees and gasless transactions.
Definitions​
Bundle: An ordered array of transactions that execute atomically, ensuring all transactions in the bundle are processed together or not at all.
Builder: A new stakeholder in the MEV supply chain responsible for constructing blocks. Builders package transaction bundles, individual transactions from the public txpool, and private transaction order flow into proposed blocks.
Proposer: A validator who selects the most profitable block from multiple builders' proposals for inclusion in the blockchain.
Paymaster: An infrastructure component that enables transaction sponsorship, allowing self or third parties to cover gas fees.
Sponsor Policy: A set of rules defined by the gas sponsor to determine which transactions qualify for sponsorship. This may include criteria such as whitelisted transaction senders or specific transaction types.
Overall Workflow​
The gas sponsorship process involves several key components and steps:
User Initiation:
A user prepares a transaction using any compatible wallet.
The wallet sets the gas price to zero for potentially sponsored transactions.
Paymaster Submission:
The wallet submits the zero-gas-price transaction to the Paymaster.
Sponsor Policy Verification:
The Paymaster checks the transaction against existing sponsor policies.
Policies may include criteria such as sender/recipient addresses, token types, or transaction limits.
Sponsorship Processing:
If the transaction is eligible for sponsorship: a. The Paymaster creates a sponsor transaction with a higher gas price. b. The original user transaction and the sponsor transaction are combined into a bundle.
If not eligible, the transaction is rejected or returned to the user for normal processing.
Bundle Creation and Submission:
This bundle is submitted to multiple MEV builders.
Builder Selection and Block Proposal:
MEV builders incorporate the bundle into their block proposals.
Blockchain Inclusion:
Proposers (validators) select the most profitable block from the builders' proposals.
The selected block, containing both the user's original transaction and the sponsor's transaction, is added to the blockchain.
This ensures atomic execution of both transactions.
Post-Transaction Processing:
The Paymaster Manager updates the sponsor's account, deducting the appropriate amount for the sponsored gas.
This solution enables seamless gas sponsorship without requiring significant changes to existing wallet infrastructures. It provides a flexible system that can accommodate various sponsorship models while maintaining the security and integrity of the blockchain network.
Paymaster Infra​
Ready to enable gasless experiences in your app or wallet? Here's some helpful information on paymaster infrastructure that are available on BOT Chain:
Nodereal. The MegaFuel powered by Nodereal is a paymaster implementation based on BOT Chain Paymaster for EOA Wallet. With minimal modifications, wallets can integrate MegaFuel to support gas fee sponsorship, significantly enhancing user experience. At the same time, sponsors can customize their sponsorship on MegaFuel, allowing sponsored users to send gasless transactions.
Paymaster API Spec​
To facilitate widespread adoption and ensure interoperability across diverse wallet implementations, it is crucial to establish a standardized set of interface specifications for paymasters. This standardization will enable wallet developers to integrate gas sponsorship features efficiently and consistently, regardless of the specific paymaster service they choose to utilize.
API Spec​
Paymaster needs to implement a JSON-RPC API called pm_isSponsorable, so that it can return sponsor and policy information to wallets. Paymaster also needs to implement eth_sendRawTransaction JSON-RPC API. The detailed API Specs are defined as below:
pm_isSponsorable​
Request Parameters
jsonrpc: The JSON-RPC protocol version ("2.0").
id: A unique identifier for the request (1 in this example).
method: The method name to be invoked ("pm_isSponsorable").
params: An array containing a single object with the following fields:
to: The recipient address of the transaction.
from: The sender address of the transaction.
value: The value of the transaction in hexadecimal.
data: Additional data for the transaction in hexadecimal.
gas: The gas limit of the transaction in hexadecimal.
Example:
{
"jsonrpc": "2.0",
"id": 1,
"method": "pm_isSponsorable",
"params": [
"to": "0x...", // an address
"from": "0x...", // an address"value": "0xa1",
"data": "0x",
"value": "0x1b4",
"gas" : "0x101b4"
}
]
Response Fields
id: The unique identifier for the request (1 in this example).
result: An object containing the sponsorship policy details:
(Required) Sponsorable: A boolean indicating whether the transaction is sponsored (true or false).
(Required) SponsorPolicy:. The name of the sponsor policy.
"result": {
"Sponsorable": true,
"SponsorPolicy": "a sample policy name"
eth_sendrawtransaction​
The eth_sendrawtransaction API implemented by the Paymaster should follow this Ethereum API Spec. The client can create a new message call transaction or a contract creation for signed transactions via eth_sendrawtransaction API.
The params should contain the signed transaction data.
"method": "eth_sendRawTransaction",
"0x02f86a6102850df8475800850df84758000a94cd9c02358c223a3e788c0b9d94b98d434c7aa0f18080c080a0bcb0e8ffa344e4b855c6e13ee9e4e5d22cff6ad8bd1145a93b93c5d332100c2ca03765236eba5fbb357e35014fd19ba4b3c6b87f3793bd14dddf7913fc8dcc88bf"
DATA, 32 Bytes - the transaction hash.
"result": "0xe670ec64341771606e55d6b4ca35a1a6b75ee3d5145a99d05921026d1527331"
Wallet Integration​
This guide outlines the steps for wallet developers to integrate paymaster services, enabling gas fee sponsorship for their users. By following these standards, wallets can offer seamless, gasless transactions across multiple paymaster providers.
Interaction Workflow​
Integration involves modifying the transaction creation and sending process to interact with paymaster services.
The main steps are:
Transaction Preparation:
When a user initiates a transaction, first call gm_sponsorable to check if it's eligible for sponsorship.
If sponsorable, set the transaction's gas price to zero.
User Notification:
Inform the user that the transaction will be gas-free and sponsored by the "policy name" returned by the API.
Transaction Signing:
Have the user sign the zero-gas-price transaction.
Submission to Paymaster:
Send the signed transaction to the paymaster using eth_sendRawTransaction.
Response Handling:
Process the paymaster's response:
If successful, inform the user that the transaction is submitted.
If failed, consider falling back to normal transaction processing or informing the user of the failure.
Transaction Monitoring:
Monitor the transaction status as usual.
Best Practice​
Always check sponsorability before modifying gas prices.
Provide clear user feedback about sponsorship status.
Implement proper error handling for cases where sponsorship fails.
Consider fallback mechanisms for non-sponsored transactions.
Try Gasless Transaction​
Experience Paymaster in mainstream Wallets​
Several mainstream cryptocurrency wallets have already implemented Paymaster integration. This tutorial will guide you through the experience of sending gasless transactions to paymaster integrated wallets.
Paymaster Integrated Wallets​
Wallets with integrated Paymaster functionality offer a seamless experience for users. These wallets automatically detect whether a transaction is eligible for sponsorship. When a transaction qualifies, the wallet sets the gas price to zero without any user intervention.
To illustrate this, we'll walk through the process by transferring stable coin on BOT Chain.

---

## JSON-RPC-Endpoint

Source: https://dev-docs.botchain.ai/docs/Developers/json-rpc-endpoint/

Developers
JSON-RPC-Endpoint
JSON-RPC endpoints refers to the network location where a program could transfer its RPC requests to access server data. Once you connect a decentralized application to an RPC endpoint, you can access the functionalities of different operations, which could enable real-time usage of blockchain data. BOT Chain provides several RPC endpoints for connecting into both its Mainnet and Testnet. In this section, we list the JSON-RPC endpoints that can be used for connecting to BOT Chain.
One-click adding BOT network​
Visit the ChainList and connect to your wallet. It will add alive RPC endpoints.
RPC Endpoints for BOT Chain​
eth_getLogs is disabled on below Mainnet endpoints. Please use 3(rd) party endpoints from here. If you need to pull logs frequently, we recommend using WebSockets to push new logs to you when they are available.
BOT Mainnet (ChainID 677)​
https://rpc.botchain.ai
BOT Chain Testnet (ChainID 968)​
https://rpc.bohr.life
Starting HTTP JSON-RPC​
You can start the HTTP JSON-RPC with the –http flag
## mainnet
## testnet
JSON-RPC API List​
BOT Chain is EVM-compatible and strives to be as compatible as possible with the Go-Ethereum API. However, BOT Chain also has unique features, such as faster finality and the storage of blob data on the execution layer, which require their own specialized APIs.
Geth(Go-Ethereum) API​
BOT Chain is nearly fully compatible with the Geth APIs. Any exceptions or incompatibilities are explicitly listed. If you're looking for detailed usage of a specific API, you will most likely find the answer in the following link:
Geth JSON-RPC API documentation.
Finality​
Ethereum's PoS consensus protocol, known as "Gasper," is built on LMD-GHOST (a fork choice rule) and Casper FFG (a finality gadget). Similarly, BOT Chain's consensus protocol, called "Parlia," is constructed on top of a difficulty-based fork choice mechanism with FFG, as described in BEP-126. To further enhance BOT Chain's throughput, validators are allowed to produce multiple consecutive blocks, as explained in BEP-341. These differences result in BOT Chain having a unique finality process compared to Ethereum.
Blob​
BOT Chain implements EIP-4844, which supports Shard Blob Transactions. For more details, please refer to the Blob API documentation.
Other BOT Chain API​
BOT Chain implements some other APIs

---

## Node Types

Source: https://dev-docs.botchain.ai/docs/Developers/node-types/

Developers
Node Types
Run BOT Chain ​
Archive Node​
Refer to https://github.com/bl-BOHR/node-deploy
Fast Node ​
Node Maintenance​
1. Binary​
All the clients are suggested to upgrade to the latest release. The latest version is supposed to be more stable and has better performance.
2. Storage​
2.1 Prune State​
According to the test, the performance of a full node will degrade when the storage size reaches a high volume (previously it was 1.5TB, which is an experimental value, the latest number needs to be updated). We suggest that the fullnode always keep light storage by pruning the storage.
2.2 How to Prune​
Stop the BOT Chain node.
Run nohup geth snapshot prune-state --datadir {the data dir of your BOT node} &. It will take 3-5 hours to finish.
Start the node once it is done.
The maintainers should always have a few backup nodes in case one of the nodes is getting pruned. The hardware is also important, make sure the SSD meets: 500 GB of free disk space, solid-state drive(SSD), gp3, 8k IOPS, 500 MB/S throughput, read latency <1ms (if node is started with snap sync, it will need NVMe SSD).
2.3 Prune Ancient Data in Real Time​
Ancient data is block data that is already considered immutable. This is determined by a threshold which is currently set at 90000. This means that blocks older than 90000 are considered ancient data. We recommend the --prunceancient flag to users who don't care about the ancient data. This is also advised for users who want to save disk space, since this will only keep data for the latest 90000 blocks. Note that once this flag is turned on, the ancient data will not be recovered again and you cannot go back running your node without this flag in the start-up command.
2.4 How to use the flag​
./geth --tries-verify-mode none --config /server/config.toml --datadir /server/node --cache 8000 --rpc.allow-unprotected-txs --history.transactions 0 --pruneancient=true --syncmode=full
2.5 Prune Block Tools​
A new offline feature introduced in v1.1.8 to prune undesired ancient block data. It will discard blocks, receipts, and headers in the ancient database to save space.
How to prune​
Stop the BOT Chain Node.
Run
./geth snapshot prune-block --datadir /server/node --datadir.ancient ./chaindata/ancient --block-amount-reserved 1024
block-amount-reserved is the number of ancient data blocks that you want to keep after pruning.
3. Light Storage​
When the node crashes or been force killed, the node will sync from a block that was a few minutes or a few hours ago. This is because the state in memory is not persisted into the database in real time, and the node needs to replay blocks from the last checkpoint once it starts. The replaying time depends on the configuration TrieTimeout in the config.toml. We suggest you raise it if you can tolerate long replaying time, so the node can keep light storage.

---

## Quick Guide

Source: https://dev-docs.botchain.ai/docs/Developers/quick-guide/

Developers
Quick Guide
If you are a developer looking to build applications on the BOT Chain, this document provides all the essential information you need.
Getting Started​
BOT Chain is a high-performance blockchain network.
Since BOT Chain is EVM-compatible, your existing Ethereum smart contract skills will seamlessly transfer to BOT Chain.
Connecting​
Here are some resources to help you get connected to the BOT network:
Wallet Configuration
Test net
Chain ID：968
RPC：https://rpc.bohr.life
Native Token：BOT
Total Supply：150 Million
Explorer：https://scan.bohr.life/
Main net
Chain ID：677
RPC：https://rpc.botchain.ai
Explorer：https://scan.botchain.ai
Get Tokens​
BOT is the native utility token of BOT Chain and is used to pay transaction fees. For the testnet, you can obtain test tokens from the BOT Chain faucet.
BOT Chain Testnet Faucet
For the mainnet, BOT tokens are currently available exclusively via our official DEX, where you can swap for BOT using supported assets.
B DEX
JSON-RPC API​
Interacting with BOT Chain requires sending requests to specific JSON-RPC API methods. BOT Chain's APIs are compatible with Geth.
Developer Tools​
Explorer
BOTScan (Testnet)
BOTScan (Mainnet)
SDK. If you are only using the SDK for Ethereum-compatible functions, then all Ethereum SDKs should work with BOT Chain.
ethers.js
web3.js
Tools
Remix
Hardhat
Foundry
Indexing
TheGraph
Covalent
Others
Wallets
BO Wallet
Metamask

---

## BOT Chain Developer Documentation

Source: https://dev-docs.botchain.ai/docs/intro/

BOT Chain Developer Documentation
BOT Chain is an EVM-compatible Layer 1 for DePIN and AI applications. This documentation covers network configuration, RPC, test tokens, contract deployment, verification, and ecosystem protocols.
Key Features & Advantages​
Full Ethereum Virtual Machine (EVM) Compatibility
BOT Chain is 100% EVM-compatible, allowing developers to migrate Ethereum-based DApps and DeFi projects with almost zero code changes. Popular tools like MetaMask, Trust Wallet, Truffle, and Remix work out of the box.
Ultra-Low Fees & Lightning-Fast Confirmations
With the average transaction fees around $0.06 (as of early 2025) — far below most EVM chains during congestion — and block times of ≈0.75 seconds, BOT Chain delivers near-instant, cost-effective transactions and a noticeably smoother user experience.
Role of the BOT Token​
BOT is the native utility and governance token of the BOT Chain ecosystem:
Paying Transaction Fees – the economical fuel for all on-chain activity
Staking – delegate BOT to validators, earn rewards, and help secure the network
Governance – BOT holders vote on protocol upgrades and future direction
Future Prospects​
BOT Chain is emerging as a leading force in blockchain, especially in DeFi and decentralized applications. By combining blazing speed, minimal costs, and deep interoperability, it directly tackles today's most critical scalability and usability challenges. With continuous innovation and a rapidly growing community, BOT Chain is well-positioned to power the next wave of mainstream blockchain adoption.

---

## Introduction

Source: https://dev-docs.botchain.ai/docs/introduction/

Introduction
BOT Chain is an innovative blockchain solution that delivers full programmability and native interoperability across the entire ecosystem. It operates on a Proof of Staked Authority (PoSA) consensus mechanism, enabling short block times and significantly lower transaction fees.The validators with the highest bonded stake are elected to produce blocks. Comprehensive slashing mechanisms—including double-sign detection, malicious voting detection, and other penalty logic—ensure the network's security, stability, and finality.Beyond the active validator set, BOT Chain maintains a group of backup validators known as "Candidates." These candidate validators can also produce blocks and collect gas fees on the mainnet (though with much lower probability than active validators). Unavailable or misbehaving candidates are still subject to slashing, albeit at a reduced rate. This design provides strong economic incentives for candidates to stay online and contribute to network security.In extreme scenarios—such, such as when a majority of active validators go offline due to an attack—Candidate Validators can report stalled block production, help resume the chain, and trigger a re-election of the active validator set.
BOT Chain also offers:
Full EVM compatibility – supports all existing Ethereum tooling while delivering faster finality and dramatically lower fees.
Fast finality – transactions are typically finalized within two blocks.
Native interoperability – built-in, efficient cross-chain communication and asset transfers.
Self-sovereign blockchain – secured by an elected validator set with robust on-chain governance.
High-performance scaling – optimized for dApps that demand speed and a seamless user experience.
Decentralized governance via PoSA – combining security with genuine community participation. The native BOT token serves as both gas for smart-contract execution and the staking asset for network security and governance.
BOT Chain is built from the ground up to be fast, affordable, interoperable, and community-driven—making it an ideal foundation for the next generation of DeFi and decentralized applications.

---

## Fast Finality

Source: https://dev-docs.botchain.ai/docs/introduction/fast-finality/

Introduction
Fast Finality
Finality is critical for blockchain security, once the block is finalized, it wouldn't be reverted anymore. The fast finality feature is very useful. The users can make sure they get the accurate information from the latest finalized block, then they can decide what to do next instantly.
BOT Chain users are encouraged to wait until receiving blocks sealed by more than ⅔*N+1 different validators. In that way, the BOT Chain can tolerate less than ⅓*N Byzantine validators. For example, with 21 validators, if the block time is 3 seconds, the ⅔*N+1 different validator seals will need a time period of (⅔*21+1)*3 = 45 seconds. Any critical applications for BOT Chain may have to wait for ⅔*N+1 to ensure a relatively secure finality. With the above enhancement by slashing mechanism, ½*N+1 or even fewer blocks are enough as confirmation for most transactions.
When the feature Fast Finality is enabled. The chain will be finalized within two blocks if ⅔*N or more validators vote normally, otherwise the chain has a fixed number of blocks to reach probabilistic finality as before.

---

## Proof of Staked Authority

Source: https://dev-docs.botchain.ai/docs/introduction/proof-of-staked-authority/

Introduction
Proof of Staked Authority
Although Proof-of-Work (PoW) has been recognized as a practical mechanism to implement a decentralized network, it is not friendly to the environment and also requires a large number of participants to maintain security.
Ethereum and some other blockchain networks, such as MATIC Bor, TOMOChain, GoChain, xDAI, do use Proof-of-Authority(PoA) or its variants in different scenarios, including both testnet and mainnet. PoA provides some defense to 51% attack, with improved efficiency and tolerance to certain levels of Byzantine players (malicious or hacked). It serves as an easy choice to pick as the fundamentals.
Meanwhile, the PoA protocol is most criticized for being not as decentralized as PoW, as the validators, i.e. the nodes that take turns to produce blocks, have all the authorities and are prone to corruption and security attacks. Other blockchains, such as EOS and Lisk both, introduce different types of Delegated Proof of Stake (DPoS) to allow the token holders to vote and elect the validator set. It increases the decentralization and favors community governance.
BOT Chain here proposes to combine DPoS and PoA for consensus, so that:
Blocks are produced by a limited set of validators
Validators take turns to produce blocks in a PoA manner, similar to Ethereum's Clique consensus design
Validator sets are elected in and out based on a staking based governance
Fast finalization can greatly improve user experience. The Fast Finality feature will be enabled upon the coming Plato upgrade. This will be a major advantage of BOT Chain, and many dapps will benefit from it.
The consensus protocol of BOT Chain fulfills the following goals:
Short blocking time, 0.75 seconds on the mainnet.
It requires quite a short time to confirm the finality of transactions.
There is no inflation of native token: BOT, the block reward is collected from transaction fees, and it will be paid in BOT.
It is 100% compatible with the Ethereum system.
It allows modern proof-of-stake blockchain network governance.

---

## Reward

Source: https://dev-docs.botchain.ai/docs/introduction/reward/

Introduction
Reward
All the BOT Chain validators in the current validator set will be rewarded with transaction fees in BOT. As BOT is not an inflationary token, there will be no mining rewards like what Bitcoin and Ethereum networks generate, and the gas fee is the major reward for validators. After the coming Plato upgrade, part of the fees collected will be used as reward for finality voting. As BOT is also utility tokens with other use cases, delegators and validators will still enjoy other benefits of holding BOT.
The reward for validators is the fees collected from transactions in each block. Validators can decide how much to give back to the delegators who stake their BOT to them, in order to attract more staking. Every validator will take turns to produce the blocks in the same probability (if they stick to 100% liveness), thus, in the long run, all the stable validators may get a similar size of the reward. Meanwhile, the stakes on each validator may be different, so this brings a counter-intuitive situation that more users trust and delegate to one validator, they potentially get less reward. So rational delegators will tend to delegate to the one with fewer stakes as long as the validator is still trustworthy (insecure validator may bring slashable risk). In the end, the stakes on all the validators will have less variation. This will actually prevent the stake concentration and "winner wins forever" problem seen on some other networks.

---

## Security

Source: https://dev-docs.botchain.ai/docs/introduction/security/

Introduction
Security
Given there are more than ½*N+1 validators are honest, PoA based networks usually work securely and properly. However, there are still cases where a certain amount Byzantine validators may still manage to attack the network, e.g. through Clone Attack. BOT Chain does introduce Slashing logic to penalize Byzantine validators for double signing or inavailability. This Slashing logic will expose the malicious validators in a very short time and make the "Clone Attack" very hard or extremely non-beneficial to execute.

---

## Staking and Governance

Source: https://dev-docs.botchain.ai/docs/introduction/staking-and-governance/

Introduction
Staking and Governance
Proof of Staked Authority brings in decentralization and community involvement. Its core logic can be summarized as the below. You may see similar ideas from other networks, especially Cosmos and EOS.
Token holders, including the validators, can put their tokens "bonded" into the stake. Token holders can delegate their tokens onto any validator or validator candidate, expecting it to become an actual validator, and later they can choose a different validator or candidate to re-delegate their tokens.
All validator candidates will be ranked by the number of bonded tokens on them, and the top ones will become the real validators.
Validators can share (part of) their blocking reward with their delegators.
Validators can suffer from "Slashing", a punishment for their bad behaviors, such as double sign and/or instability.
There is an "unbonding period" for validators and delegators so that the system makes sure the tokens remain bonded when bad behaviors are caught, the responsible will get slashed during this period.

---

## Validator Creation Guide

Source: https://dev-docs.botchain.ai/docs/staking/validator-creation-guide/

Staking
Validator Creation Guide
This guide outlines the process for creating a new validator on the BOT Chain. The BOT staking dApp is the official tool for creating and managing validators on the BOT Chain.
Testnet: https://staking.bohr.life
Mainnet: https://staking.botchain.ai
Terminology​
Operator Address: The address for creating and modifying validator information on the BOT. You should use this address when connecting to the staking dApp. The corresponding account should have more than 2001 BOT for creating validators and paying transaction fees.
Consensus Address: A unique address for your validator’s node. It is used for consensus engines when mining new blocks. It should be different from the operator's address. If you have an existing validator created on the Beacon Chain, the old consensus address cannot be reused and you should create a new one.
Vote Address: An address used for fast finality voting. If you have an existing validator created on the Beacon Chain, the old vote address cannot be reused and you should create a new one.
BLS Proof: A BLS signature verifying ownership of the vote address.
Identity: For associating a new validator with an existing one from the Beacon Chain. It is useful when delegators migrate their stakes - they can know there is a new validator running by the same validator operator. This is optional unless you’re migrating an old validator.
Steps​
1. Connecting to the dApp​
Please connect to the staking dApp using your Operator Address. MetaMask, and WalletConnect options are available for the step. Make sure that the account has more than 2001 BOT before moving on to the next step.
2. Filling out the form​
Navigate to the dApp and select the Become a Validator button in the right middle of the page to initiate the creation process.
The following information is required to create a validator.
Basic Information​
You’ll need to provide the following details on the Create Validator page:
Validator Name: Choose a name consisting of 3-9 alphanumeric characters, excluding special characters.
Website: Provide a URL to a website with additional information about your validator.
Description: A brief description of your validator.
Addresses​
The following addresses are required:
Consensus Address: A unique address for your validator’s node.
Vote Address: An address used for fast finality voting.
BLS Proof: A BLS signature verifying ownership of the vote address.
Identity: For associating a new validator with an existing one from the Beacon Chain. This is optional unless you’re migrating an old validator.
Generate Consensus Address​
Note: Make sure you are downloading the correct binary based on your machine’s platform, e.g., if you are using MacOS, you should download the geth_mac file. In the following, we will refer to the binary as geth for simplicity.
To create a new account for mining, please use the following command and set a password for the account.
geth account new --datadir ${DATA_DIR}
DATA_DIR: The directory where you want to store your key store files.
This command will return the public address (i.e. consensus address) and the path to your private key. Please backup the key file!
An example consensus address is 0x4b3FFeDb3470D441448BF18310cAd868Cf0F44B5.
If you already have an account for mining, you can use the seed phrase to recover the account.
geth account import --datadir ${DATA_DIR}
If you have created a validator on the Beacon Chain, please use a different one for the consensus address.
Generate Vote Address and BLS Proof​
To create a new BLS account, please use the following command.
geth bls account new --datadir ${DATA_DIR}
DATA_DIR: The directory where you want to store your key store files.
If you already have a voting key, create a bls wallet and use the keyfile to recover it, using the following command.
geth bls account import ${KEY_FILE} --datadir ${DATA_DIR}
DATA_DIR: The backup file for restoring the BLS account.
Then you can get your vote address by running the following command.
geth bls account list --datadir ${DATA_DIR}
An example address is b5fe571aa1b39e33c2735a184885f737a59ba689177f297cba67da94bea5c23dc71fd4deefe2c0d2d21851eb11081f69.
Then you can get your bls proof by running the following command.
geth bls account generate-proof --chain-id ${BOT_CHAIN_ID} ${OPEATOR_ADDRESS} ${VOTE_ADDRESS}
BOT_CHAIN_ID: 677 for BOT mainnet, and 968 for BOT testnet.
OPEATOR_ADDRESS: The address of your account, which will be recognized as the operator of the new validator.
VOTE_ADDRESS: The vote address created in the last step.
An example proof is 0xaf762123d031984f5a7ae5d46b98208ca31293919570f51ae2f0a03069c5e8d6d47b775faba94d88dbbe591c51c537d718a743b9069e63b698ba1ae15d9f6bf7018684b0a860a46c812716117a59c364e841596c3f0a484ae40a1178130b76a5
Create indentity​
Note: Make sure you are downloading the correct binary based on your machine’s platform, e.g., if you are using MacOS, you should download the macos_binary.zip file, and after unzip it your will find botcli (for mainet) and tbotcli(for testnet). In the following, we will refer to binary as botcli for simplicity.
Setup account​
If you have mnemonic, you can import your account by running the following command:
${workspace}/bin/botcli keys add <your-account-name> --recover --home ${HOME}/.botcli
Enter a passphrase for your key:
Repeat the passphrase:
Enter your recovery seed phrase:
You will be asked to set a password for this account and input your mnemonic. After that, you will get your account info.
${workspace}/bin/botcli: The path to the botcli binary executable. For testnet, you should use tbotcli instead.
${HOME}: The folder where you store your account information.
Or if you have a ledger, you can import your account by running the following command:
${workspace}/bin/botcli keys add <your-account-name> --ledger --index ${index} --home ${HOME}/.botcli
${workspace}/bin/botcli: The path to the botcli binary executable. For testnet, you should use tbotcli instead.
${HOME}: The folder where you store your account information.
${index}: The index of the ledger account you want to import.
Get identity​
After the account is imported, you can get your identity by running the following command:
For local key:
${workspace}/bin/botcli \ validator-ownership \ sign-validator-ownership \ --bot-operator-address ${NEW_VALIDATOR_OPERATOR_ADDR_ON_BOT} \  --from ${ACCOUNT_NAME} \  --chain-id ${BOT_CHAIN_ID} \
For ledger key:
${workspace}/bin/botcli \ validator-ownership \ sign-validator-ownership \ --bot-operator-address ${NEW_VALIDATOR_OPERATOR_ADDR_ON_BOT} \ --from ${BOT_OPERATOR_NAME} \ --chain-id ${CHAIN_ID} \ --ledger
${workspace}/bin/botcli: The path to the botcli binary executable. For testnet, you should use tbotcli instead.
--to ${NEW_VALIDATOR_OPERATOR_ADDR_ON_BOT}: Specifies the BOT address to which the new validator operator address will be mapped.
--from ${ACCOUNT_NAME}: Specifies the account name from which the sign will be performed. The account should be the operator of the validator created on the Beacon Chain.
And you will get the output like this:
TX JSON: {"type":"auth/StdTx","value":{"msg":[{"type":"migrate/ValidatorOwnerShip","value":{"bot_operator_address":"RXN7r5XZlaljqzp8msZvx6Y6124="}}],"signatures":[{"pub_key":{"type":"tendermint/PubKeySecp256k1","value":"Ahr+LlBMLgiUFkP75kIuJW1YHrsTy39GeOdV+IaTREDN"},"signature":"AL5mj52s0+tcdoEb6c6PAmqBixuv3XEmrLW3Y1kvUeYgG3RqVvWU/dIVcfxiHHwLGXlcn0X1v00jFrpLIsxtqA==","account_number":"0","sequence":"0"}],"memo":"","source":"0","data":null}}
Sign Message: {"account_number":"0","chain_id":"Bot-GGG-Ganges","data":null,"memo":"","msgs":[{"bot_operator_address":"0x45737baf95d995a963ab3a7c9ac66fc7a63ad76e"}],"sequence":"0","source":"0"}
Sign Message Hash: 0x8f7179e7969e497b5f3c006535e55c2fa5bea5d118a8008eddce3fccd1675673
Signature: 0x00be668f9dacd3eb5c76811be9ce8f026a818b1bafdd7126acb5b763592f51e6201b746a56f594fdd21571fc621c7c0b19795c9f45f5bf4d2316ba4b22cc6da8
PubKey: 0x021afe2e504c2e08941643fbe6422e256d581ebb13cb7f4678e755f886934440cd
The Signature is your identity for associating with the old validator created on the BOT Chain.
Commissions​
Rate: The commission rate of the validator.
Max Rate: The maximum commission rate that the validator can set.
Max Change Rate: The maximum rate change the validator can set to every epoch (1 day).
Self-delegation​
Self Delegate Amount: The amount to delegate when creating the validator. The minimal number to input is 2001 - for the minimal self delegation amount is 2000 BOT and an extra 1 BOT for locking to a dead address.
3. Submitting the form​
Once you have filled out all the required information, click the Submit button to submit the transaction.
Note: Upon completing these steps, your node is not guaranteed to become an active validator. Selection is based on a ranking that reflects the total BOT stake, with only the top N nodes being chosen as active validators. The number N is determined by the “maxElectedValidators” parameter within the StakeHubContract (0x0000000000000000000000000000000000002002).

---

## Bridge

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Bridge/

📄️ BOT Chain 上的 Bridge 简介
BOT Chain Bridge 是官方的跨链基础设施，让用户在 BOT Chain 与其他受支持网络之间转移 USDT。它将 BOT Chain 与 Ethereum、BNB Smart Chain 和 Tron 连接起来，使 USDT 能够快速、安全地在 BOT Chain 生态中流入和流出。

---

## 合约地址

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Bridge/contract-addresses/

Bridge
合约地址
本页总览
Bridge 合约已部署在 BOT Chain 主网（Chain ID: 677）和测试网（Chain ID: 968）。对应的合约也部署在每一条受支持的外部网络上。
Bridge —— BOT Chain 主网​
合约地址说明
BridgeRouter0xef8DC669ECa13E612b67Ff09478352E85bD6CC53bridge-in / bridge-out 请求的入口
USDT（BOT Chain）0xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3CBOT Chain 上的 USDT 代币合约
Multicall30x47FA21f684bBAD707A53a0f9BE59F1422F46C265批量合约调用
Bridge —— 外部网络​
网络合约地址
Ethereum (1)BridgeGateway0x2945d3aF6f012e49f7421252b5fB57D1bb7E6Edd
Ethereum (1)USDT（ERC-20）0xdAC17F958D2ee523a2206206994597C13D831ec7
BNB Smart Chain (56)BridgeGateway0x3cd6fB6b0CDdD3610f0f4769AA7Bb686Cd4a4b55
BNB Smart Chain (56)USDT（BEP-20）0x55d398326f99059fF775485246999027B3197955
TronBridgeGatewayTGhXbQpjBgC6bDp5jAexzeQPHEXXsx5f35
TronUSDT（TRC-20）TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
Bridge —— BOT Chain 测试网​
BridgeRouter0x6239404Aa276ba68486E2Fa40E90CDd36ff8ec3A
USDT（BOT Chain 测试网）0x75edC9335175Fc0552D51D48439F229c10420fe3
Bridge —— 外部测试网络​
Ethereum Sepolia (11155111)BridgeGateway0xc83AE6F73e8918750b87DD001E36093A1AB7b272
Ethereum Sepolia (11155111)USDT（ERC-20）0x7B1e05a39adF207a759EAf89E867dBcC1C615130
BNB Smart Chain 测试网 (97)BridgeGateway0xbCAA929FdB16f5a7185C96A4Ed0CC4F25ab86E40
BNB Smart Chain 测试网 (97)USDT（BEP-20）0x5d012516D129Ab3aE7673FE32E5ABFCD9be4d086
Tron NileBridgeGatewayTMGhDtUkEhARjd1uYDVssubqH4ivnarfv7
Tron NileUSDT（TRC-20）TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf
所有测试网与主网上的 USDT 代币，其 resource_id 均相同：
0xac589789ed8c9d2c61f17b13369864b5f181e58eba230a6ee4ec4c3e7750cd1d
Bridge 合约函数示例​
入口场景目标链到账内容
deposit(...)普通跨链仅转入目标链代币，例如 USDT
depositWithBotGas(...)跨链至 BOT Chain 并希望附带原生 BOT 作为 Gas到账 USDT + BOT；BOT 的成本将从本次 USDT 充值的净额中扣除。

---

## 核心概念

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Bridge/core-concepts/

Bridge
核心概念
本页总览
锁定与释放（流动性模型）​
由于 USDT 在每一条受支持的网络上都以原生形式存在，Bridge 采用锁定与释放（Lock & Release）模型，由每条链上的 USDT 流动性金库提供支撑，而非铸造封装代币。
Bridge In（转入）： USDT 在源链的 TokenVault 中被锁定，同时从 BOT Chain 金库中释放等额 USDT 给接收方。
Bridge Out（转出）： USDT 在 BOT Chain 金库中被锁定，同时从目标链的金库中释放等额（扣除提现费用后）的 USDT。
验证者 / 中继者​
跨链转账由一组去中心化的验证者保障安全。当源链上检测到一笔充值时，验证者各自独立观察该事件并生成签名证明。一旦达到所需的签名阈值，中继者会将聚合后的证明提交到目标链，以释放 USDT。
验证者从不托管用户资金；他们只对所观察到的事件进行证明。
BridgeValidator 合约在释放 USDT 之前会强制校验签名阈值。
确认数与最终性​
为防范链重组，Bridge 会在验证者对一笔转账进行证明之前，等待源链上达到最低数量的区块确认。
BOT Chain：物理最终性（Physical Finality）—— 交易一经打包即为最终，因此确认几乎是即时的。
外部链（Ethereum、BSC、Tron）：Bridge 会等待各网络特定的确认数后再进行处理。
安全模型​
每笔转账都由唯一的 transferId 标识，且只能被认领一次（防重放）。
释放需要经过链上验证的、达到法定数量的验证者签名。
金库余额由锁定的 USDT 以 1:1 完全支撑。
可暂停：紧急情况下，治理方可暂停 BridgeRouter 以保护用户资金。

---

## 费用

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Bridge/fees/

Bridge
费用
BOT Chain Bridge 对 USDT 转账采用简单、固定的费用结构。
方向跨链费用说明
Bridge In（转入 BOT Chain）免费（0 USDT）转入 BOT Chain 的充值不收取任何跨链费用
Bridge Out（转出 BOT Chain）0.1%（最低 1 USDT）从转账金额中扣除 0.1% 的费用（最低 1 USDT）
Bridge In：接收方收到全额充值的 USDT（源链上的网络 Gas 仍需照常支付）。
Bridge Out：接收方收到的金额为「转账金额 − 提现费用（0.1%，最低 1 USDT）」。转账金额必须大于 10 USDT。

---

## BOT Chain 上的 Bridge 简介

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Bridge/introduction/

Bridge
BOT Chain 上的 Bridge 简介
本页总览
BOT Chain Bridge 是官方的跨链基础设施，让用户在 BOT Chain 与其他受支持网络之间转移 USDT。它将 BOT Chain 与 Ethereum、BNB Smart Chain 和 Tron 连接起来，使 USDT 能够快速、安全地在 BOT Chain 生态中流入和流出。
BOT Chain 是一条高性能、兼容 EVM 的 Layer 1 区块链，具备 0.75 秒出块时间、物理最终性（Physical Finality）以及极低的 Gas 费用，一旦转账被确认，跨链资金即可快速到账。
为什么使用 BOT Chain Bridge？​
免费充值 —— 将 USDT 跨链转入 BOT Chain（bridge in）不收取任何跨链手续费
简单、可预期的提现费用 —— 将 USDT 跨链转出 BOT Chain 收取 0.1%（最低 1 USDT）
快速结算 —— BOT Chain 侧具备 0.75 秒出块时间与物理最终性
安全设计 —— 验证者 / 多重签名验证，每笔转账均有链上证明
多链覆盖 —— 支持 Ethereum（ERC-20）、BNB Smart Chain（BEP-20）与 Tron（TRC-20）的 USDT
快速开始路径​
支持的链与资产
合约地址
核心概念
费用
准备好将 BOT Chain 连接到多链世界了吗？让我们开始吧！

---

## 支持的链与资产

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Bridge/supported-chains/

Bridge
支持的链与资产
BOT Chain Bridge 目前仅支持 USDT 的转移，在 BOT Chain 与以下网络之间进行。
网络Chain IDUSDT 标准
BOT Chain677USDT（BOT Chain）
Ethereum1ERC-20 USDT
BNB Smart Chain56BEP-20 USDT
TronTron 主网（非 EVM）
跨链桥场景使用：728126428TRC-20 USDT

---

## DEX

Source: https://dev-docs.botchain.ai/zh-Hans/docs/DEX/

📄️ BOT Chain 上的 DEX 简介
BOT Chain 是一条高性能、兼容 EVM 的 Layer 1 区块链，具备 0.75 秒出块时间、物理最终性（Physical Finality） 以及极低的 Gas 费用——是构建快速、高效的去中心化交易所（DEX）的理想平台。

---

## API 参考

Source: https://dev-docs.botchain.ai/zh-Hans/docs/DEX/api-reference/

DEX
API 参考
BOT Chain DEX 为开发者提供官方 API。
所有 DEX API 均记录在我们的 Apifox 工作区中。你可以查看详细的接口、请求/响应示例，并直接在浏览器中测试。
查看 API 文档：
测试网：https://s.apifox.cn/78c89a55-76be-4d27-9efe-35626bd465f2
主网：https://s.apifox.cn/139b78fd-a57f-470a-ac74-b7246d32f2e6

---

## BDEX V2

Source: https://dev-docs.botchain.ai/zh-Hans/docs/DEX/bdex-v2/

DEX
BDEX V2
本页总览
BDEX V2 是部署在 BOT Chain 上的恒定乘积 AMM（x × y = k），基于经过充分验证的 Uniswap V2 架构。它为代币创建者和开发者提供了简单可靠的 DEX 基础设施。
创建交易对​
BDEX V2 交易对通过 V2 Factory 合约创建。交易对由两个代币地址唯一标识，且每个代币对只能拥有一个 V2 交易对合约。
Factory 方法：
function createPair(address tokenA, address tokenB) external returns (address pair);
function getPair(address tokenA, address tokenB) external view returns (address pair);
基本规则：
tokenA 与 tokenB 必须是不同的代币。
两个代币地址都不能是零地址。
如果交易对已存在，createPair 会回滚（revert）。
创建后，开发者可通过 getPair(tokenA, tokenB) 读取交易对地址，或监听 PairCreated 事件。
示例流程：
const pair = await factory.getPair(tokenA, tokenB)
if (pair === ZERO_ADDRESS) {
const tx = await factory.createPair(tokenA, tokenB)
await tx.wait()
}
对于大多数前端集成，开发者无需先手动创建交易对。通过 router 添加初始流动性时，可在需要时自动创建交易对。
添加 / 移除流动性​
BDEX V2 流动性通过 V2 Router02 合约管理。流动性提供者将两种代币存入交易对并获得 V2 LP 代币。LP 代币是交易对合约的 ERC-20 代币，代表提供者在资金池中的份额。
常用方法：
function addLiquidity(
address tokenA,
address tokenB,
uint amountADesired,
uint amountBDesired,
uint amountAMin,
uint amountBMin,
address to,
uint deadline
) external returns (uint amountA, uint amountB, uint liquidity);
function removeLiquidity(
uint liquidity,
) external returns (uint amountA, uint amountB);
集成注意事项：
添加流动性前，用户必须授权（approve）V2 Router02 使用两种 ERC-20 代币。
对于已存在的资金池，应按当前储备比例添加流动性。
对于新资金池，首位流动性提供者通过选择存入比例来定义初始价格。
应设置 amountAMin 和 amountBMin 以保护用户免受滑点影响。
移除流动性会销毁 LP 代币，并按用户的资金池份额返还对应的代币对。
原生 BOT 流动性：
对于涉及原生 BOT 的资金池，请使用 ETH 风格的 router 方法，例如 addLiquidityETH / removeLiquidityETH。在内部，原生 BOT 会被封装为 WBOT。
代币兑换指南​
BDEX V2 兑换可直接通过 Router02 执行，但推荐前端应用使用官方 Routing API 来获取最优路由和可执行的 calldata。
推荐集成路径：
调用 Routing API GET /quote。
从响应中读取 methodParameters.to、methodParameters.calldata 和 methodParameters.value。
通过 eth_sendTransaction 提交这些字段。
Routing API 示例：
GET /quote?chainId=677
&tokenInAddress=0x...
&tokenOutAddress=0x...
&amount=1000000000000000000
&type=exactIn
&protocols=v2
&recipient=0x...
&slippageTolerance=0.5
Router02 直接调用方法：
function swapExactTokensForTokens(
uint amountIn,
uint amountOutMin,
address[] calldata path,
) external returns (uint[] memory amounts);
function swapTokensForExactTokens(
uint amountOut,
uint amountInMax,
兑换手续费：
BDEX V2 采用固定 0.30% 的兑换手续费。
手续费从输入代币数量中扣取。
资金池不会对输出代币单独收费。
手续费保留在资金池中，并通过资金池储备的增长分配给 LP。
转账征税代币（Fee-on-transfer）：
转账征税代币应仅使用 V2 路由。对于这类税费代币，V3 的流动性和兑换流程可能会回滚。Routing API 会自动检测受支持的转账征税场景，并在需要时限制路由。

---

## BDEX V3

Source: https://dev-docs.botchain.ai/zh-Hans/docs/DEX/bdex-v3/

DEX
BDEX V3
本页总览
BDEX V3 引入了集中流动性（Concentrated Liquidity），允许 LP 在自定义价格区间内配置资金，从而显著提升资金效率。它基于 Uniswap V3 架构，并针对 BOT Chain 0.75 秒出块时间和低 Gas 环境进行了适配。
集中流动性指南​
BDEX V3 采用集中流动性模型。与 V2 不同，流动性并非始终分布在整个价格区间内。流动性提供者可以选择一个自定义价格区间，在该区间内其资金处于活跃状态。
当市场价格位于所选区间内时，该头寸赚取兑换手续费。当市场价格移动到区间之外时，该头寸变为非活跃状态，不再赚取手续费，直到价格重新进入区间。
核心合约：
合约用途
V3 Factory创建并管理 V3 资金池
NonfungiblePositionManager以 NFT 形式创建并管理 LP 头寸
QuoterV2在链下模拟兑换输出
Universal Router跨受支持的协议执行兑换
支持的费率档位：
费率档位费率值Tick 间距典型适用场景
0.05%50010稳定币或高度相关的交易对
0.30%300060大多数标准交易对
1.00%10000200高波动或长尾资产
创建 V3 资金池：
function createPool(
address tokenA,
address tokenB,
uint24 fee
) external returns (address pool);
资金池创建后，必须先用初始价格进行初始化，然后才能添加流动性。
function initialize(uint160 sqrtPriceX96) external;
添加集中流动性：
开发者应使用 NonfungiblePositionManager.mint 来创建头寸。该头寸以 ERC-721 NFT 形式表示。
struct MintParams {
address token0;
address token1;
uint24 fee;
int24 tickLower;
int24 tickUpper;
uint256 amount0Desired;
uint256 amount1Desired;
uint256 amount0Min;
uint256 amount1Min;
address recipient;
uint256 deadline;
}
function mint(MintParams calldata params)
external
payable
returns (
uint256 tokenId,
uint128 liquidity,
uint256 amount0,
uint256 amount1
);
集成注意事项：
在铸造头寸前，用户必须授权 NonfungiblePositionManager 使用两种代币。
tickLower 和 tickUpper 必须与资金池的 tick 间距匹配。
应设置 amount0Min 和 amount1Min 以保护用户免受滑点影响。
价格区间越窄，资金效率越高，但头寸变为非活跃状态的概率也越高。
头寸管理​
BDEX V3 的 LP 头寸由 NonfungiblePositionManager 管理。每个头寸都是一个 NFT，拥有各自的代币对、费率档位、价格区间、流动性数量和累积手续费。
常用头寸操作：
function increaseLiquidity(IncreaseLiquidityParams calldata params)
returns (uint128 liquidity, uint256 amount0, uint256 amount1);
function decreaseLiquidity(DecreaseLiquidityParams calldata params)
returns (uint256 amount0, uint256 amount1);
function collect(CollectParams calldata params)
function burn(uint256 tokenId) external payable;
头寸生命周期：
Mint（铸造） —— 创建一个新的集中流动性头寸 NFT。
Increase Liquidity（增加流动性） —— 向现有头寸添加更多流动性。
Decrease Liquidity（减少流动性） —— 移除头寸中的部分或全部流动性。
Collect Fees（领取手续费） —— 领取累积的兑换手续费。
Burn（销毁） —— 在移除所有流动性和手续费后销毁该 NFT。
手续费领取说明：
V3 的手续费不会自动转入 LP 的钱包。
LP 必须调用 collect 来领取累积的手续费。
只有当头寸处于活跃状态（即当前资金池价格位于所选 tick 区间内）时，手续费才会累积。
移除流动性不会自动领取全部手续费；应用应在需要时调用 collect。

---

## 合约地址

Source: https://dev-docs.botchain.ai/zh-Hans/docs/DEX/contract-addresses/

DEX
合约地址
本页总览
所有 BDEX 智能合约均已部署在 BOT Chain 主网（Chain ID: 677）和测试网（Chain ID: 968）。
主网​
共享基础设施 — 主网​
合约地址说明
WBOT0xD5452816194a3784dBa983426cCe7c122F4abd30封装的 BOT（原生 BOT 的 ERC-20 表示）
Multicall30x47FA21f684bBAD707A53a0f9BE59F1422F46C265批量合约调用
Permit20x8366170f09a04f715a13549D616a06aED16Db7c3基于签名的代币授权
Universal Router0xaE6ae8630f7A888dEc0B9195C85F7515d5887655V2 与 V3 的统一兑换入口
BDEX V2 — 主网​
V2 Factory0x117115f3B72C8d1989178089A67D0C26f8EE0AA3创建并管理所有 V2 交易对
V2 Router020x1414eD29FdFD322c3c0a830330ed982E2D629e76路由兑换并管理流动性操作
pairInitCodeHash0xa075aa7c03cb5559a4c6202459721232c21e18148152410f6beec063e8499e6cV2 交易对的 CREATE2 init code hash
BDEX V3 — 主网​
V3 Factory0x1C51c173323ec11BB4e3C4fD2314c225Dc4b5419创建并管理所有 V3 资金池
SwapRouter0x07032d47A1b9f8460cBeE9dC17c1d3E438693929执行 V3 兑换（单跳与多跳）
QuoterV20x034A705b36067cff99ABf5C662Be881cBd8d0176链下报价模拟
NonfungiblePositionManager0xDAc3FcFF004d8a8675b94E44941A1a2e3b240090以 ERC-721 NFT 形式管理 LP 头寸
常用代币（主网）​
代币符号精度地址
Wrapped BOTWBOT180xD5452816194a3784dBa983426cCe7c122F4abd30
Tether USDUSDT60xaBabc7Ddc03e501d190C676BF3d92ef0e6e87a3C
测试网​
共享基础设施 — 测试网​
WBOT0xD5452816194a3784dBa983426cCe7c122F4abd30封装的 BOT（原生 BOT 的 ERC-20 表示）
Multicall30x47FA21f684bBAD707A53a0f9BE59F1422F46C265批量合约调用
Permit20xaE85b2bc7578F8Ca9217900a2D548151F96447de基于签名的代币授权
Universal Router0x73Be0A1d8011B335A7aBeF6c45544E8ca4448AB5V2 与 V3 的统一兑换入口
BDEX V2 — 测试网​
V2 Factory0x65b8e98ceA190d8c28B3e4716402027f634d15a3创建并管理所有 V2 交易对
V2 Router020xD6425a02f0845B8D99e349C34D2E7A576E177345路由兑换并管理流动性操作
pairInitCodeHash0x9d2cc5d1f5560e2a4119c794e0fa625b8c50af562e72436c234ec1addb77de47V2 交易对的 CREATE2 init code hash
BDEX V3 — 测试网​
V3 Factory0x1C51c173323ec11BB4e3C4fD2314c225Dc4b5419创建并管理所有 V3 资金池
SwapRouter0x07032d47A1b9f8460cBeE9dC17c1d3E438693929执行 V3 兑换（单跳与多跳）
QuoterV20x034A705b36067cff99ABf5C662Be881cBd8d0176链下报价模拟
NonfungiblePositionManager0xDAc3FcFF004d8a8675b94E44941A1a2e3b240090以 ERC-721 NFT 形式管理 LP 头寸
常用代币（测试网）​
Wrapped BOTWBOT180xD5452816194a3784dBa983426cCe7c122F4abd30
Tether USDUSDT60x75edC9335175Fc0552D51D48439F229c10420fe3

---

## 核心概念

Source: https://dev-docs.botchain.ai/zh-Hans/docs/DEX/core-concepts/

DEX
核心概念
本页总览
AMM（自动做市商）​
BDEX 采用 AMM 模型，无需订单簿即可实现无许可的代币交易。流动性提供者将代币对存入资金池，交易者通过确定性定价算法与这些资金池进行兑换。
支持两种 AMM 模型：
模型协议公式适用场景
恒定乘积BDEX V2x × y = k简单、通用、Gas 成本更低
集中流动性BDEX V3在价格区间内提供流动性资金效率高、适合进阶 LP 策略
流动性池​
流动性池持有两种代币的储备。任何人都可以按正确比例存入两种代币来提供流动性，并获得代表其份额的 LP 代币（V2）或 NFT 头寸（V3）。
V2 资金池：每个交易对只有一个资金池，固定收取 0.30% 手续费
V3 资金池：每个交易对可在不同费率档位（0.05%、0.30%、1.00%）拥有多个资金池
费用结构​
项目V2V3
兑换手续费0.30%（固定）0.05% / 0.30% / 1.00%
LP 手续费分成100% 归 LP100% 归 LP（处于活跃区间时）
滑点与价格影响​
滑点是兑换预期输出与实际输出之间的差额。价格影响随交易规模相对于资金池流动性的增大而上升。
务必为 V2 设置 amountOutMin，或为 V3 及 Universal Router 流程设置 amountOutMinimum，以防范过度滑点
推荐滑点容忍度：主流交易对 0.1% - 1.0%，低流动性代币最高可至 5%
在提交交易前，使用 Routing API、V3 QuoterV2 或 V2 getAmountsOut 预览兑换结果
Tick 与 Tick 间距（仅 V3）​
在 V3 中，流动性被放置在由 tick 定义的价格区间内。可用的 tick 间距取决于所选的费率档位。详见 BDEX V3 章节。

---

## BOT Chain 上的 DEX 简介

Source: https://dev-docs.botchain.ai/zh-Hans/docs/DEX/introduction/

DEX
BOT Chain 上的 DEX 简介
本页总览
BOT Chain 是一条高性能、兼容 EVM 的 Layer 1 区块链，具备 0.75 秒出块时间、物理最终性（Physical Finality） 以及极低的 Gas 费用——是构建快速、高效的去中心化交易所（DEX）的理想平台。
为什么在 BOT Chain 上构建 DEX？​
超低 Gas 费用 —— 大幅降低兑换与提供流动性的成本
快速最终性 —— 降低流动性提供者面临的无常损失风险
抗 MEV —— 营造更公平的交易环境
完整 EVM 兼容 —— 轻松 Fork Uniswap V2、PancakeSwap 或 Uniswap V3
快速开始路径​
合约地址
代币兑换指南
准备好在 BOT Chain 上构建下一个领先的 DEX 了吗？让我们开始吧！

---

## 开发者

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Developers/

📄️ 快速指南
如果您是一名希望在 BOT Chain 上构建应用程序的开发人员，本文档提供了您所需的所有基本信息。

---

## Blob API

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Developers/blob-api/

开发者
Blob API
本页总览
eth_getBlobSidecarByTxHash​
参数​
哈希字符串（必需）
HEX String - 交易的哈希值
full_blob_flag 布尔值（可选）
默认值为 true。如果为 true，则返回完整的 blob 信息，如果为 false，则仅返回 blob 的前 32 个字节。
curl -X POST "http://localhost:8545/" -H "Content-Type: application/json"  --data '{"jsonrpc":"2.0","method":"eth_getBlobSidecarByTxHash","params":["0x377d3615d2e76f4dcc0c9a1674d2f5487cba7644192e7a4a5af9fe5f08b60a63"],"id":1}'
curl -X POST "http://localhost:8545/" -H "Content-Type: application/json"  --data '{"jsonrpc":"2.0","method":"eth_getBlobSidecarByTxHash","params":["0x377d3615d2e76f4dcc0c9a1674d2f5487cba7644192e7a4a5af9fe5f08b60a63", false],"id":1}'
eth_getBlobSidecars​
区块编号 数量|标签
HEX 字符串 - 整数块号
HEX 字符串 - 块的哈希值
字符串“earliest”表示最早/创世块
String "latest" - 最新开采的区块
字符串“safe” - 用于最新的合理头块
String "finalized" - 用于最新的最终确定块
默认值为 true。如果为 true，则返回完整的 blob 信息，如果为 false，则仅返回 blob 的前 32 个字节。
curl -X POST "http://localhost:8545/" -H "Content-Type: application/json"  --data '{"jsonrpc":"2.0","method":"eth_getBlobSidecars","params":["latest"],"id":1}'
curl -X POST "http://localhost:8545/" -H "Content-Type: application/json"  --data '{"jsonrpc":"2.0","method":"eth_getBlobSidecars","params":["0xc5043f", false],"id":1}'

---

## BOT Chain 节点配置：最佳实践

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Developers/bot-chain-node-configuration-best-practices/

开发者
BOT Chain 节点配置：最佳实践
本页总览
硬件规格​
为了确保最佳的性能和可靠性，根据您在BOT Chain上的事务处理和状态查询的具体要求选择合适的节点类型至关重要。
归档&全节点部署指南​
克隆存储库并进入目录
bash
git clone https://github.com/bl-BOHR/node-deploy.git && cd node-deploy
授予执行权限（仅在Linux上第一次需要）
chmod +x BOHR_full_node.sh BOHR_archive_node.sh bin/geth*
初始化并启动节点
全节点：
./BOHR_full_node.sh reset
存档节点：
./BOHR_archive_node.sh reset
查看日志
节点日志位于：.local/fullnode/node/BOHR-node.log
对于需要以轻量级模式访问最新世界状态的用户来说，快速节点是理想的选择。它对系统 CPU 和磁盘空间的要求较少。
推荐配置​
为了全面访问 BOT 主网的整个历史世界状态，请考虑部署存档节点。详细说明可在 BOT Chain GitHub 存储库中找到。（此处需要指向我们存储库的外部链接。）
处理器：至少 2 核 CPU。
内存：至少 4 GB RAM。
存储：固态硬盘（SSD），最小容量为128GB。
网络：稳定高速的互联网连接，最低 1 MBps。
存档节点​
为了获取最新的世界状态并验证状态的有效性或生成数据证明，标准的全节点是合适的。
处理器：至少 4 核 CPU。
内存：至少 8 GB RAM。
存储：SSD，最小容量为 1TB（建议使用 NVME SSD 以获得最佳性能）。
网络：稳定高速的互联网连接，最低 2 MBps。
全节点​
验证者最有价值的资产是两个密钥：一个用于签署交易，另一个用于签署区块
存储：固态硬盘（SSD），最小容量为 1TB。
对等配置​
主网​
无需指定静态节点，主网只需要Bootnodes，这些节点已在代码中配置。另外，请确保使用最新版本的 config.toml 文件。
测试网​
测试网仍然需要手动配置 StaticNodes，因此 StaticNodes 列表包含在最新版本的 config.toml 中。
测试网上没有对等点的故障排除​
检查配置问题，例如错误的链 ID、错误的配置文件/目录。
确保根据最新版本更新 config.toml 文件
不要在测试网上使用引导节点，这不是必需的。
删除 geth/nodes 和 geth/nodekey 文件/目录可能会有所帮助
重新下载快照并重试。
用硬件钱包存储您的BOT​
请不要将您的 RPC 端点公开到公共网络。
保护您的完整节点 RPC 免受黑客攻击​
为了保护您的BOT，请勿与任何人分享您的 24 个单词。唯一需要了解它们的人就是你。简而言之，HSM 是经济实惠、高性能且便携式的硬件，有助于安全地生成、存储和管理您的私钥。当 HSM 配置正确时，恶意软件攻击和远程提取私钥会变得更加困难。
账户私钥​
为了保护您的BOT，您应该只直接从官方来源下载软件，并确保您始终使用最新、最安全的版本
软件漏洞​
保持 geth 始终运行很重要。有多种方法可以实现这一点，我们推荐的最简单的解决方案是将 geth 注册为 systemd 服务，以便它在系统重新启动和其他事件时自动启动。
将服务器作为守护进程运行​
长时间运行（同步）并突然终止后，只有归档节点在重新启动时才有望快速重新同步。
设置备份节点​
以存档模式运行验证器节点
优雅地关闭节点
使用工具进行主动监控
运行备份节点的步骤​
安装最新版本的geth
使用快速同步模式同步到最新高度。您可以下载最新的快照，也可以在节点完全同步后开始快速同步
优雅地关闭你的节点kill -HUP $(pgrep geth)
重新启动您的节点。
Why Node will be Offline for a While After Restart? or What will Happen If the Client is Force Killed?​
重现步骤：
原因
运行节点同步一段时间。
突然终止节点（kill -9 或系统崩溃）。
重启节点，观察从1小时前的区块高度到哪里重新同步。
如果 Geth 崩溃（或未正常关闭），则内存中保存的最近状态将丢失并需要重新生成。需要Geth很长时间才能恢复状态。
根本原因是 geth 会定期刷新状态树。该周期在 config.toml 中定义为 trieTimeout。
您可以通过向 geth 控制台发送命令来停止挖掘新块
如何将备份节点升级为验证节点？​
使用 geth Attach ipc:path/to/geth.ipc 连接到您的验证器节点
然后，让备份节点恢复验证，
miner.stop()
鼓励每个候选验证者独立运行其操作，因为不同的设置可以提高网络的弹性。由于验证者投入大量资金，因此保护他们免受不同的 DoS 和 DDoS 攻击非常重要。在本节中，我们将讨论 BOT Chain 为其验证者采用的安全机制。
miner.start()
确保验证者的安全​
验证者负责确保网络能够承受拒绝服务攻击。减轻这些风险的一种推荐方法是验证者在所谓的哨兵节点架构中仔细构建其网络拓扑。 Sentry 节点可以快速启动或更改其 IP 地址。由于与哨兵节点的链接位于私有 IP 空间中，因此基于互联网的攻击无法直接干扰它们。这将确保验证者阻止提案，并且投票始终能够到达网络的其余部分。
哨兵节点（DDOS防护）​
要设置哨兵节点架构，您可以按照以下说明操作：
请不要将您的验证器全节点 RPC 端点公开到公共网络。
构建私有网络并在验证器节点与其哨兵之间建立可信的私有连接
安装你的全节点
在哨兵节点的控制台上，运行 admin.nodeInfo.enode 您应该得到与此类似的内容。
将哨兵设置为验证节点的对等点
！！！注意：[::] 将被解析为 localhost (127.0.0.1)。如果您的节点位于本地网络上，请检查每个单独的主机并使用 ifconfig 查找您的 IP 如果您的对等点不在本地网络上，您需要知道您的外部 IP 地址（使用服务）来构造 enode URL。复制该值并在第一个运行的节点的控制台中，
enode://f2da64f49c30a0038bba3391f40805d531510c473ec2bcc7c201631ba003c6f16fa09e03308e48f87d21c0fed1e4e0bc53428047f6dcf34da344d3f5bb69373b@[::]:30306?discport=0
更新验证节点的config.toml文件
如果成功则返回 true，但这并不意味着节点添加成功。
# make node invisible
NoDiscovery = true
# connect only to sentry
StaticNodes = ["enode://f2da64f49c30a0038bba3391f40805d531510c473ec2bcc7c201631ba003c6f16fa09e03308e48f87d21c0fed1e4e0bc53428047f6dcf34da344d3f5bb69373b@[10.1.1.1]:30306"]
要确认运行 admin.peers，您应该会看到刚刚添加的节点的详细信息。
这样，您的验证器节点将尝试仅与您提供的哨兵节点进行对等。
确认连接
geth 使用多个 TCP 端口用于不同的目的。
防火墙配置​
geth 使用侦听器 (TCP) 端口和发现 (UDP) 端口，默认情况下均位于 31000。
如果您需要运行JSON-RPC，您还需要TCP端口8545。请注意，JSON-RPC端口不应该向外界开放，因为从那里您可以进行管理操作。
If you need to run JSON-RPC, you'll also need TCP port 8545. Note that JSON-RPC port should not be opened to the outside world, because from there you can do admin operations.

---

## 领取测试 tBOT 代币

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Developers/claim-test-tbot-tokens/

开发者
领取测试 tBOT 代币
本页总览
从在线水龙头领取 tBOT​
按以下步骤在 BOT Chain 测试网领取测试 tBOT：
将钱包切换到 BOT Chain 测试网（Chain ID：968）。
打开 https://faucet.botchain.ai/basic。
输入钱包地址并完成验证。
领取后，点击返回的 tx hash，在 https://scan.bohr.life/ 查询交易。
限制说明： 每个地址每 24 小时最多可领取 10 tBOT。tBOT 无真实价值。

---

## EOA Paymaster

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Developers/eoa-paymaster/

开发者
EOA Paymaster
本页总览
概述​
EOA 基于 Paymaster​
本文档介绍了专门为外部拥有帐户（EOA）钱包设计的 Paymaster 解决方案，与EIP-4337中定义的 Paymaster 不同。只需很少的修改，钱包就可以集成该解决方案来支持 Gas 费赞助，从而显着增强用户体验。
什么是基于 EOA 的 Paymaster​
EIP-4337（通过入口点合约规范进行账户抽象）中的 Paymaster 是一个关键组件，旨在增强 Ethereum 交易的灵活性和用户体验。它允许第三方支付用户的交易费用，用户无需持有 ETH 来支付 Gas 费。
虽然EIP-4337为智能合约钱包引入了 Paymaster 的革命性概念，但Ethereum生态系统的很大一部分仍然依赖于EOAs。认识到这一点，这就提出了专为 EOA 钱包设计的突破性 Paymaster 解决方案。这项创新为更广泛的 BOT Chain 用户群带来了交易赞助和增强的用户体验的好处，而无需转向智能合约钱包。 EOA Paymaster 解决方案旨在使赞助交易的访问民主化，使区块链交互对于数百万现有的 EOA 钱包用户来说更加用户友好且更具成本效益。
它是如何工作的​
交易处理发生重大转变：
验证者角色：验证者不再验证区块内的单个交易 Gas 价格。
交易捆绑：私有交易被分组并提交给构建者。
优先级：构建者根据每个捆绑包的总 Gas 价格确定优先级。
捆绑包内灵活性：在单个捆绑包内，gas 价格可能会有所不同，从而允许零费用和更高费用的交易共存。
这种灵活性实现了创新功能，例如赞助 Gas 费和无 Gas 交易。
定义​
Bundle：以原子方式执行的有序交易数组，确保捆绑中的所有交易一起处理或根本不处理。
Builder：MEV供应链中负责构建区块的新利益相关者。构建者将交易捆绑、来自公共交易池的单个交易以及私人交易订单流打包到提议的区块中。
提案者：验证者从多个构建者的提案中选择最有利可图的区块以包含在区块链中。
Paymaster：支持交易赞助的基础设施组件，允许自己或第三方支付 Gas 费。
赞助商政策：由 Gas 赞助商定义的一组规则，用于确定哪些交易有资格获得赞助。这可能包括白名单交易发送者或特定交易类型等标准。
总体工作流程​
Gas 赞助流程涉及几个关键组成部分和步骤：
用户启动：
用户使用任何兼容的钱包准备交易。
钱包将潜在赞助交易的 Gas 价格设置为零。
Paymaster 提交：
钱包将零 Gas 价格交易提交给 Paymaster。
赞助商政策验证：
Paymaster 根据现有赞助商政策检查交易。
策略可能包括发件人/收件人地址、令牌类型或交易限制等标准。
赞助处理：
如果交易符合赞助资格： Paymaster 以更高的 Gas 价格创建赞助商交易。 b.原始用户交易和赞助商交易合并为一个捆绑包。
如果不符合条件，交易将被拒绝或返回给用户进行正常处理。
捆绑包创建和提交：
此捆绑包已提交给多个 MEV 构建者。
建造者选择和区块提案：
MEV 构建者将捆绑包合并到他们的区块提案中。
区块链包容性：
提案者（验证者）从构建者的提案中选择最有利可图的区块。
包含用户原始交易和赞助商交易的选定区块将被添加到区块链中。
这确保了两个事务的原子执行。
交易后处理：
Paymaster 经理更新赞助商的帐户，扣除适当的赞助 Gas 金额。
该解决方案可实现无缝 Gas 赞助，无需对现有钱包基础设施进行重大更改。它提供了一个灵活的系统，可以适应各种赞助模式，同时保持区块链网络的安全性和完整性。
Paymaster 基础设施​
准备好在您的应用程序或钱包中启用无 Gas 体验了吗？以下是 BOT Chain 上提供的有关 Paymaster 基础设施的一些有用信息：
Nodereal。由 Nodereal 提供支持的 MegaFuel 是基于 BOT Chain Paymaster 的 EOA 钱包的 Paymaster 实现。只需很少的修改，钱包就可以集成MegaFuel来支持 Gas 费赞助，从而显着增强用户体验。同时，赞助商可以在MegaFuel上定制他们的赞助，允许赞助用户发送无 Gas 交易。
Paymaster API 规格​
为了促进广泛采用并确保不同钱包实现之间的互操作性，为 Paymaster 建立一套标准化的接口规范至关重要。这种标准化将使钱包开发人员能够高效、一致地集成 Gas 赞助功能，无论他们选择使用哪种特定的 Paymaster 服务。
API 规格​
Paymaster需要实现一个名为pm_isSponsorable的JSON-RPCAPI，以便它可以将赞助商和保单信息返回给钱包。 Paymaster 还需要实施 eth_sendRawTransaction JSON-RPC API。详细的API规格定义如下：
pm_isSponsorable​
请求参数
jsonrpc：JSON-RPC协议版本（“2.0”）。
id：请求的唯一标识符（本例中为 1）。
method：要调用的方法名称（“pm_isSponsorable”）。
params：包含单个对象的数组，该对象具有以下字段：
to：交易的接收地址。
from：交易的发送者地址。
value：交易的十六进制值。
data：交易的附加数据（十六进制）。
gas：交易的gas limit（十六进制）。
示例：
{
"jsonrpc": "2.0",
"id": 1,
"method": "pm_isSponsorable",
"params": [
"to": "0x...", // an address
"from": "0x...", // an address"value": "0xa1",
"data": "0x",
"value": "0x1b4",
"gas" : "0x101b4"
}
]
响应字段
result：包含赞助政策详细信息的对象：
（必需）Sponsorable：一个布尔值，指示交易是否受到赞助（true 或 false）。
（必填）SponsorPolicy：。赞助商政策的名称。
"result": {
"Sponsorable": true,
"SponsorPolicy": "a sample policy name"
eth_sendrawtransaction​
由 Paymaster 实施的 eth_sendrawtransaction API 应遵循此 Ethereum API 规范。客户端可以通过eth_sendrawtransactionAPI创建新的消息调用交易或为签名交易创建合约。
params 应包含签名的交易数据。
"method": "eth_sendRawTransaction",
"0x02f86a6102850df8475800850df84758000a94cd9c02358c223a3e788c0b9d94b98d434c7aa0f18080c080a0bcb0e8ffa344e4b855c6e13ee9e4e5d22cff6ad8bd1145a93b93c5d332100c2ca03765236eba5fbb357e35014fd19ba4b3c6b87f3793bd14dddf7913fc8dcc88bf"
DATA，32 字节 - 交易哈希。
"result": "0xe670ec64341771606e55d6b4ca35a1a6b75ee3d5145a99d05921026d1527331"
钱包集成​
本指南概述了钱包开发人员集成 Paymaster 服务、为其用户提供 Gas 费赞助的步骤。通过遵循这些标准，钱包可以跨多个 Paymaster 提供商提供无缝、无 Gas 的交易。
互动工作流程​
集成涉及修改交易创建和发送流程以与 Paymaster 服务交互。
主要步骤是：
交易准备：
当用户发起交易时，首先调用gm_sponsorable检查是否符合赞助资格。
如果可赞助，请将交易的 Gas 价格设置为零。
用户通知：
通知用户该交易将是无 Gas 的，并由API返回的“政策名称”赞助。
交易签名：
让用户签署零 Gas 价格交易。
提交给 Paymaster：
使用 eth_sendRawTransaction 将签名的交易发送给 Paymaster。
响应处理：
处理 Paymaster 的回复：
如果成功，通知用户交易已提交。
如果失败，请考虑回退到正常事务处理或通知用户失败。
交易监控：
照常监控交易状态。
最佳实践​
在修改 Gas 价格之前，请务必检查赞助情况。
提供有关赞助状态的清晰用户反馈。
对赞助失败的情况实施适当的错误处理。
考虑非赞助交易的后备机制。
尝试无 Gas 交易​
在主流钱包中体验Paymaster​
多个主流加密货币钱包已经实现了 Paymaster 集成。本教程将指导您体验将无 Gas 交易发送到 Paymaster 集成钱包的体验。
Paymaster 集成钱包​
具有集成 Paymaster 功能的钱包为用户提供无缝体验。这些钱包会自动检测交易是否有资格获得赞助。当交易合格时，钱包会将 Gas 价格设置为零，无需任何用户干预。
为了说明这一点，我们将通过在 BOT Chain 上转移稳定币来完成整个过程。

---

## JSON-RPC-端点

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Developers/json-rpc-endpoint/

开发者
JSON-RPC-端点
本页总览
JSON-RPC 端点是指程序可以传输其 RPC 请求以访问服务器数据的网络位置。将去中心化应用程序连接到 RPC 端点后，您可以访问不同操作的功能，从而实现区块链数据的实时使用。 BOT Chain 提供了多个 RPC 端点用于连接到其主网和测试网。在本节中，我们列出了可用于连接到 BOT Chain 的 JSON-RPC 端点。
一键添加BOT网络​
访问 ChainList 并连接到您的钱包。它将添加活动的 RPC 端点。
RPC BOT Chain 的端点​
eth_getLogs 在以下主网端点上被禁用。请使用此处的第 3(rd) 方端点。如果您需要频繁拉取日志，我们建议您使用 WebSockets 在新日志可用时将其推送给您。
BOT 主网（ChainID 677）​
https://rpc.botchain.ai
BOT Chain 测试网（ChainID 968）​
https://rpc.bohr.life
启动 HTTP JSON-RPC​
您可以使用 –http 标志启动 HTTP JSON-RPC
## mainnet
## testnet
JSON-RPC API 列表​
BOT Chain 与 EVM 兼容，并努力与 Go-Ethereum API 尽可能兼容。然而，BOT Chain也具有独特的功能，例如更快的最终性和执行层上的blob数据存储，这需要它们自己专门的API。
Geth(Go-Ethereum) API​
BOT Chain 几乎与 Geth API 完全兼容。明确列出任何例外或不兼容性。如果您正在寻找特定 API 的详细用法，您很可能会在以下链接中找到答案：
Geth JSON-RPC API 文档。
最终确定​
Ethereum 的 PoS 共识协议，称为“Gasper”，是建立在 LMD-GHOST（分叉选择规则）和 Casper FFG（最终性小工具）之上的。类似地，BOT Chain 的共识协议称为“Parlia”，是在 FFG 的基于难度的分叉选择机制之上构建的，如 BEP-126 中所述。为了进一步增强 BOT Chain 的吞吐量，验证器可以生成多个连续的块，如 BEP-341 中所述。这些差异导致 BOT Chain 与 Ethereum 相比具有独特的最终确定过程。
Blob​
BOT Chain 实现了 EIP-4844，它支持 Shard Blob 事务。有关更多详细信息，请参阅 Blob API 文档。
其他BOT ChainAPI​
BOT Chain 实现了一些其他的 API

---

## 节点类型

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Developers/node-types/

开发者
节点类型
本页总览
运行BOT Chain​
存档节点​
参考https://github.com/bl-BOHR/node-deploy
快速节点​
节点维护​
1. 二进制​
建议所有客户端升级到最新版本。最新版本应该更稳定并且具有更好的性能。
2. 存储​
2.1 修剪状态​
根据测试，当存储大小达到较高容量时（之前是1.5TB，这是一个实验值，最新的数字需要更新），全节点的性能会下降。我们建议全节点通过修剪存储来始终保持轻存储。
2.2 如何修剪​
停止 BOT Chain 节点。
运行nohup geth snapshot prune-state --datadir {the data dir of your BOT node} &。需要3-5小时才能完成。
完成后启动节点。
维护者应该始终有一些备份节点，以防其中一个节点被修剪。硬件也很重要，确保 SSD 满足：500 GB 可用磁盘空间、固态硬盘 (SSD)、gp3、8k IOPS、500 MB/S 吞吐量、读取延迟 <1ms（如果节点以快照同步启动，则需要 NVMe SSD）。
2.3 实时修剪古代数据​
古代数据是已经被认为不可变的块数据。这是由当前设置为 90000 的阈值决定的。这意味着超过 90000 的块被视为古老数据。我们向不关心古代数据的用户推荐 --prunceancient 标志。这也建议想要节省磁盘空间的用户，因为这只会保留最新 90000 个块的数据。请注意，一旦打开此标志，旧数据将不会再次恢复，并且如果启动命令中没有此标志，您将无法返回运行节点。
2.4 如何使用标志​
./geth --tries-verify-mode none --config /server/config.toml --datadir /server/node --cache 8000 --rpc.allow-unprotected-txs --history.transactions 0 --pruneancient=true --syncmode=full
2.5 修剪块工具​
v1.1.8 中引入的新离线功能，用于删除不需要的古老区块数据。它将丢弃古代数据库中的块、收据和标头以节省空间。
如何修剪​
运行
./geth snapshot prune-block --datadir /server/node --datadir.ancient ./chaindata/ancient --block-amount-reserved 1024
block-amount-reserved 是修剪后要保留的旧数据块的数量。
3. 光存储​
当节点崩溃或被强制杀死时，节点将从几分钟或几小时前的块同步。这是因为内存中的状态并没有实时持久化到数据库中，节点启动后需要从上一个检查点重播块。重播时间取决于config.toml中的配置TrieTimeout。如果您可以容忍较长的重放时间，我们建议您提高它，以便节点可以保持轻存储。

---

## 快速指南

Source: https://dev-docs.botchain.ai/zh-Hans/docs/Developers/quick-guide/

开发者
快速指南
本页总览
如果您是一名希望在 BOT Chain 上构建应用程序的开发人员，本文档提供了您所需的所有基本信息。
开始使用​
BOT Chain 是一个高性能的区块链网络。
由于BOT Chain兼容EVM，您现有的Ethereum智能合约技能将无缝转移到BOT Chain。
正在连接​
以下是一些可帮助您连接到 BOT 网络的资源：
钱包配置
测试网
Chain ID：968
RPC：https://rpc.bohr.life
原生代币：BOT
总供应量：1.5亿
探索者：https://scan.bohr.life/
主网
Chain ID：677
RPC：https://rpc.botchain.ai
浏览器：https://scan.botchain.ai
获取代币​
BOT是BOT Chain的原生实用代币，用于支付交易费用。对于测试网，您可以通过 BOT Chain Faucet 获取测试代币。
BOT Chain Testnet Faucet
对于主网，BOT 代币目前只能通过官方 DEX 获取，您可以使用支持的资产兑换 BOT。
B DEX
JSON-RPC API​
与 BOT Chain 交互需要向特定的 JSON-RPC API 方法发送请求。 BOT Chain的API与Geth兼容。
开发者工具​
探索者
BOTScan（测试网）
BOTScan（主网）
SDK。如果您仅将 SDK 用于 Ethereum 兼容功能，则所有 Ethereum SDK 应与 BOT Chain 配合使用。
ethers.js
web3.js
工具
Remix
Hardhat
Foundry
索引
TheGraph
Covalent
其他
钱包
BO Wallet
Metamask

---

## BOT Chain 开发者文档

Source: https://dev-docs.botchain.ai/zh-Hans/docs/intro/

BOT Chain 开发者文档
本页总览
BOT Chain 是一条兼容 EVM 的 Layer 1 公链，面向 DePIN 与 AI 应用。本文档涵盖网络配置、RPC、测试代币、合约部署与验证，以及生态协议。
主要特点和优势​
完全 Ethereum 虚拟机 (EVM) 兼容性
BOT Chain 100% EVM 兼容，允许开发者以几乎零代码更改的方式迁移基于 Ethereum 的 DApps 和 DeFi 项目。 MetaMask、Trust Wallet、Truffle 和 Remix 等流行工具开箱即用。
超低费用和闪电般快速的确认
平均交易费用约为 0.06 美元（截至 2025 年初），远低于大多数 EVM 链在拥堵期间的表现，区块时间约为 0.75 秒，BOT Chain 提供近乎即时、经济高效的交易和明显更流畅的用户体验。
BOT 代币的作用​
BOT 是 BOT Chain 生态系统的原生实用程序和治理代币：
支付交易费用——所有链上活动的经济燃料
质押 – 将 BOT 委托给验证者，赚取奖励并帮助保护网络
治理 – BOT 持有者对协议升级和未来方向进行投票
未来展望​
BOT Chain 正在成为区块链领域的主导力量，特别是在 DeFi 和去中心化应用中。通过结合极快的速度、最低的成本和深度的互操作性，它可以直接解决当今最关键的可扩展性和可用性挑战。凭借持续创新和快速发展的社区，BOT Chain 已做好准备推动下一波主流区块链的采用。

---

## 简介

Source: https://dev-docs.botchain.ai/zh-Hans/docs/introduction/

简介
BOT Chain 是一种创新的区块链解决方案，可在整个生态系统中提供完全的可编程性和本机互操作性。它基于权益证明（PoSA）共识机制运行，可缩短出块时间并显着降低交易费用。具有最高抵押权益的验证者被选举来生成区块。全面的惩罚机制——包括双签检测、恶意投票检测和其他惩罚逻辑——确保网络的安全性、稳定性和最终性。除了活跃的验证人集之外，BOT Chain还维护着一组被称为“候选者”的备份验证人。这些候选验证者还可以在主网上生成区块并收取燃气费（尽管概率比活跃验证者低得多）。无法参加或行为不端的候选人仍然会受到削减，尽管幅度有所降低。这种设计为候选人保持在线并为网络安全做出贡献提供了强有力的经济激励。在极端情况下，例如当大多数活跃验证者因攻击而离线时，候选验证者可以报告停滞的区块生产，帮助恢复链，并触发活跃验证者集的重新选举。
BOT Chain 还提供：
完全EVM兼容性 – 支持所有现有的Ethereum工具，同时提供更快的最终结果并大幅降低费用。
快速最终确定——交易通常在两个区块内完成。
原生互操作性 – 内置、高效的跨链通信和资产转移。
自主权区块链 – 由具有强大链上治理的当选验证者集提供保护。
高性能扩展 – 针对需要速度和无缝用户体验的 dApps 进行了优化。
通过PoSA进行去中心化治理——将安全性与真正的社区参与相结合。原生 BOT 代币既可作为智能合约执行的 Gas，又可作为网络安全和治理的质押资产。
BOT Chain 从头开始​​构建，速度快、价格实惠、可互操作且由社区驱动，使其成为下一代 DeFi 和去中心化应用程序的理想基础。

---

## 快速最终性

Source: https://dev-docs.botchain.ai/zh-Hans/docs/introduction/fast-finality/

简介
快速最终性
最终性对于区块链安全至关重要，一旦区块被最终确定，它就不会再被恢复。快速最终性功能非常有用。用户可以确保他们从最新确定的区块中获得准确的信息，然后他们可以立即决定下一步做什么。
BOT Chain 鼓励用户等待，直到收到超过 ⅔N+1 个不同验证者密封的区块。这样，BOT Chain 可以容忍少于 ⅓N 的拜占庭验证者。例如，对于 21 个验证人，如果出块时间为 3 秒，⅔N+1 个不同的验证人印章将需要 (⅔21+1)3 = 45 秒的时间段。 BOT Chain 的任何关键应用程序可能必须等待 ⅔N+1 以确保相对安全的最终性。通过上述削减机制的增强，1/2*N+1甚至更少的区块足以作为大多数交易的确认。
当功能Fast Finality启用时。如果 ⅔*N 或更多验证者正常投票，则该链将在两个区块内最终确定，否则该链将有固定数量的区块来像以前一样达到概率最终性。

---

## 质押权限证明

Source: https://dev-docs.botchain.ai/zh-Hans/docs/introduction/proof-of-staked-authority/

简介
质押权限证明
虽然工作量证明（PoW）已被公认为是实现去中心化网络的实用机制，但它对环境并不友好，而且还需要大量参与者来维护安全。
Ethereum 和其他一些区块链网络，例如 MATIC Bor、TOMOChain、GoChain、xDAI，在不同场景（包括测试网和主网）中确实使用了权威证明（PoA）或其变体。 PoA 提供对 51% 攻击的一定防御，提高了效率和对某些级别的拜占庭玩家（恶意或黑客攻击）的容忍度。它是一个很容易选择作为基础的选择。
同时，PoA协议最受批评的是它不像PoW那样去中心化，因为验证者（即轮流生产区块的节点）拥有所有权限，并且容易受到腐败和安全攻击。其他区块链，例如 EOS 和 Lisk，都引入了不同类型的委托权益证明 (DPoS)，以允许代币持有者投票并选择验证者集。它增加了权力下放并有利于社区治理。
BOT Chain 这里建议将 DPoS 和 PoA 结合起来达成共识，这样：
区块由一组有限的验证者生成
验证者以PoA的方式轮流生产区块，类似于Ethereum 的 Clique共识设计
验证器集是根据基于质押的治理来选举进出的
快速定稿可以极大提升用户体验。 Fast Finality 功能将在即将到来的 Plato 升级时启用。这将是BOT Chain的一大优势，许多dapp都将从中受益。
BOT Chain的共识协议实现以下目标：
阻塞时间短，主网0.75秒。
确认交易的最终性需要相当短的时间。
原生代币没有通货膨胀：BOT，区块奖励从交易费用中收取，并以BOT支付。
与Ethereum系统100%兼容。
它允许现代的权益证明区块链网络治理。

---

## 奖励

Source: https://dev-docs.botchain.ai/zh-Hans/docs/introduction/reward/

简介
奖励
当前验证人集合中的所有BOT Chain验证人将获得BOT中的交易费用奖励。由于 BOT 不是通胀代币，因此不会像比特币和 Ethereum 网络那样产生挖矿奖励，而 Gas 费是验证者的主要奖励。即将到来的Plato升级后，收取的部分费用将用于最终投票的奖励。由于 BOT 也是具有其他用例的实用代币，委托人和验证者仍将享受持有 BOT 的其他好处。
验证者的奖励是从每个区块的交易中收取的费用。验证者可以决定向将 BOT 质押给他们的委托人回馈多少，以吸引更多质押。每个验证者都会以相同的概率轮流出块（如果他们坚持 100% 的活跃度），因此，从长远来看，所有稳定的验证者都可能获得相似大小的奖励。同时，每个验证者的赌注可能不同，因此这会带来一种违反直觉的情况，即更多的用户信任并委托给一个验证者，他们可能获得更少的奖励。因此，只要验证人仍然值得信赖，理性的委托人就会倾向于委托给权益较少的人（不安全的验证人可能会带来极大的风险）。最终，所有验证者的赌注变化将会更小。这实际上可以防止其他网络上出现的权益集中和“赢家永远获胜”的问题。

---

## 安全

Source: https://dev-docs.botchain.ai/zh-Hans/docs/introduction/security/

简介
安全
鉴于有超过 ½*N+1 验证者是诚实的，基于 PoA 的网络通常安全且正常工作。然而，仍然存在一定数量的拜占庭验证者仍可能设法攻击网络的情况，例如通过克隆攻击。 BOT Chain 确实引入了 Slashing 逻辑来惩罚拜占庭验证者的双重签名或不可用。这种 Slashing 逻辑将在很短的时间内暴露恶意验证者，并使“克隆攻击”执行起来非常困难或极其无益。

---

## 质押和治理

Source: https://dev-docs.botchain.ai/zh-Hans/docs/introduction/staking-and-governance/

简介
质押和治理
权益证明带来了权力下放和社区参与。其核心逻辑可概括如下。您可能会在其他网络中看到类似的想法，尤其是 Cosmos 和 EOS。
代币持有者，包括验证者，可以将他们的代币“绑定”到权益中。代币持有者可以将他们的代币委托给任何验证者或验证者候选者，期望它成为真正的验证者，然后他们可以选择不同的验证者或候选者来重新委托他们的代币。
所有候选验证人将按照其绑定代币数量进行排名，排名靠前的将成为真正的验证人。
验证者可以与委托者分享（部分）他们的区块奖励。
验证者可能会遭受“削减”，这是对其不良行为（例如双重符号和/或不稳定）的惩罚。
验证者和委托者有一个“解除绑定期”，以便系统确保在发现不良行为时代币保持绑定状态，在此期间责任人将被削减。

---

## 验证器创建指南

Source: https://dev-docs.botchain.ai/zh-Hans/docs/staking/validator-creation-guide/

质押
验证器创建指南
本页总览
本指南概述了在 BOT Chain 上创建新验证器的过程。 BOT 质押 dApp 是用于在 BOT Chain 上创建和管理验证器的官方工具。
测试网：https://staking.bohr.life
主网：https://staking.botchain.ai
术语​
算子地址：BOT上创建和修改验证人信息的地址。连接到质押 dApp 时应使用此地址。对应账户应有超过2001个BOT用于创建验证器和支付交易费用。
共识地址：验证者节点的唯一地址。它用于挖掘新块时的共识引擎。它应该与运营商的地址不同。如果您在信标链上创建了现有的验证器，则旧的共识地址无法重复使用，您应该创建一个新的。
投票地址：用于快速最终投票的地址。如果您在信标链上创建了现有的验证器，则旧的投票地址无法重复使用，您应该创建一个新的。
BLS 证明：验证投票地址所有权的 BLS 签名。
身份：用于将新验证器与信标链中的现有验证器相关联。当委托人迁移他们的权益时，它非常有用 - 他们可以知道有一个新的验证器由同一验证器操作员运行。除非您要迁移旧的验证器，否则这是可选的。
步骤​
1. 连接到 dApp​
请使用您的运营商地址连接到质押 dApp。 MetaMask 和 WalletConnect 选项可用于该步骤。在继续下一步之前，请确保该帐户的余额超过 2001 BOT。
2. 填写表格​
导航到 dApp 并选择页面右中部的“成为验证者”按钮以启动创建过程。
创建验证器需要以下信息。
基本信息​
您需要在创建验证器页面上提供以下详细信息：
验证器名称：选择由 3-9 个字母数字字符组成的名称，不包括特殊字符。
网站：提供一个网站 URL，其中包含有关您的验证器的其他信息。
描述：验证器的简短描述。
地址​
需要以下地址：
共识地址：验证者节点的唯一地址。
投票地址：用于快速最终投票的地址。
身份：用于将新验证器与信标链中的现有验证器相关联。除非您要迁移旧的验证器，否则这是可选的。
生成共识地址​
注意：请确保根据您的计算机平台下载正确的二进制文件，例如，如果您使用的是 MacOS，则应下载 geth_mac 文件。为了简单起见，下面我们将二进制文件称为 geth。
创建新账户进行挖矿，请使用以下命令并为该账户设置密码。
geth account new --datadir ${DATA_DIR}
DATA_DIR：您要存储密钥存储文件的目录。
该命令将返回公共地址（即共识地址）和您的私钥路径。请备份密钥文件！
共识地址示例为 0x4b3FFeDb3470D441448BF18310cAd868Cf0F44B5。
如果您已经有挖矿账号，可以使用助记词恢复账号。
geth account import --datadir ${DATA_DIR}
如果您在信标链上创建了验证器，请使用不同的验证器作为共识地址。
生成投票地址和 BLS 证明​
要创建新的 BLS 帐户，请使用以下命令。
geth bls account new --datadir ${DATA_DIR}
如果您已有投票密钥，请使用以下命令创建 bls 钱包并使用密钥文件来恢复它。
geth bls account import ${KEY_FILE} --datadir ${DATA_DIR}
DATA_DIR：用于恢复BLS帐户的备份文件。
然后您可以通过运行以下命令来获取您的投票地址。
geth bls account list --datadir ${DATA_DIR}
示例地址为 b5fe571aa1b39e33c2735a184885f737a59ba689177f297cba67da94bea5c23dc71fd4deefe2c0d2d21851eb11081f69。
然后你可以通过运行以下命令来获取你的 bls 证明。
geth bls account generate-proof --chain-id ${BOT_CHAIN_ID} ${OPEATOR_ADDRESS} ${VOTE_ADDRESS}
BOTCHAINID：BOT 主网为 677，BOT 测试网为 968。
OPEATOR_ADDRESS：您的帐户地址，该地址将被识别为新验证器的操作者。
VOTE_ADDRESS：上一步创建的投票地址。
一个示例证明是0xaf762123d031984f5a7ae5d46b98208ca31293919570f51ae2f0a03069c5e8d6d47b775faba94d88dbbe591c51c537d 718a743b9069e63b698ba1ae15d9f6bf7018684b0a860a46c812716117a59c364e841596c3f0a484ae40a1178130b76a5
创建身份​
注意：确保您根据机器的平台下载正确的二进制文件，例如，如果您使用 MacOS，则应下载 macos_binary.zip 文件，解压后您将找到 botcli（用于 mainet）和 tbotcli（用于 testnet）。为了简单起见，下面我们将二进制文件称为 botcli。
设置帐户​
如果您有助记词，可以通过以下命令导入您的账户：
${workspace}/bin/botcli keys add <your-account-name> --recover --home ${HOME}/.botcli
Enter a passphrase for your key:
Repeat the passphrase:
输入您的恢复助记词：
您将被要求为此帐户设置密码并输入您的助记词。之后，您将获得您的帐户信息。
${workspace}/bin/botcli：botcli 二进制可执行文件的路径。对于测试网，您应该使用 tbotcli。
${HOME}：存储帐户信息的文件夹。
或者，如果您有分类帐，您可以通过运行以下命令导入您的帐户：
${workspace}/bin/botcli keys add <your-account-name> --ledger --index ${index} --home ${HOME}/.botcli
${workspace}/bin/botcli：botcli 二进制可执行文件的路径。对于测试网，您应该使用 tbotcli。
${index}：您要导入的账本账户的索引。
获取身份​
账号导入后，您可以通过以下命令获取您的身份：
对于本地密钥：
${workspace}/bin/botcli \ validator-ownership \ sign-validator-ownership \ --bot-operator-address ${NEW_VALIDATOR_OPERATOR_ADDR_ON_BOT} \  --from ${ACCOUNT_NAME} \  --chain-id ${BOT_CHAIN_ID} \
对于账本密钥：
${workspace}/bin/botcli \ validator-ownership \ sign-validator-ownership \ --bot-operator-address ${NEW_VALIDATOR_OPERATOR_ADDR_ON_BOT} \ --from ${BOT_OPERATOR_NAME} \ --chain-id ${CHAIN_ID} \ --ledger
${workspace}/bin/botcli：botcli 二进制可执行文件的路径。对于测试网，您应该使用 tbotcli。
--to ${NEWVALIDATOROPERATORADDRON_BOT}：指定新验证器操作符地址将映射到的BOT地址。
--from ${ACCOUNT_NAME}：指定执行签名的帐户名。该帐户应该是在信标链上创建的验证器的操作者。
你将得到如下输出：
TX JSON: {"type":"auth/StdTx","value":{"msg":[{"type":"migrate/ValidatorOwnerShip","value":{"bot_operator_address":"RXN7r5XZlaljqzp8msZvx6Y6124="}}],"signatures":[{"pub_key":{"type":"tendermint/PubKeySecp256k1","value":"Ahr+LlBMLgiUFkP75kIuJW1YHrsTy39GeOdV+IaTREDN"},"signature":"AL5mj52s0+tcdoEb6c6PAmqBixuv3XEmrLW3Y1kvUeYgG3RqVvWU/dIVcfxiHHwLGXlcn0X1v00jFrpLIsxtqA==","account_number":"0","sequence":"0"}],"memo":"","source":"0","data":null}}
Sign Message: {"account_number":"0","chain_id":"Bot-GGG-Ganges","data":null,"memo":"","msgs":[{"bot_operator_address":"0x45737baf95d995a963ab3a7c9ac66fc7a63ad76e"}],"sequence":"0","source":"0"}
Sign Message Hash: 0x8f7179e7969e497b5f3c006535e55c2fa5bea5d118a8008eddce3fccd1675673
Signature: 0x00be668f9dacd3eb5c76811be9ce8f026a818b1bafdd7126acb5b763592f51e6201b746a56f594fdd21571fc621c7c0b19795c9f45f5bf4d2316ba4b22cc6da8
PubKey: 0x021afe2e504c2e08941643fbe6422e256d581ebb13cb7f4678e755f886934440cd
签名是您与在 BOT Chain 上创建的旧验证器关联的身份。
佣金​
Rate：验证人的佣金率。
最大佣金率：验证者可以设置的最大佣金率。
最大变化率：验证者可以为每个时期（1 天）设置的最大变化率。
自我委托​
自委托金额：创建验证器时委托的金额。输入的最小数字是 2001 - 最小自委托金额是 2000 BOT 和额外的 1 BOT 用于锁定死地址。
3. 提交表格​
填写完所有必填信息后，单击“提交”按钮提交交易。
注意：完成这些步骤后，不保证您的节点成为活跃验证者。选择基于反映总 BOT 权益的排名，仅选择前 N 个节点作为活跃验证者。数量 N 由 StakeHubContract 中的“maxElectedValidators”参数确定（0x0000000000000000000000000000000000002002）。

