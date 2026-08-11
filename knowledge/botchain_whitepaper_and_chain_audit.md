# BOT Chain Whitepaper & Chain Audit

Synced: 2026-08-09

---

## BOT Chain Whitepaper

Source: https://media.botchain.ai/media/docs/bot-chain-whitepaper.pdf

【相关问题】BOT Chain 白皮书在哪里？ / Where is the BOT Chain whitepaper？ / whitepaper 下载
【关键词】白皮书;whitepaper;PDF;media.botchain.ai
【参考回答-中文】
BOT Chain 官方白皮书（PDF）：https://media.botchain.ai/media/docs/bot-chain-whitepaper.pdf
也可从媒体中心入口获取：https://media.botchain.ai/media
说明：该 PDF 主要为版式/图像排版，文本层不可直接抽取；对外引用请以 PDF 原文与官方渠道为准。前瞻性路线图内容仅在官方渠道发布后视为正式承诺。
白皮书主题方向（结合官网与公开材料）：BOT Chain 定位为面向 AI Agent、DePIN、可验证计算与协议经济的高性能 EVM 兼容 Layer 1；强调 AI 原生基础设施、身份/算力/结算等能力，以及生态建设与开发者接入。
【参考回答-英文】
Official BOT Chain whitepaper (PDF): https://media.botchain.ai/media/docs/bot-chain-whitepaper.pdf
Media hub: https://media.botchain.ai/media
Note: the PDF is primarily layout/image-based and does not expose a reliable text layer for extraction. Cite the PDF and official channels. Treat forward-looking roadmap items as commitments only after official publication.
Public positioning: high-performance EVM-compatible Layer 1 for AI Agents, DePIN, verifiable computing, and the protocol economy, with AI-native infrastructure themes (identity, compute, settlement) and builder/ecosystem access.
【来源】https://media.botchain.ai/media/docs/bot-chain-whitepaper.pdf

---

## BOT Chain Audit Report (CertiK) — Chain.pdf

Source: https://www.botchain.ai/docs/Chain.pdf

【相关问题】BOT Chain 链审计报告在哪里？ / Where is the BOT Chain audit report？ / Chain.pdf CertiK
【关键词】审计;CertiK;Chain.pdf;安全报告
【参考回答-中文】
BOT Chain 链审计报告（公开 PDF）：https://www.botchain.ai/docs/Chain.pdf
相关安全入口：CertiK Skynet https://skynet.certik.com/projects/botchain ；另有 DEX/Bridge 审计报告可在官方产品页查阅。
以下为 PDF 文本摘录（完整内容以原文件为准）：

--- page 1 ---
CertiK Assessed on Feb 23rd, 2026
BOT Chain - Chain
P r e l i m i n a r y  C o m m e n t s

--- page 2 ---
Executive Summary
Vulnerability Summary
3 Centralization 3 Acknowledged
Centralization findings highlight privileged roles &
functions and their capabilities, or instances where the
project takes custody of users’ assets.
0 Critical
Critical risks are those that impact the safe functioning of
a platform and must be addressed before launch. Users
should not invest in any project with outstanding critical
risks.
0 Major
Major risks may include logical errors that, under specific
circumstances, could result in fund losses or loss of
project control.
0 Medium
Medium risks may not pose a direct risk to users’ funds,
but they can affect the overall functioning of a platform.
2 Minor 2 Acknowledged
Minor risks can be any of the above, but on a smaller
scale. They generally do not compromise the overall
integrity of the project, but they may be less efficient than
other solutions.
3 Informational 3 Resolved
Informational errors are often recommendations to
improve the style of the code or certain operations to fall
within industry best practices. They usually do not affect
the overall functioning of the code.
0 Discussion The impact of the issue is yet to be determined, hence
requires further clarifications from the project team.
SUMMARY BOT CHAIN - CHAIN
CertiK Assessed on Feb 23rd, 2026
BOT Chain - Chain
These preliminary comments were prepared by CertiK.
TYPES
DEX, Staking
ECOSYSTEM
Binance Smart Chain
(BSC)
METHODS
Manual Review, Static Analysis
LANGUAGE
Solidity
TIMELINE
Preliminary comments published on 02/09/2026
8
Total Findings
3
Resolved
0
Partially Resolved
5
Acknowledged
0
Declined
0
Pending

--- page 3 ---
TABLE OF CONTENTS BOT CHAIN - CHAIN
Summary
Executive Summary
Vulnerability Summary
Codebase
Audit Scope
Approach & Methods
System Overview
BOT Staking & Chain Governance (BSC Fork)
Review Notes
Out‑of‑Scope Dependencies
Testing & Documentation
Code Completeness
Findings
BCC-01 : Hidden Privileged Role In `SystemV2`
BCC-02 : Centralized Control Of Contract Upgrade
BCC-03 : Centralizatio Risks
BCC-04 : Missing Zero Address Validation
BCC-05 : Potential Cross-Chain Replay Attack With Merkle Proofing Mechanism
BCC-06 : Contracts With Todos
BCC-07 : Inconsistency Between Comment And Code
BCC-08 : Commented Out Code
Appendix
Disclaimer
TABLE OF CONTENTS BOT CHAIN - CHAIN

--- page 4 ---
CODEBASE BOT CHAIN - CHAIN
Repository
Private Repo
CODEBASE BOT CHAIN - CHAIN

--- page 5 ---
AUDIT SCOPE BOT CHAIN - CHAIN
CertiKProject/certik-audit-projects
BSCGovernor.sol
BSCValidatorSet.sol
SlashIndicator.sol
StakeHub.sol
System.sol
AUDIT SCOPE BOT CHAIN - CHAIN

--- page 6 ---
APPROACH & METHODS BOT CHAIN - CHAIN
This audit was conducted for BOT Chain to evaluate the security and correctness of the smart contracts associated with the
BOT Chain - Chain project. The assessment included a comprehensive review of the in-scope smart contracts. The audit
was performed using a combination of Manual Review and Static Analysis.
The review process emphasized the following areas:
Architecture review and threat modeling to understand systemic risks and identify design-level flaws.
Identification of vulnerabilities through both common and edge-case attack vectors.
Manual verification of contract logic to ensure alignment with intended design and business requirements.
Dynamic testing to validate runtime behavior and assess execution risks.
Assessment of code quality and maintainability, including adherence to current best practices and industry standards.
The audit resulted in findings categorized across multiple severity levels, from informational to critical. To enhance the
project’s security and long-term robustness, we recommend addressing the identified issues and considering the following
general improvements:
Improve code readability and maintainability by adopting a clean architectural pattern and modular design.
Strengthen testing coverage, including unit and integration tests for key functionalities and edge cases.
Maintain meaningful inline comments and documentations.
Implement clear and transparent documentation for privileged roles and sensitive protocol operations.
Regularly review and simulate contract behavior against newly emerging attack vectors.
APPROACH & METHODS BOT CHAIN - CHAIN

--- page 7 ---
SYSTEM OVERVIEW BOT CHAIN - CHAIN
The BOT Chain audit covers a chain governance and staking suite based on BSC chain.
BOT Staking & Chain Governance (BSC Fork)
The chain governance suite includes System , StakeHub , BSCValidatorSet , SlashIndicator , and BSCGovernor .
Note that for this part, only the differences between the BOT chain contracts and the bsc-genesis-contract  have
been audited.
System  defines fixed system addresses and core access-control modifiers for consensus, cross-chain, slashing, and
governance actors.
StakeHub  manages validator creation, delegation, redelegation, unbonding, and slashing-related parameters.
BSCValidatorSet  maintains the active validator set, handles fee distribution and maintenance state, and integrates with
system reward logic.
SlashIndicator  tracks validator downtime and malicious behavior, enforces slash thresholds, and signals
felony/misdemeanor events.
BSCGovernor  is an OpenZeppelin Governor-based governance module with a timelock, proposal threshold/quorum
rules, and a whitelist of targets.
SYSTEM OVERVIEW BOT CHAIN - CHAIN

--- page 8 ---
REVIEW NOTES BOT CHAIN - CHAIN
Out‑of‑Scope Dependencies
The codebase contains multiple components and dependencies that were not fully covered by this assessment. In particular:
Parts of the repository are forked or derived from upstream projects (e.g., Uniswap V3 core/periphery). Components
that were not explicitly in scope and/or appear unchanged from upstream were treated as external dependencies and
assumed to behave as specified by their original maintainers.
Third‑party libraries and build tooling were not audited comprehensively. Any security properties of the development
toolchain are outside the scope of this report.
The security of external contracts and external systems interacted with by the reviewed contracts (e.g., ERC‑20
tokens, WETH, bridge operators/relayers, off‑chain signing infrastructure, governance processes, and key management)
is out of scope. These elements were treated as operational assumptions unless the contract enforces the relevant
security guarantees on‑chain.
Our review focused on the on‑chain behavior of the in‑scope Solidity contracts within the defined scope.
Testing & Documentation
The repository includes automated tests and developer tooling, particularly around the Uniswap‑derived components.
However, overall integration and edge‑case coverage appears limited across the full system, especially when
considering cross‑component behavior (e.g., bridge flows, privileged operations, and configuration correctness).
We recommend expanding test coverage to include stress scenarios and failure modes (e.g., misconfiguration, unexpected
inputs, privilege/role transitions, and revert‑path behavior). On the documentation front, inline comments exist, but
higher‑level documentation is limited. Adding concise system‑level documentation (architecture and operational
assumptions) would improve maintainability and reduce misconfiguration risk.
Code Completeness
We noticed several TODO /FIXME  comments remaining in the codebase. These markers may indicate incomplete
hardening work, deferred changes, or leftover development notes. We recommend triaging these items by resolving or
removing outdated TODO/FIXME notes and re-reviewing any security-relevant logic added or modified as a result.
REVIEW NOTES BOT CHAIN - CHAIN

--- page 9 ---
FINDINGS BOT CHAIN - CHAIN
This report has been prepared for BOT Chain to identify potential vulnerabilities and security issues within the reviewed
codebase. During the course of the audit, a total of 8 issues were identified. Leveraging a combination of Manual Review &
Static Analysis the following findings were uncovered:
ID Title Category Severity Status
BCC-01Hidden Privileged Role In SystemV2 CentralizationCentralization Acknowledged
BCC-02Centralized Control Of Contract Upgrade CentralizationCentralization Acknowledged
BCC-03Centralizatio Risks CentralizationCentralization Acknowledged
BCC-04 Missing Zero Address Validation Volatile Code Minor Acknowledged
BCC-05 Potential Cross-Chain Replay Attack With
Merkle Proofing Mechanism Design Issue Minor Acknowledged
BCC-06 Contracts With Todos Coding Issue Informational Resolved
BCC-07 Inconsistency Between Comment And Code Inconsistency Informational Resolved
BCC-08 Commented Out Code Coding Style Informational Resolved
FINDINGS BOT CHAIN - CHAIN
8
Total Findings
0
Critical
3
Centralization
0
Major
0
Medium
2
Minor
3
Informational
0
Discussion

--- page 10 ---
BCC-01 Hidden Privileged Role In SystemV2
Category Severity Location Status
Centralization CentralizationSystemV2.sol (base): 51, 56, 61, 66, 71, 76, 81 Acknowledged
Description
SystemV2  restricts certain functions to predefined system contract addresses (e.g., GovHub, Slash, StakeHub) by checking
msg.sender . However, these system addresses are declared as internal constant  and are not exposed via public
getter functions, which may reduce transparency and cause confusion for integrators/users relying on the ABI.
Recommendation
Change the visibility of the private role or add the getter  function to clarify the transparency or clarify the intended
behavior.
Alleviation
[BOT Chain, 02/23/2026]: The team acknowledged this issue.
[CertiK, 02/23/2026]: It is suggested to implement the aforementioned methods to avoid centralized failure. Also, CertiK
strongly encourages the project team to periodically revisit the private key security management of all addresses related to
centralized roles.
BCC-01 BOT CHAIN - CHAIN

--- page 11 ---
BCC-02 Centralized Control Of Contract Upgrade
Category Severity Location Status
Centralization Centralization
BSCGovernor.sol (base): 17; BSCTimelock.sol (ba
se): 9; GovToken.sol (base): 12; StakeCredit.sol (b
ase): 12; TokenRecoverPortal.sol (base): 21
Acknowledged
Description
In the contracts BSCGovernor , BSCTimelock , GovToken , StakeCredit , and TokenRecoverPortal , the privileged
account proxy admin  has the authority to update the implementation contract behind the upgradeable proxy.
Any compromise of the proxy admin  may allow a hacker to upgrade the proxy to a malicious implementation, thereby
changing contract logic and potentially enabling arbitrary minting, fund draining, censorship of governance actions, or other
malicious behaviors depending on the upgraded implementation.
Recommendation
We recommend that the team make efforts to restrict access to the admin of the proxy contract. A strategy of combining a
time-lock and a multi-signature ( ⅔ , ⅗ ) wallet can be used to prevent a single point of failure due to a private key
compromise. In addition, the team should be transparent and notify the community in advance whenever they plan to migrate
to a new implementation contract.
Here are some feasible short-term and long-term suggestions that would mitigate the potential risk to a different level and
suggestions that would permanently fully resolve the risk.
Short Term:
A combination of a time-lock and a multi signature ( ⅔ , ⅗ ) wallet mitigate the risk by delaying the sensitive operation and
avoiding a single point of key management failure.
A time-lock with reasonable latency, such as 48 hours, for awareness of privileged operations;
AND
Assignment of privileged roles to multi-signature wallets to prevent a single point of failure due to a private key
compromised;
AND
A medium/blog link for sharing the time-lock contract and multi-signers addresses information with the community.
For remediation and mitigated status, please provide the following information:
Provide the deployed time-lock address.
Provide the gnosis address with ALL the multi-signer addresses for the verification process.
BCC-02 BOT CHAIN - CHAIN

--- page 12 ---
Provide a link to the medium/blog with all of the above information included.
Long Term:
A combination of a time-lock on the contract upgrade operation and a DAO for controlling the upgrade operation mitigate the
contract upgrade risk by applying transparency and decentralization.
A time-lock with reasonable latency, such as 48 hours, for community awareness of privileged operations;
AND
Introduction of a DAO, governance, or voting module to increase decentralization, transparency, and user involvement;
AND
A medium/blog link for sharing the time-lock contract, multi-signers addresses, and DAO information with the community.
For remediation and mitigated status, please provide the following information:
Provide the deployed time-lock address.
Provide the gnosis address with ALL the multi-signer addresses for the verification process.
Provide a link to the medium/blog with all of the above information included.
Permanent:
Renouncing ownership of the admin  account or removing the upgrade functionality can fully resolve the risk.
Renounce the ownership and never claim back the privileged role;
OR
Remove the risky functionality.
Note: we recommend the project team consider the long-term solution or the permanent solution. The project team shall
make a decision based on the current state of their project, timeline, and project resources.
Alleviation
[BOT Chain, 02/23/2026]: The team acknowledged this issue.
[CertiK, 02/23/2026]: It is suggested to implement the aforementioned methods to avoid centralized failure. Also, CertiK
strongly encourages the project team to periodically revisit the private key security management of all addresses related to
centralized roles.
BCC-02 BOT CHAIN - CHAIN

--- page 13 ---
BCC-03 Centralizatio Risks
Category Severity Location Status
Centralization Centralization
BSCGovernor.sol (base): 171; BSCTimelock.sol (b
ase): 31; BSCValidatorSet.sol (base): 168, 175, 179,
521, 602; GovHub.sol (base): 21, 29, 34, 38; GovTo
ken.sol (base): 50, 59, 71; SlashIndicator.sol (bas
e): 90, 97, 101, 137, 193, 315, 357; StakeCredit.sol
(base): 73, 85, 103, 114, 136, 151, 188, 211; System
Reward.sol (base): 42, 63; TokenHub.sol (base): 10
6, 113, 130, 141, 154, 190, 201, 238, 300, 304; Token
RecoverPortal.sol (base): 243
Acknowledged
Description
In the contract BSCGovernor , the role GOV_HUB_ADDR  has authority over the functions shown in the diagram below. Any
compromise to the GOV_HUB_ADDR  account may allow the hacker to take advantage of this authority and change critical
governance parameters (e.g., voting delay/period, proposal threshold, quorum) and the governor protector.
BCC-03 BOT CHAIN - CHAIN

--- page 14 ---
Authenticated Role Function
Internal Calls
External Calls
External Calls
Internal Calls
Internal Calls
Internal Calls
External Calls
External Calls
Internal Calls
Internal Calls
GOV_HUB_ADDR updateParam
_setVotingDelay
value.bytesToAddress
key.compareStrings
_updateQuorumNumerator
_setProtector
_setVotingPeriod
value.bytesToUint64
value.bytesToUint256
_setProposalThreshold
_setLateQuorumVoteExtension
BCC-03 BOT CHAIN - CHAIN

--- page 15 ---
In the contract BSCTimelock , the role GOV_HUB_ADDR  has authority over the functions shown in the diagram below. Any
compromise to the GOV_HUB_ADDR  account may allow the hacker to take advantage of this authority and change the
timelock minimum delay (e.g., reduce the delay).
Authenticated Role Function
External Calls
External Calls
Internal Calls
GOV_HUB_ADDR updateParam
value.bytesToUint256
key.compareStrings
updateDelay
In the contract BSCValidatorSet , the role CROSS_CHAIN_CONTRACT_ADDR  has authority over the functions shown in the
diagram below. Any compromise to the CROSS_CHAIN_CONTRACT_ADDR  account may allow the hacker to take advantage of
this authority and call cross-chain handler entrypoints (which are deprecated and revert in this version).
Authenticated Role
Function
Function
Function
CROSS_CHAIN_CONTRACT_ADDR
handleFailAckPackage
handleAckPackage
handleSynPackage
In the contract BSCValidatorSet , the role GOV_HUB_ADDR  has authority over the functions shown in the diagram below.
Any compromise to the GOV_HUB_ADDR  account may allow the hacker to take advantage of this authority and change critical
consensus and fee-distribution parameters (e.g., burn ratio, cabinet size, gas treasury settings).
BCC-03 BOT CHAIN - CHAIN

--- page 16 ---
Function
State Variables
External Calls
External Calls
External Calls
External Calls
External Calls
External Calls
External Calls
Authenticated Role
External Calls
External Calls
updateParam
maxNumOfCandidates
maintainSlashScale
burnRatio
systemRewardAntiMEVRatio
numOfCabinets
maxNumOfWorkingCandidates
systemRewardBaseRatio
maxNumOfMaintaining
turnLength
Memory.compareStrings
newSystemRewardBaseRatio.add
newSystemRewardAntiMEVRatio.add
newGasTreasuryRatio.add
newBurnRatio.add
BytesToTypes.bytesToUint256
.add
IStakeHub.maxElectedValidators
abi.decode
GOV_HUB_ADDR
BCC-03 BOT CHAIN - CHAIN

--- page 17 ---
In the contract BSCValidatorSet , the role SLASH_CONTRACT_ADDR  has authority over the functions shown in the diagram
below. Any compromise to the SLASH_CONTRACT_ADDR  account may allow the hacker to take advantage of this authority and
arbitrarily misdemeanor/felony slash (jail/remove) validators.
Function
Internal Calls
Function State Variables
Internal Calls
Authenticated Role
Internal Calls
Internal Calls
misdemeanor
_misdemeanor
_enterMaintenance
canEnterMaintenance
felony numOfMaintaining
_felony
SLASH_CONTRACT_ADDR
In the contract BSCValidatorSet , the role STAKE_HUB_ADDR  has authority over the functions shown in the diagram below.
Any compromise to the STAKE_HUB_ADDR  account may allow the hacker to take advantage of this authority and trigger
felony slashing/removal of validators.
Function
State Variables
Internal Calls
Authenticated Role
Function
felony
numOfMaintaining
_felony
STAKE_HUB_ADDR
removeTmpMigratedValidator
In the contract GovHub , the role CROSS_CHAIN_CONTRACT_ADDR  has authority over the functions shown in the diagram
below. Any compromise to the CROSS_CHAIN_CONTRACT_ADDR  account may allow the hacker to take advantage of this
authority and call cross-chain handler entrypoints (which are deprecated and revert in this version).
BCC-03 BOT CHAIN - CHAIN

--- page 18 ---
Authenticated Role
Function
Function
Function
CROSS_CHAIN_CONTRACT_ADDR
handleFailAckPackage
handleAckPackage
handleSynPackage
In the contract GovHub , the role TIMELOCK_ADDR  has authority over the functions shown in the diagram below. Any
compromise to the TIMELOCK_ADDR  account may allow the hacker to take advantage of this authority and push arbitrary
updateParam(...)  calls to system contracts via GovHub.updateParam(...) .
Authenticated Role Function
Internal Calls
Internal Calls
TIMELOCK_ADDR updateParam
ParamChangePackage
notifyUpdates
In the contract GovToken , the role STAKE_HUB_ADDR  has authority over the functions shown in the diagram below. Any
compromise to the STAKE_HUB_ADDR  account may allow the hacker to take advantage of this authority and mint/burn
govBNB  (via sync ) and delegate votes.
BCC-03 BOT CHAIN - CHAIN

--- page 19 ---
Authenticated Role
Function
Function
Internal Calls
Function
Internal Calls
STAKE_HUB_ADDR
delegateVote
sync
syncBatch
_delegate
_sync
In the contract SlashIndicator , the role CROSS_CHAIN_CONTRACT_ADDR  has authority over the functions shown in the
diagram below. Any compromise to the CROSS_CHAIN_CONTRACT_ADDR  account may allow the hacker to take advantage of
this authority and call cross-chain handler entrypoints (which are deprecated and revert in this version).
Authenticated Role
Function
Function
Function
CROSS_CHAIN_CONTRACT_ADDR
handleSynPackage
handleFailAckPackage
handleAckPackage
In the contract SlashIndicator , the role GOV_HUB_ADDR  has aut

【参考回答-英文】
BOT Chain audit report (public PDF): https://www.botchain.ai/docs/Chain.pdf
Also see CertiK Skynet: https://skynet.certik.com/projects/botchain. DEX/Bridge audit PDFs are available from official product pages.
PDF text excerpt (full content is in the original file):

--- page 1 ---
CertiK Assessed on Feb 23rd, 2026
BOT Chain - Chain
P r e l i m i n a r y  C o m m e n t s

--- page 2 ---
Executive Summary
Vulnerability Summary
3 Centralization 3 Acknowledged
Centralization findings highlight privileged roles &
functions and their capabilities, or instances where the
project takes custody of users’ assets.
0 Critical
Critical risks are those that impact the safe functioning of
a platform and must be addressed before launch. Users
should not invest in any project with outstanding critical
risks.
0 Major
Major risks may include logical errors that, under specific
circumstances, could result in fund losses or loss of
project control.
0 Medium
Medium risks may not pose a direct risk to users’ funds,
but they can affect the overall functioning of a platform.
2 Minor 2 Acknowledged
Minor risks can be any of the above, but on a smaller
scale. They generally do not compromise the overall
integrity of the project, but they may be less efficient than
other solutions.
3 Informational 3 Resolved
Informational errors are often recommendations to
improve the style of the code or certain operations to fall
within industry best practices. They usually do not affect
the overall functioning of the code.
0 Discussion The impact of the issue is yet to be determined, hence
requires further clarifications from the project team.
SUMMARY BOT CHAIN - CHAIN
CertiK Assessed on Feb 23rd, 2026
BOT Chain - Chain
These preliminary comments were prepared by CertiK.
TYPES
DEX, Staking
ECOSYSTEM
Binance Smart Chain
(BSC)
METHODS
Manual Review, Static Analysis
LANGUAGE
Solidity
TIMELINE
Preliminary comments published on 02/09/2026
8
Total Findings
3
Resolved
0
Partially Resolved
5
Acknowledged
0
Declined
0
Pending

--- page 3 ---
TABLE OF CONTENTS BOT CHAIN - CHAIN
Summary
Executive Summary
Vulnerability Summary
Codebase
Audit Scope
Approach & Methods
System Overview
BOT Staking & Chain Governance (BSC Fork)
Review Notes
Out‑of‑Scope Dependencies
Testing & Documentation
Code Completeness
Findings
BCC-01 : Hidden Privileged Role In `SystemV2`
BCC-02 : Centralized Control Of Contract Upgrade
BCC-03 : Centralizatio Risks
BCC-04 : Missing Zero Address Validation
BCC-05 : Potential Cross-Chain Replay Attack With Merkle Proofing Mechanism
BCC-06 : Contracts With Todos
BCC-07 : Inconsistency Between Comment And Code
BCC-08 : Commented Out Code
Appendix
Disclaimer
TABLE OF CONTENTS BOT CHAIN - CHAIN

--- page 4 ---
CODEBASE BOT CHAIN - CHAIN
Repository
Private Repo
CODEBASE BOT CHAIN - CHAIN

--- page 5 ---
AUDIT SCOPE BOT CHAIN - CHAIN
CertiKProject/certik-audit-projects
BSCGovernor.sol
BSCValidatorSet.sol
SlashIndicator.sol
StakeHub.sol
System.sol
AUDIT SCOPE BOT CHAIN - CHAIN

--- page 6 ---
APPROACH & METHODS BOT CHAIN - CHAIN
This audit was conducted for BOT Chain to evaluate the security and correctness of the smart contracts associated with the
BOT Chain - Chain project. The assessment included a comprehensive review of the in-scope smart contracts. The audit
was performed using a combination of Manual Review and Static Analysis.
The review process emphasized the following areas:
Architecture review and threat modeling to understand systemic risks and identify design-level flaws.
Identification of vulnerabilities through both common and edge-case attack vectors.
Manual verification of contract logic to ensure alignment with intended design and business requirements.
Dynamic testing to validate runtime behavior and assess execution risks.
Assessment of code quality and maintainability, including adherence to current best practices and industry standards.
The audit resulted in findings categorized across multiple severity levels, from informational to critical. To enhance the
project’s security and long-term robustness, we recommend addressing the identified issues and considering the following
general improvements:
Improve code readability and maintainability by adopting a clean architectural pattern and modular design.
Strengthen testing coverage, including unit and integration tests for key functionalities and edge cases.
Maintain meaningful inline comments and documentations.
Implement clear and transparent documentation for privileged roles and sensitive protocol operations.
Regularly review and simulate contract behavior against newly emerging attack vectors.
APPROACH & METHODS BOT CHAIN - CHAIN

--- page 7 ---
SYSTEM OVERVIEW BOT CHAIN - CHAIN
The BOT Chain audit covers a chain governance and staking suite based on BSC chain.
BOT Staking & Chain Governance (BSC Fork)
The chain governance suite includes System , StakeHub , BSCValidatorSet , SlashIndicator , and BSCGovernor .
Note that for this part, only the differences between the BOT chain contracts and the bsc-genesis-contract  have
been audited.
System  defines fixed system addresses and core access-control modifiers for consensus, cross-chain, slashing, and
governance actors.
StakeHub  manages validator creation, delegation, redelegation, unbonding, and slashing-related parameters.
BSCValidatorSet  maintains the active validator set, handles fee distribution and maintenance state, and integrates with
system reward logic.
SlashIndicator  tracks validator downtime and malicious behavior, enforces slash thresholds, and signals
felony/misdemeanor events.
BSCGovernor  is an OpenZeppelin Governor-based governance module with a timelock, proposal threshold/quorum
rules, and a whitelist of targets.
SYSTEM OVERVIEW BOT CHAIN - CHAIN

--- page 8 ---
REVIEW NOTES BOT CHAIN - CHAIN
Out‑of‑Scope Dependencies
The codebase contains multiple components and dependencies that were not fully covered by this assessment. In particular:
Parts of the repository are forked or derived from upstream projects (e.g., Uniswap V3 core/periphery). Components
that were not explicitly in scope and/or appear unchanged from upstream were treated as external dependencies and
assumed to behave as specified by their original maintainers.
Third‑party libraries and build tooling were not audited comprehensively. Any security properties of the development
toolchain are outside the scope of this report.
The security of external contracts and external systems interacted with by the reviewed contracts (e.g., ERC‑20
tokens, WETH, bridge operators/relayers, off‑chain signing infrastructure, governance processes, and key management)
is out of scope. These elements were treated as operational assumptions unless the contract enforces the relevant
security guarantees on‑chain.
Our review focused on the on‑chain behavior of the in‑scope Solidity contracts within the defined scope.
Testing & Documentation
The repository includes automated tests and developer tooling, particularly around the Uniswap‑derived components.
However, overall integration and edge‑case coverage appears limited across the full system, especially when
considering cross‑component behavior (e.g., bridge flows, privileged operations, and configuration correctness).
We recommend expanding test coverage to include stress scenarios and failure modes (e.g., misconfiguration, unexpected
inputs, privilege/role transitions, and revert‑path behavior). On the documentation front, inline comments exist, but
higher‑level documentation is limited. Adding concise system‑level documentation (architecture and operational
assumptions) would improve maintainability and reduce misconfiguration risk.
Code Completeness
We noticed several TODO /FIXME  comments remaining in the codebase. These markers may indicate incomplete
hardening work, deferred changes, or leftover development notes. We recommend triaging these items by resolving or
removing outdated TODO/FIXME notes and re-reviewing any security-relevant logic added or modified as a result.
REVIEW NOTES BOT CHAIN - CHAIN

--- page 9 ---
FINDINGS BOT CHAIN - CHAIN
This report has been prepared for BOT Chain to identify potential vulnerabilities and security issues within the reviewed
codebase. During the course of the audit, a total of 8 issues were identified. Leveraging a combination of Manual Review &
Static Analysis the following findings were uncovered:
ID Title Category Severity Status
BCC-01Hidden Privileged Role In SystemV2 CentralizationCentralization Acknowledged
BCC-02Centralized Control Of Contract Upgrade CentralizationCentralization Acknowledged
BCC-03Centralizatio Risks CentralizationCentralization Acknowledged
BCC-04 Missing Zero Address Validation Volatile Code Minor Acknowledged
BCC-05 Potential Cross-Chain Replay Attack With
Merkle Proofing Mechanism Design Issue Minor Acknowledged
BCC-06 Contracts With Todos Coding Issue Informational Resolved
BCC-07 Inconsistency Between Comment And Code Inconsistency Informational Resolved
BCC-08 Commented Out Code Coding Style Informational Resolved
FINDINGS BOT CHAIN - CHAIN
8
Total Findings
0
Critical
3
Centralization
0
Major
0
Medium
2
Minor
3
Informational
0
Discussion

--- page 10 ---
BCC-01 Hidden Privileged Role In SystemV2
Category Severity Location Status
Centralization CentralizationSystemV2.sol (base): 51, 56, 61, 66, 71, 76, 81 Acknowledged
Description
SystemV2  restricts certain functions to predefined system contract addresses (e.g., GovHub, Slash, StakeHub) by checking
msg.sender . However, these system addresses are declared as internal constant  and are not exposed via public
getter functions, which may reduce transparency and cause confusion for integrators/users relying on the ABI.
Recommendation
Change the visibility of the private role or add the getter  function to clarify the transparency or clarify the intended
behavior.
Alleviation
[BOT Chain, 02/23/2026]: The team acknowledged this issue.
[CertiK, 02/23/2026]: It is suggested to implement the aforementioned methods to avoid centralized failure. Also, CertiK
strongly encourages the project team to periodically revisit the private key security management of all addresses related to
centralized roles.
BCC-01 BOT CHAIN - CHAIN

--- page 11 ---
BCC-02 Centralized Control Of Contract Upgrade
Category Severity Location Status
Centralization Centralization
BSCGovernor.sol (base): 17; BSCTimelock.sol (ba
se): 9; GovToken.sol (base): 12; StakeCredit.sol (b
ase): 12; TokenRecoverPortal.sol (base): 21
Acknowledged
Description
In the contracts BSCGovernor , BSCTimelock , GovToken , StakeCredit , and TokenRecoverPortal , the privileged
account proxy admin  has the authority to update the implementation contract behind the upgradeable proxy.
Any compromise of the proxy admin  may allow a hacker to upgrade the proxy to a malicious implementation, thereby
changing contract logic and potentially enabling arbitrary minting, fund draining, censorship of governance actions, or other
malicious behaviors depending on the upgraded implementation.
Recommendation
We recommend that the team make efforts to restrict access to the admin of the proxy contract. A strategy of combining a
time-lock and a multi-signature ( ⅔ , ⅗ ) wallet can be used to prevent a single point of failure due to a private key
compromise. In addition, the team should be transparent and notify the community in advance whenever they plan to migrate
to a new implementation contract.
Here are some feasible short-term and long-term suggestions that would mitigate the potential risk to a different level and
suggestions that would permanently fully resolve the risk.
Short Term:
A combination of a time-lock and a multi signature ( ⅔ , ⅗ ) wallet mitigate the risk by delaying the sensitive operation and
avoiding a single point of key management failure.
A time-lock with reasonable latency, such as 48 hours, for awareness of privileged operations;
AND
Assignment of privileged roles to multi-signature wallets to prevent a single point of failure due to a private key
compromised;
AND
A medium/blog link for sharing the time-lock contract and multi-signers addresses information with the community.
For remediation and mitigated status, please provide the following information:
Provide the deployed time-lock address.
Provide the gnosis address with ALL the multi-signer addresses for the verification process.
BCC-02 BOT CHAIN - CHAIN

--- page 12 ---
Provide a link to the medium/blog with all of the above information included.
Long Term:
A combination of a time-lock on the contract upgrade operation and a DAO for controlling the upgrade operation mitigate the
contract upgrade risk by applying transparency and decentralization.
A time-lock with reasonable latency, such as 48 hours, for community awareness of privileged operations;
AND
Introduction of a DAO, governance, or voting module to increase decentralization, transparency, and user involvement;
AND
A medium/blog link for sharing the time-lock contract, multi-signers addresses, and DAO information with the community.
For remediation and mitigated status, please provide the following information:
Provide the deployed time-lock address.
Provide the gnosis address with ALL the multi-signer addresses for the verification process.
Provide a link to the medium/blog with all of the above information included.
Permanent:
Renouncing ownership of the admin  account or removing the upgrade functionality can fully resolve the risk.
Renounce the ownership and never claim back the privileged role;
OR
Remove the risky functionality.
Note: we recommend the project team consider the long-term solution or the permanent solution. The project team shall
make a decision based on the current state of their project, timeline, and project resources.
Alleviation
[BOT Chain, 02/23/2026]: The team acknowledged this issue.
[CertiK, 02/23/2026]: It is suggested to implement the aforementioned methods to avoid centralized failure. Also, CertiK
strongly encourages the project team to periodically revisit the private key security management of all addresses related to
centralized roles.
BCC-02 BOT CHAIN - CHAIN

--- page 13 ---
BCC-03 Centralizatio Risks
Category Severity Location Status
Centralization Centralization
BSCGovernor.sol (base): 171; BSCTimelock.sol (b
ase): 31; BSCValidatorSet.sol (base): 168, 175, 179,
521, 602; GovHub.sol (base): 21, 29, 34, 38; GovTo
ken.sol (base): 50, 59, 71; SlashIndicator.sol (bas
e): 90, 97, 101, 137, 193, 315, 357; StakeCredit.sol
(base): 73, 85, 103, 114, 136, 151, 188, 211; System
Reward.sol (base): 42, 63; TokenHub.sol (base): 10
6, 113, 130, 141, 154, 190, 201, 238, 300, 304; Token
RecoverPortal.sol (base): 243
Acknowledged
Description
In the contract BSCGovernor , the role GOV_HUB_ADDR  has authority over the functions shown in the diagram below. Any
compromise to the GOV_HUB_ADDR  account may allow the hacker to take advantage of this authority and change critical
governance parameters (e.g., voting delay/period, proposal threshold, quorum) and the governor protector.
BCC-03 BOT CHAIN - CHAIN

--- page 14 ---
Authenticated Role Function
Internal Calls
External Calls
External Calls
Internal Calls
Internal Calls
Internal Calls
External Calls
External Calls
Internal Calls
Internal Calls
GOV_HUB_ADDR updateParam
_setVotingDelay
value.bytesToAddress
key.compareStrings
_updateQuorumNumerator
_setProtector
_setVotingPeriod
value.bytesToUint64
value.bytesToUint256
_setProposalThreshold
_setLateQuorumVoteExtension
BCC-03 BOT CHAIN - CHAIN

--- page 15 ---
In the contract BSCTimelock , the role GOV_HUB_ADDR  has authority over the functions shown in the diagram below. Any
compromise to the GOV_HUB_ADDR  account may allow the hacker to take advantage of this authority and change the
timelock minimum delay (e.g., reduce the delay).
Authenticated Role Function
External Calls
External Calls
Internal Calls
GOV_HUB_ADDR updateParam
value.bytesToUint256
key.compareStrings
updateDelay
In the contract BSCValidatorSet , the role CROSS_CHAIN_CONTRACT_ADDR  has authority over the functions shown in the
diagram below. Any compromise to the CROSS_CHAIN_CONTRACT_ADDR  account may allow the hacker to take advantage of
this authority and call cross-chain handler entrypoints (which are deprecated and revert in this version).
Authenticated Role
Function
Function
Function
CROSS_CHAIN_CONTRACT_ADDR
handleFailAckPackage
handleAckPackage
handleSynPackage
In the contract BSCValidatorSet , the role GOV_HUB_ADDR  has authority over the functions shown in the diagram below.
Any compromise to the GOV_HUB_ADDR  account may allow the hacker to take advantage of this authority and change critical
consensus and fee-distribution parameters (e.g., burn ratio, cabinet size, gas treasury settings).
BCC-03 BOT CHAIN - CHAIN

--- page 16 ---
Function
State Variables
External Calls
External Calls
External Calls
External Calls
External Calls
External Calls
External Calls
Authenticated Role
External Calls
External Calls
updateParam
maxNumOfCandidates
maintainSlashScale
burnRatio
systemRewardAntiMEVRatio
numOfCabinets
maxNumOfWorkingCandidates
systemRewardBaseRatio
maxNumOfMaintaining
turnLength
Memory.compareStrings
newSystemRewardBaseRatio.add
newSystemRewardAntiMEVRatio.add
newGasTreasuryRatio.add
newBurnRatio.add
BytesToTypes.bytesToUint256
.add
IStakeHub.maxElectedValidators
abi.decode
GOV_HUB_ADDR
BCC-03 BOT CHAIN - CHAIN

--- page 17 ---
In the contract BSCValidatorSet , the role SLASH_CONTRACT_ADDR  has authority over the functions shown in the diagram
below. Any compromise to the SLASH_CONTRACT_ADDR  account may allow the hacker to take advantage of this authority and
arbitrarily misdemeanor/felony slash (jail/remove) validators.
Function
Internal Calls
Function State Variables
Internal Calls
Authenticated Role
Internal Calls
Internal Calls
misdemeanor
_misdemeanor
_enterMaintenance
canEnterMaintenance
felony numOfMaintaining
_felony
SLASH_CONTRACT_ADDR
In the contract BSCValidatorSet , the role STAKE_HUB_ADDR  has authority over the functions shown in the diagram below.
Any compromise to the STAKE_HUB_ADDR  account may allow the hacker to take advantage of this authority and trigger
felony slashing/removal of validators.
Function
State Variables
Internal Calls
Authenticated Role
Function
felony
numOfMaintaining
_felony
STAKE_HUB_ADDR
removeTmpMigratedValidator
In the contract GovHub , the role CROSS_CHAIN_CONTRACT_ADDR  has authority over the functions shown in the diagram
below. Any compromise to the CROSS_CHAIN_CONTRACT_ADDR  account may allow the hacker to take advantage of this
authority and call cross-chain handler entrypoints (which are deprecated and revert in this version).
BCC-03 BOT CHAIN - CHAIN

--- page 18 ---
Authenticated Role
Function
Function
Function
CROSS_CHAIN_CONTRACT_ADDR
handleFailAckPackage
handleAckPackage
handleSynPackage
In the contract GovHub , the role TIMELOCK_ADDR  has authority over the functions shown in the diagram below. Any
compromise to the TIMELOCK_ADDR  account may allow the hacker to take advantage of this authority and push arbitrary
updateParam(...)  calls to system contracts via GovHub.updateParam(...) .
Authenticated Role Function
Internal Calls
Internal Calls
TIMELOCK_ADDR updateParam
ParamChangePackage
notifyUpdates
In the contract GovToken , the role STAKE_HUB_ADDR  has authority over the functions shown in the diagram below. Any
compromise to the STAKE_HUB_ADDR  account may allow the hacker to take advantage of this authority and mint/burn
govBNB  (via sync ) and delegate votes.
BCC-03 BOT CHAIN - CHAIN

--- page 19 ---
Authenticated Role
Function
Function
Internal Calls
Function
Internal Calls
STAKE_HUB_ADDR
delegateVote
sync
syncBatch
_delegate
_sync
In the contract SlashIndicator , the role CROSS_CHAIN_CONTRACT_ADDR  has authority over the functions shown in the
diagram below. Any compromise to the CROSS_CHAIN_CONTRACT_ADDR  account may allow the hacker to take advantage of
this authority and call cross-chain handler entrypoints (which are deprecated and revert in this version).
Authenticated Role
Function
Function
Function
CROSS_CHAIN_CONTRACT_ADDR
handleSynPackage
handleFailAckPackage
handleAckPackage
In the contract SlashIndicator , the role GOV_HUB_ADDR  has aut

【来源】https://www.botchain.ai/docs/Chain.pdf
