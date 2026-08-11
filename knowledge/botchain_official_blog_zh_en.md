# BOT Chain Official Blog

Synced: 2026-08-09; posts=4

---

## 走进 BOT Chain：AI 智能体身份、算力与结算基础设施

Source: https://www.botchain.ai/zh/blog/ai-agent-infrastructure-bot-chain

【相关问题】走进 BOT Chain：AI 智能体身份、算力与结算基础设施 / blog ai-agent-infrastructure-bot-chain
【关键词】blog;AI Agent;AI-native;基础设施;BOT Chain
【参考回答-中文】
返回博客走进 BOT Chain：AI 智能体身份、算力与结算基础设施
一份状态感知的指南，介绍 BOT Chain 当前 EVM 基础及其在 AI 智能体身份、算力协调与可验证结算方面的方向。
BC
BOT Chain 编辑团队
2026年8月6日约 2 分钟阅读
复制链接分享
AI 智能体基础设施是让软件智能体能够标识自身、获取或协调算力、在策略约束下执行交易并可信结算结果的一组系统。在 BOT Chain 上，当前已记录的基础是兼容 EVM 的 §LAYER1§，具备 RPC 访问、测试网工具、节点运营资源与 BOT Explorer；智能体专用身份与账户功能属于即将推出的 AI Agent Launchpad V1。
这一区分很重要。AI 模型可以生成决策，但仅凭持有私钥无法安全地成为经济参与者。生产级智能体需要对身份、权限、算力、交易执行与证据分别进行控制。本指南将这些层级映射到 BOT Chain，同时清晰区分可公开使用的基础设施与已宣布的产品方向及路线图事项。
AI 智能体需要的是技术栈，而非单一的“AI 区块链”功能
区块链本身并不能让软件自主运行。它可以提供共享执行、资产所有权与可审计记录，但智能体的推理、私有数据以及许多外部工具通常仍保留在链下。因此，有价值的设计问题不是整个 AI 模型是否运行在链上，而是哪些决策与状态转换需要共同的、可验证的结算层。
对大多数应用而言，需要四个相互连接的层级。身份为智能体提供其他系统可发现或验证的稳定引用。算力提供完成任务所需的推理或处理资源。执行与策略决定智能体被允许做什么。结算记录价值转移与状态变更，以便另一方可以独立查验结果。
BOT Chain AI 智能体基础设施的状态感知图
BOT Chain 将自己定位为面向自主 AI 智能体与去中心化价值系统、兼容 EVM 的 AI 原生 §LAYER1§，并将 DePIN 作为其更广泛生态方向之一。然而，其 AI 智能体技术栈中的各组件并非都处于相同的可用状态。评估该网络最可靠的方式，是将当前 EVM 基础与即将推出的 Launchpad 能力及其已发布的算力路线图分开看待。
图 1. BOT Chain AI 智能体基础设施的状态感知视图。当前公开基础与即将推出及路线图事项相互分离。来源审阅：2026年8月3日。
状态说明：路线图日期并不能证明某项功能已在生产环境可用。在发布开发者主张或部署依赖之前，应验证当前产品页面、发布说明与开发者文档。
层级
公开证据
本文使用的状态
开发者应如何假设
身份
BOT Chain 官方帖子称 Launchpad V1 将支持 ERC-8004。
即将推出
在发布文档确认之前，不要将 ERC-8004 智能体身份描述为已上线。
算力
网站呈现了 DePIN 算力架构，并在路线图中列出 §VCOMPUTE§ 与算力节点激活。
已发布路线图
在没有当前产品文档的情况下，不要推断公开算力市场或链上模型运行时已可用。
执行与策略
BOT Chain 支持 EVM 智能合约，而应用特定的权限与交易控制仍是开发者的责任。计划中的 ERC-4337 支持属于 Launchpad V1。
当前 EVM 执行 / 即将推出的账户基础设施
智能合约执行今天即可使用，但智能体专用钱包、委托与策略控制不应被视为已发布产品。
结算
开发者文档公布了 EVM 兼容性、主网与测试网 RPC 资源、部署指南与 Explorer 访问方式。
当前已记录的基础
开发者可以使用已发布的资源，将这条链作为 EVM 执行与结算环境进行评估。
身份：智能体交易前需要的可验证引用
智能体需要的不仅是名称或钱包地址。其他应用可能需要发现其服务端点、确认由谁控制，并将交互与持久记录关联。ERC-8004 是以太坊标准轨草案提案，面向跨组织边界的智能体发现、身份、声誉与验证。
BOT Chain 已宣布 AI Agent Launchpad V1 将支持 ERC-8004。该表述具有前瞻性：Launchpad V1 被描述为即将推出，因此本文不将 ERC-8004 注册呈现为 BOT Chain 当前已发布的功能。相关实现细节、注册表地址与开发者工作流应以最终发布文档为准。
对构建者而言，实用经验是将身份与授权分开。可发现的智能体档案有助于交易对手方找到并评估智能体，但不应自动授予其对资产的无限制控制权。身份回答“这是哪个智能体？”策略回答“它可以做什么？”这是相关但不可互换的两个问题。
算力：协调资源，而非将整个模型放到链上
AI 工作负载通常依赖 GPU、CPU、存储、模型端点与私有应用数据。在通用区块链上记录每一步推理往往不必要、成本高昂或与隐私要求不兼容。更稳妥的架构将模型执行保留在链下，同时用区块链记录需要共享验证的承诺、权限、支付与结果。
BOT Chain 的 官方网站 阐述了 §VCOMPUTE§ 与去中心化算力协调的路线图，包括算力节点激活。这些引用描述的是已发布的算力路线图；它们本身并不能证明每项计划中的算力服务都已公开可用。开发者在将算力层视为应用依赖之前，应查找当前的节点规格、API、服务条款以及可验证的作业结果格式。
这种区分也能避免一种常见范畴错误：去中心化算力并不等同于链上结算。算力产生输出，结算决定接受哪种状态变更或支付。生产级设计需要在两者之间建立明确桥梁——例如经过认证的结果、验证规则，以及记录已接受结果的交易。
执行与结算：当前公开基础
技术栈中当前记录最清晰的部分是 BOT Chain 的 EVM 执行环境。开发者文档 目前将 BOT Chain 呈现为兼容 EVM 的 §LAYER1§，而项目最新定位聚焦于面向自主智能体与去中心化价值系统的 AI 原生基础设施。文档发布了网络配置、JSON-RPC 访问、测试代币、合约部署、验证与节点运营相关资源。官方网站 将 BOT 标识为用于链上 Gas 的原生代币，而 BOT Explorer 可查看交易、地址、合约和网络活动。
由于网络暴露熟悉的 EVM 接口，团队可以从标准智能合约与 RPC 工作流起步，而不必等待每一项智能体专用产品。相关起点包括 BOT Chain 开发者文档，开发者板块 和 BOT Explorer.
EVM 兼容性很有价值，但它不会自动创造安全的智能体自主性。开发者仍需定义合约级规则、签名者托管、交易限额、故障处理、监控与人工干预路径。BOT Chain 还宣布了计划在 ERC-4337 支持，见于 AI Agent Launchpad V1。在技术发布材料可用之前，应将其视为即将推出的产品方向，而非默认的生产级账户基础设施。
实用的智能体到结算工作流
以下工作流是一种架构模式，而非声称每个步骤都已打包为 BOT Chain 产品。它展示团队今天如何结合当前 EVM 基础设施与应用层控制，同时为未来的 Launchpad 能力保留清晰的集成点。
步骤 1：定义任务与信任边界
明确智能体可以决策的范围、可访问的数据、最大风险敞口以及哪些操作需要人工批准。将私有提示词、凭证与敏感数据保留在公开交易载荷之外。
步骤 2：附加身份，但不与权限混为一谈
今天使用应用层身份，并在 Launchpad V1 发布 ERC-8004 注册时规划迁移路径。将身份记录视为用于发现与声誉的引用，而非花费或修改合约的全面权限。
步骤 3：在链下运行模型与工具
在符合应用延迟、隐私与成本要求的环境中执行推理、检索与外部 API 调用。仅捕获另一方必须验证的承诺或结果。
步骤 4：提交前执行策略
验证合约地址、函数选择器、金额、截止时间与时限。拒绝超出已批准策略的操作，并为模糊或高影响决策保留复核路径。
步骤 5：在 BOT Chain 上提交并验证
使用已记录的 RPC 接口提交已授权交易。通过 BOT Explorer 或直接查询的 RPC 端点确认回执、合约事件与最终状态。你的应用应定义交易回滚、延迟或产生意外状态时的处理方式。
开发者现在可以评估什么
团队无需等待完整智能体路线图即可验证结算层。一个实用的概念验证可以：将 EVM 工具链连接至 BOT Chain，使用已发布的主网或测试网配置，在适当时获取测试代币，部署小型合约，提交受控交易，并通过 BOT Explorer 验证产生的事件。这测试的正是智能体应用最终将依赖的接口。
策略层应同步设计。定义允许的合约与方法、支出上限、过期规则、重试行为与紧急暂停机制。存储足够的结构化证据以还原智能体为何请求某项操作，但不要在链上公开密钥或敏感模型上下文。当 Launchpad V1 文档发布后，应评估其身份、钱包与 ERC-4337 组件如何契合这些控制，而不是默认取代它们。
这一架构证明了什么——又没有证明什么
BOT Chain 的公开材料支持一项当前主张：开发者可以访问兼容 EVM 的 §LAYER1§、RPC 资源、测试网工具、节点运营资源以及透明的 BOT Explorer 记录。它们也支持一项前瞻性主张：AI Agent Launchpad V1 即将推出，并计划支持草案 ERC-8004 身份基础设施与 ERC-4337 账户抽象。网站还发布了 §VCOMPUTE§ 与去中心化算力协调的路线图。
这些来源并不足以支持“每个 AI 智能体已经可以通过一个生产级界面完成注册、获得专用智能账户、购买去中心化算力并结算端到端自主工作流”这一更强主张。该主张应等待发布文档、已部署合约、支持的网络地址以及可复现的开发者流程。清晰的状态表述不是故事的局限，而是让基础设施可信、可测试的关键。
核心要点
AI 智能体基础设施在身份、算力、策略与结算相互连接、而非被揉成一个模糊功能时才能发挥作用。BOT Chain 今天提供可公开访问且可测试的 EVM 执行基础，包括 RPC 访问、测试网资源、智能合约部署以及透明的 BOT Explorer 记录。其即将推出的 Launchpad 与已发布的算力路线图旨在用智能体身份、智能账户和更广泛的资源协调来扩展这一基础。构建者现在即可开始测试当前链接口，并在相关技术组件发布后逐步集成新的智能体专用能力。
常见问题
BOT Chain 会直接在链上运行 AI 模型吗？
当前公开的开发者文档并未确立通用的链上模型推理运行时。BOT Chain 网站发布了 §VCOMPUTE§ 与去中心化算力协调的路线图。实用设计通常将推理保留在链下，仅记录需要共享验证的权限、承诺、支付或结果。
ERC-8004 身份今天在 BOT Chain 上可用吗？
BOT Chain 官方公告称 AI Agent Launchpad V1 将支持草案 ERC-8004 提案，并将该产品描述为即将推出。在发布文档提供已部署合约、网络地址与实现工作流之前，该支持应被描述为计划中，而非当前可用。
EVM 兼容性为何与 AI 智能体基础设施相关？
它让开发者能够使用熟悉的智能合约模式、RPC 方法与面向以太坊的工具来处理执行与结算层。它不会自动提供智能体身份、安全委托或策略控制；这些必须来自应用设计或单独发布的智能体账户基础设施。
团队在生产环境使用 BOT Chain 之前应验证什么？
验证最新的网络与 RPC 配置、合约部署与验证流程、钱包或签名者控制、Gas 资金、监控、故障恢复与 Explorer 可见性。对于路线图或 Launchpad 功能，还应要求当前的发布说明、合约地址、安全信息以及可复现的集成路径。
从已记录的基础开始构建
从可公开访问且可测试的接口开始：阅读开发者文档，查阅开发者资源，在 BOT Explorer 中查看网络活动 和 探索 BOT Chain 生态支持计划。若要了解更广泛的概念，请参阅 什么是 AI 原生区块链？.
下一篇什么是 AI 原生区块链？ BOT Chain 实用入门指南
【参考回答-英文】
详见原文：https://www.botchain.ai/zh/blog/ai-agent-infrastructure-bot-chain
【来源】https://www.botchain.ai/zh/blog/ai-agent-infrastructure-bot-chain

---

## 什么是 AI 原生区块链？ BOT Chain 实用入门指南

Source: https://www.botchain.ai/zh/blog/what-is-an-ai-native-blockchain

【相关问题】什么是 AI 原生区块链？ BOT Chain 实用入门指南 / blog what-is-an-ai-native-blockchain
【关键词】blog;AI Agent;AI-native;基础设施;BOT Chain
【参考回答-中文】
返回博客什么是 AI 原生区块链？ BOT Chain 实用入门指南
AI 原生区块链旨在为自主软件提供账户、策略、执行、结算和可审计性，使其能够安全地在链上运行。
BC
BOT Chain 编辑团队
2026年8月3日约 2 分钟阅读
复制链接分享
AI 原生基础设施并不是贴上了 AI 标签的区块链，而是为自主软件持有权限、执行交易、结算价值并留下可审计记录而设计的网络。
AI 原生区块链是面向 AI 智能体作为活跃参与者而构建的可编程结算与协调层。它为软件控制的参与者提供使用账户、遵循支出与访问策略、调用智能合约、支付服务、验证结果并创建可供其他系统查验的链上历史的能力。
这一区分很重要，因为 AI 模型可以生成决策，但无法独自建立经济信任。一旦智能体被允许购买算力、转移代币、触发合约或向另一台机器付款，应用就需要可执行的边界和可靠的行为记录。这正是区块链基础设施的作用。
BOT Chain 是兼容 EVM 的 AI 原生 Layer 1 区块链，面向自主 AI 智能体与去中心化价值系统。对 AI 构建者而言，其价值体现在熟悉的以太坊开发流程、高性能执行、低交易成本和透明的链上可观测性。
什么让区块链成为 AI 原生？
“AI 原生区块链”仍是一个新兴类别，而非单一正式标准。因此，有用的定义应从工作负载出发，而非标签本身。AI 智能体持续运行、以软件速度决策、与 API 和服务交互，并可能需要在无需人类逐步审批的情况下完成交易。面向这些智能体的基础设施必须支持自主性，同时约束这种自主性。
通用链可以承载与 AI 相关的智能合约，但 AI 原生区块链更进一步：其网络、账户模型、开发者接口及周边基础设施都围绕机器驱动的执行与验证来组织。实践中，六项能力决定一条区块链是否已准备好承载 AI 智能体应用。
图 1. 六维 AI 原生区块链就绪框架。
AI 智能体所需能力
能力
智能体需要什么
为何重要
身份与策略
账户以及谁或什么可以行动的规则
自主性需要清晰的权限边界。
执行
确定性的智能合约调用与交易回执
意图必须转化为可执行的状态变更。
结算
可预测的费用与及时的最终性
智能体需要知道一项操作何时完成。
验证
可观察的状态、日志与交易历史
其他智能体和应用必须能够核验结果。
算力协调
请求、核算或结算外部资源的方式
大多数 AI 推理仍在链下，但访问与支付可以在链上协调。
开发者兼容性
稳定的 RPC 访问、开发者文档和熟悉的 EVM 工具
构建者需要高效交付并维护智能体应用。
这些能力构成了评估 AI 原生区块链基础设施的通用框架。它们不应被理解为本文提及的每个网络当前都已具备的功能。
传统区块链设计为何可能不足
大多数区块链用户体验围绕人们打开钱包、查看提示并逐笔批准交易而设计。当软件需要反复行动、响应变化并按需购买服务时，这种模式就会显得笨拙。
三类约束很快就会出现。第一，拥有不受限制权限的钱包会带来不可接受的风险。第二，缓慢或不可预测的结算会让智能体难以判断是否继续工作流。第三，强迫每个用户或智能体在执行小额操作前先获取原生代币，会带来运营摩擦。AI 原生设计通过明确策略、更快确认、可编程费用处理和更好的可观测性来解决这些约束。
同样重要的是明确哪些内容应放在链上。大语言模型推理和其他算力密集型任务通常仍在链下。链在这些任务周围最有价值的是作为信任层：记录授权、协调访问、结算支付，并锚定可后续核验的结果或回执。
BOT Chain 如何契合 AI 原生模型
1. 兼容 EVM 的开发环境
BOT Chain is an EVM-compatible, AI-native Layer 1 blockchain designed for autonomous AI agents and decentralized value systems. 开发者可以使用熟悉的以太坊工具和工作流部署智能合约并构建去中心化应用，而无需重建整套开发栈。
The BOT Chain developer environment provides mainnet and testnet RPC access, test tokens, contract deployment resources and on-chain verification tools. Developers can begin with the BOT Chain Quick Guide.
2. 高性能链上执行
BOT Chain 采用 SPoA 共识机制，支持高效的出块与网络协调。网络目前平均出块时间约 0.7 秒，峰值吞吐量超过 10,000 TPS，交易费用通常低于 0.01 美元。该执行环境旨在支持 AI 智能体与 Web3 应用中频繁、自动化且低价值的交互。
3. 透明的网络基础设施
BOT Explorer 提供对交易、区块、地址、代币和已验证合约的访问。BOT Bridge、BDEX 和 Bo Wallet 进一步连接 BOT Chain 生态中的网络访问、跨链资产、流动性和用户交互。
Builders can inspect live network records through BOT Explorer and review the wider network through the BOT Chain ecosystem pages.
4. 不断扩展的 AI 智能体路线图
BOT Chain 正在开发 AI Agent Launchpad V1，以在 Layer 1 基础设施上扩展智能体创建、链上身份、智能账户能力和原生资产发行。计划支持 ERC-8004 和 ERC-4337，旨在为自主应用提供更强大的身份与账户基础设施。
这些能力仍在推进中，在相关官方发布和文档公开之前，不应被视为已上线产品。
5. AI 智能体与 DePIN 生态发展
BOT Chain 持续在 AI 智能体与 DePIN 场景中扩展，探索区块链基础设施如何连接自主应用、物理资源与链上价值结算。算力密集型工作负载可保留在链下，而授权、支付和可验证记录可锚定在链上。
面向 AI 构建者的实用工作流
步骤 1：定义智能体的权限边界
写下智能体可以做什么、可以调用哪些合约、单次操作的最大价值、周期内的最大价值，以及哪些操作始终需要人工批准。该策略应在智能体获得资金账户之前建立。
步骤 2：选择账户与费用模型
决定应用将使用 EOA、智能合约账户、MPC 控制钱包还是其他托管模式，然后决定由谁支付 Gas。如果适合赞助模式，应定义资格规则和回退路径，而不是将“免 Gas”视为无条件承诺。
步骤 3：连接、测试与观察
使用测试网 RPC 和水龙头验证交易生命周期。记录请求、策略决策、签名、交易哈希、回执和最终状态。应像测试成功操作一样仔细测试被拒绝的操作；策略失败和网络错误都是生产工作流的一部分。
步骤 4：按风险匹配确认要求
按交易类别建立确认规则。低价值、可逆操作可在短确认窗口后继续；高价值或不可逆操作应要求更强的结算保障，并可能需要额外批准。AI 原生应用并不是消除所有人工决策，而是让剩余决策变得明确。
步骤 5：监控完整经济闭环
不仅衡量交易是否成功，还要跟踪交易成本、策略失败、确认时间、合约错误、智能体重试以及外部服务交付的价值。这些信号表明系统是否足够经济且安全，可以扩展。
AI 原生区块链并不意味着什么
它并不意味着把整个 AI 模型放到链上，也不意味着允许模型无限制支出，更不意味着高 TPS 本身就足以让网络适合智能体。它也无法替代应用层安全、模型评估和运营监控。
最可信的 AI 原生系统会将机器自主性与有边界的权限结合起来。区块链提供共享状态、可编程结算和可审计性；应用提供模型逻辑、业务规则、用户体验和风险控制。两者缺一不可。
常见问题
AI 原生区块链与部署在区块链上的 AI 项目有何不同？
是的。AI 项目可能只是在通用链上部署代币或合约，而 AI 原生基础设施围绕持续的机器操作、权限、结算、验证和资源协调来设计。
AI 模型需要运行在链上吗？
通常不需要。推理可以保留在链下，而区块链负责管理授权、支付、回执和可验证状态。这种分工既保持算力实践可行，也保留了共享信任层。
EVM 兼容性为何对 AI 开发者重要？
它让团队能够使用成熟的智能合约语言、库、钱包和开发工具，从而缩短从智能体原型到可测试链上应用的路径。
团队应如何评估 AI 原生 Layer 1？
应评估身份与账户选项、权限控制、费用处理、最终性、可观测性、开发者工具、算力协调以及官方文档质量。应将未经验证的路线图声明与今天即可测试的功能分开看待。
为自主应用构建信任层
AI 智能体需要的不仅是智能。要参与开放的数字经济，它们需要可执行的权限、可靠的执行、经济的结算，以及可供其他系统验证的记录。AI 原生区块链正是提供这一信任层的基础设施。
BOT Chain 为构建者提供兼容 EVM 的执行环境、文档化的网络访问、快速出块、低交易成本和透明的链上可观测性。其不断演进的 AI 智能体路线图旨在通过链上身份、智能账户和可编程价值交互扩展这一基础。
下一步是将今天已有的能力转化为范围明确的智能体工作流，在故障条件下进行测试，并仅在证据支持时才扩大权限范围。
开始构建：阅读开发者文档  |  探索网络  |  查看 BOT Chain 生态
【参考回答-英文】
详见原文：https://www.botchain.ai/zh/blog/what-is-an-ai-native-blockchain
【来源】https://www.botchain.ai/zh/blog/what-is-an-ai-native-blockchain

---

## Inside BOT Chain: Infrastructure for AI Agent Identity, Compute and Settlement

Source: https://www.botchain.ai/en/blog/ai-agent-infrastructure-bot-chain

【相关问题】Inside BOT Chain: Infrastructure for AI Agent Identity, Compute and Settlement / blog ai-agent-infrastructure-bot-chain
【关键词】blog;AI Agent;AI-native;基础设施;BOT Chain
【参考回答-英文】
Back to BlogInside BOT Chain: Infrastructure for AI Agent Identity, Compute and Settlement
A status-aware guide to BOT Chain’s current EVM foundation and its direction for AI agent identity, compute coordination and verifiable settlement.
BC
BOT Chain Editorial Team
Aug 6, 202610 min read
Copy linkShare
AI agent infrastructure is the set of systems that lets software agents identify themselves, obtain or coordinate compute, execute transactions under policy and settle results verifiably. On BOT Chain, the currently documented foundation is an EVM-compatible Layer 1 with RPC access, testnet tools, node-operation resources and BOT Explorer; agent-specific identity and account features belong to the upcoming AI Agent Launchpad V1.
This distinction matters. An AI model can generate a decision, but it cannot safely become an economic actor merely by holding a private key. Production agents need separate controls for identity, permissions, compute, transaction execution and evidence. This guide maps those layers to BOT Chain while clearly separating public, usable infrastructure from announced product direction and roadmap items.
AI agents need a stack, not a single “AI blockchain” feature
A blockchain does not make software autonomous by itself. It can provide shared execution, asset ownership and auditable records, but the agent’s reasoning, private data and many external tools will usually remain off-chain. The useful design question is therefore not whether an entire AI model runs on-chain. It is which decisions and state transitions need a common, verifiable settlement layer.
For most applications, four connected layers are required. Identity gives an agent a stable reference that other systems can discover or verify. Compute supplies the inference or processing resources used to complete a task. Execution and policy determine what the agent is allowed to do. Settlement records value transfer and state changes so that another party can independently inspect the result.
A status-aware map of BOT Chain’s AI agent infrastructure
BOT Chain positions itself as an EVM-compatible, AI-native Layer 1 designed for autonomous AI agents and decentralized value systems, with DePIN as one of its broader ecosystem directions. However, the components across its AI agent stack do not all have the same availability status. The most reliable way to evaluate the network is to separate its current EVM foundation from upcoming Launchpad capabilities and its published compute roadmap.
Figure 1. A status-aware view of BOT Chain’s AI agent infrastructure. Current public foundations are separated from upcoming and roadmap items. Source review: August 3, 2026.
Status note: A roadmap date is not proof that a feature is available in production. Before publishing a developer claim or deploying a dependency, verify the current product page, release notes and Developer Docs.
Layer
Public evidence
Status used in this article
What developers should assume
Identity
Official BOT Chain posts say Launchpad V1 will support ERC-8004.
Upcoming
Do not describe ERC-8004 agent identity as live until release documentation confirms it.
Compute
The website presents DePIN compute architecture and lists vCompute and compute-node activation in its roadmap.
Published roadmap
Do not infer that a public compute marketplace or on-chain model runtime is available without current product documentation.
Execution and policy
BOT Chain supports EVM smart contracts, while application-specific permissions and transaction controls remain the developer’s responsibility. Planned ERC-4337 support belongs to Launchpad V1.
Current EVM execution / upcoming account infrastructure
Smart-contract execution is available today, but agent-specific wallets, delegation and policy controls should not be treated as released products.
Settlement
Developer Docs publish EVM compatibility, mainnet and testnet RPC resources, deployment guidance and Explorer access.
Current documented foundation
Developers can evaluate the chain as an EVM execution and settlement environment using the published resources.
Identity: a verifiable reference before an agent can transact
An agent needs more than a name or wallet address. Other applications may need to discover its service endpoint, confirm who controls it and associate interactions with a persistent record. ERC-8004 is a draft Ethereum standards-track proposal for agent discovery, identity, reputation and validation across organizational boundaries.
BOT Chain has announced that AI Agent Launchpad V1 will support ERC-8004. That statement is forward-looking: Launchpad V1 is described as coming soon, so this article does not present ERC-8004 registration as a currently released BOT Chain feature. The relevant implementation details, registry addresses and developer workflow should be taken from the eventual release documentation.
For builders, the practical lesson is to keep identity separate from authorization. A discoverable agent profile can help counterparties find and assess an agent, but it should not automatically grant the agent unrestricted control over assets. Identity answers “which agent is this?” Policy answers “what may it do?” Those are related questions, not interchangeable controls.
Compute: coordinate resources without putting the whole model on-chain
AI workloads usually depend on GPUs, CPUs, storage, model endpoints and private application data. Recording every inference step on a general-purpose blockchain would often be unnecessary, expensive or incompatible with privacy requirements. A more defensible architecture keeps model execution off-chain while using blockchain records for commitments, permissions, payments and results that need shared verification.
BOT Chain’s official website outlines a roadmap for vCompute and decentralized compute coordination, including compute-node activation. These references describe the published compute roadmap; they do not, by themselves, establish that every planned compute service is publicly available. Developers should look for current node specifications, APIs, service terms and verifiable job-result formats before treating a compute layer as an application dependency.
This separation also prevents a common category error: decentralized compute is not the same thing as on-chain settlement. Compute produces an output. Settlement determines which state change or payment is accepted. A production design needs an explicit bridge between the two—for example, an authenticated result, a verification rule and a transaction that records the accepted outcome.
Execution and settlement: the current public foundation
The clearest currently documented part of the stack is BOT Chain’s EVM execution environment. The Developer Documentation currently presents BOT Chain as an EVM-compatible Layer 1, while the project’s latest positioning focuses on AI-native infrastructure for autonomous agents and decentralized value systems. The documentation publishes resources for network configuration, JSON-RPC access, test tokens, contract deployment, verification and node operation. The official website identifies BOT as the native token used for on-chain gas, while BOT Explorer exposes transactions, addresses, contracts and network activity.
Because the network exposes familiar EVM interfaces, teams can begin with standard smart-contract and RPC workflows rather than waiting for every agent-specific product. The relevant starting points are the BOT Chain Developer Documentation, the Developers section and BOT Explorer.
EVM compatibility is useful, but it does not automatically create safe agent autonomy. Developers still need to define contract-level rules, signer custody, transaction limits, failure handling, monitoring and human override paths. BOT Chain has also announced planned ERC-4337 support within AI Agent Launchpad V1. That should be treated as upcoming product direction, not assumed production account infrastructure, until technical release materials are available.
A practical agent-to-settlement workflow
The following workflow is an architecture pattern, not a claim that every step is already packaged as a BOT Chain product. It shows how teams can combine current EVM infrastructure with application-layer controls today, while leaving clear integration points for future Launchpad capabilities.
Step 1: Define the task and trust boundary
Specify what the agent may decide, which data it may access, the maximum value at risk and which actions require human approval. Keep private prompts, credentials and sensitive data outside public transaction payloads.
Step 2: Attach identity without confusing it with authority
Use an application identity today and plan a migration path if Launchpad V1 releases ERC-8004 registration. Treat the identity record as a reference for discovery and reputation, not as blanket permission to spend or change contracts.
Step 3: Run the model and tools off-chain
Execute inference, retrieval and external API calls in the environment that matches the application’s latency, privacy and cost requirements. Capture only the commitments or results that another party must verify.
Step 4: Enforce policy before submission
Validate contract addresses, function selectors, amounts, deadlines and rate limits. Reject actions that fall outside the approved policy, and retain a review path for ambiguous or high-impact decisions.
Step 5: Submit and verify on BOT Chain
Use the documented RPC interface to submit the authorized transaction. Confirm the receipt, contract events and resulting state through BOT Explorer or a directly queried RPC endpoint. Your application should define what happens when the transaction reverts, is delayed or produces an unexpected state.
What developers can evaluate now
Teams do not need to wait for the full agent roadmap to validate the settlement layer. A practical proof of concept can connect an EVM toolchain to BOT Chain, use the published mainnet or testnet configurat…
【参考回答-中文】
原文见：https://www.botchain.ai/en/blog/ai-agent-infrastructure-bot-chain
【来源】https://www.botchain.ai/en/blog/ai-agent-infrastructure-bot-chain

---

## What Is an AI-Native Blockchain? A Practical Introduction to BOT Chain

Source: https://www.botchain.ai/en/blog/what-is-an-ai-native-blockchain

【相关问题】What Is an AI-Native Blockchain? A Practical Introduction to BOT Chain / blog what-is-an-ai-native-blockchain
【关键词】blog;AI Agent;AI-native;基础设施;BOT Chain
【参考回答-英文】
Back to BlogWhat Is an AI-Native Blockchain? A Practical Introduction to BOT Chain
An AI-native blockchain is designed to give autonomous software the accounts, policies, execution, settlement and auditability required to act safely on-chain.
BC
BOT Chain Editorial Team
Aug 3, 20268 min read
Copy linkShare
AI-native infrastructure is not a blockchain with an AI label. It is a network designed so autonomous software can hold permissions, execute transactions, settle value and leave an auditable record.
An AI-native blockchain is a programmable settlement and coordination layer built for AI agents as active participants. It gives software-controlled actors a way to use accounts, follow spending and access policies, call smart contracts, pay for services, verify outcomes and create an on-chain history that other systems can inspect.
The distinction matters because an AI model can generate a decision, but it cannot create economic trust by itself. The moment an agent is allowed to purchase compute, move a token, trigger a contract or pay another machine, the application needs enforceable boundaries and a reliable record of what happened. That is the role of blockchain infrastructure.
BOT Chain is an EVM-compatible, AI-native Layer 1 blockchain designed for autonomous AI agents and decentralized value systems. Its practical value for AI builders begins with familiar Ethereum development workflows, high-performance execution, low transaction costs and transparent on-chain observability.
What makes a blockchain AI-native?
“AI-native blockchain” is still an emerging category rather than a single formal standard. A useful definition therefore starts with the workload, not the label. AI agents operate continuously, make decisions at software speed, interact with APIs and services, and may need to transact without a human approving every step. Infrastructure for those agents must support autonomy while keeping that autonomy bounded.
A general-purpose chain can host an AI-related smart contract. An AI-native blockchain goes further: its network, account model, developer interfaces and surrounding infrastructure are organized around machine-driven execution and verification. In practice, six capabilities determine whether a blockchain is ready for AI agent applications.
Figure 1. The six-part AI-native blockchain readiness framework.
The capabilities AI agents require
Capability
What the agent needs
Why it matters
Identity and policy
An account plus rules for who or what may act
Autonomy needs a clear authority boundary.
Execution
Deterministic smart-contract calls and transaction receipts
Intent must become an enforceable state change.
Settlement
Predictable fees and timely finality
Agents need to know when an action is complete.
Verification
Observable state, logs and transaction history
Other agents and applications must be able to check outcomes.
Compute coordination
A way to request, account for or settle external resources
Most AI inference remains off-chain, but access and payment can be coordinated on-chain.
Developer compatibility
Stable RPC access, developer documentation and familiar EVM tooling
Builders need to ship and maintain agent applications efficiently.
These capabilities form a general framework for evaluating AI-native blockchain infrastructure. They should not be interpreted as features currently available on every network discussed in this article.
Why conventional blockchain design can fall short
Most blockchain user experiences were designed around people opening a wallet, reviewing a prompt and approving one transaction at a time. That model becomes awkward when software is expected to act repeatedly, respond to changing conditions and purchase services on demand.
Three constraints appear quickly. First, a wallet with unrestricted authority creates unacceptable risk. Second, slow or unpredictable settlement makes it difficult for an agent to decide whether to continue a workflow. Third, forcing every user or agent to acquire a native token before taking a small action introduces operational friction. AI-native design addresses these constraints with explicit policies, faster confirmation, programmable fee handling and better observability.
It is equally important to be precise about what belongs on-chain. Large language model inference and other compute-heavy tasks usually remain off-chain. The chain is most valuable as the trust layer around those tasks: recording authorization, coordinating access, settling payment and anchoring a result or receipt that can be checked later.
How BOT Chain fits the AI-native model
1. An EVM-compatible development environment
BOT Chain is an EVM-compatible, AI-native Layer 1 blockchain designed for autonomous AI agents and decentralized value systems. Developers can use familiar Ethereum tools and workflows to deploy smart contracts and build decentralized applications without rebuilding their entire development stack.
The BOT Chain developer environment provides mainnet and testnet RPC access, test tokens, contract deployment resources and on-chain verification tools. Developers can begin with the BOT Chain Quick Guide.
2. High-performance on-chain execution
BOT Chain uses the SPoA consensus mechanism to support efficient block production and network coordination. The network currently delivers an average block time of approximately 0.7 seconds, peak throughput exceeding 10,000 TPS and transaction fees typically below $0.01. This execution environment is designed to support frequent, automated and low-value interactions across AI agent and Web3 applications.
3. Transparent network infrastructure
BOT Explorer provides access to transactions, blocks, addresses, tokens and verified contracts. BOT Bridge, BDEX and Bo Wallet further connect network access, cross-chain assets, liquidity and user interaction across the BOT Chain ecosystem.
Builders can inspect live network records through BOT Explorer and review the wider network through the BOT Chain ecosystem pages.
4. An expanding AI agent roadmap
BOT Chain is developing AI Agent Launchpad V1 to extend its Layer 1 infrastructure with agent creation, on-chain identity, smart-account capabilities and native asset issuance. Planned support for ERC-8004 and ERC-4337 is intended to provide stronger identity and account infrastructure for autonomous applications.
These capabilities are upcoming and should not be interpreted as currently released products until the relevant official launch and documentation are published.
5. AI agent and DePIN ecosystem development
BOT Chain continues to expand across AI agent and DePIN use cases, exploring how blockchain infrastructure can connect autonomous applications, physical resources and on-chain value settlement. Compute-intensive workloads can remain off-chain, while authorization, payments and verifiable records can be anchored on-chain.
A practical workflow for AI builders
Step 1: Define the agent’s authority boundary
Write down what the agent may do, which contracts it may call, the maximum value per action, the maximum value per period and which operations always require human approval. This policy should exist before the agent receives a funded account.
Step 2: Choose the account and fee model
Decide whether the application will use an EOA, a smart-contract account, an MPC-controlled wallet or another custody pattern. Then decide who pays gas. If sponsorship is appropriate, define eligibility rules and a fallback path rather than treating “gasless” as an unconditional promise.
Step 3: Connect, test and observe
Use the testnet RPC and faucet to validate the transaction lifecycle. Record the request, policy decision, signature, transaction hash, receipt and final state. Test rejected actions as carefully as successful ones; policy failures and network errors are part of the production workflow.
Step 4: Match confirmation requirements to risk
Create confirmation rules by transaction class. Low-value, reversible actions may continue after a short confirmation window. High-value or irreversible actions should require stronger settlement assurance and may need additional approval. An AI-native application is not one that removes every human decision; it is one that makes the remaining decisions explicit.
Step 5: Monitor the complete economic loop
Measure more than transaction success. Track transaction cost, failed policies, confirmation time, contract errors, agent retries and the value delivered by the external service. These signals show whether the system is economical and safe enough to scale.
What an AI-native blockchain does not mean
It does not mean putting an entire AI model on-chain. It does not mean allowing a model to spend without limits. It does not mean that high TPS alone makes a network suitable for agents. And it does not replace application-level security, model evaluation or operational monitoring.
The most credible AI-native systems combine machine autonomy with bounded authority. Blockchain contributes shared state, programmable settlement and auditability; the application contributes model logic, business rules, user experience and risk controls. Both sides are necessary.
Frequently asked questions
Is an AI-native blockchain different from an AI project deployed on a blockchain?
Yes. An AI project may simply store a token or contract on a general-purpose chain. AI-native infrastructure is designed around recurring machine actions, permissions, settlement, verification and resource coordination.
Do AI models need to run on-chain?
Usually not. Inference can remain off-chain while the blockchain manages authorization, payment, receipts and verifiable state. This division keeps compute practical while preserving a shared trust layer.
Why does EVM compatibility matter for AI developers?
It allows teams to use established smart-contract languages, libraries, wallets and development tools. That shortens the path from an agent prototype to a testable on-chain app…
【参考回答-中文】
原文见：https://www.botchain.ai/en/blog/what-is-an-ai-native-blockchain
【来源】https://www.botchain.ai/en/blog/what-is-an-ai-native-blockchain

