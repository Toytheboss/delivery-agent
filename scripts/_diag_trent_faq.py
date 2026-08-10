#!/usr/bin/env python3
"""One-off: simulate FAQ reply for Trent integration question."""
import asyncio

from bot.config_loader import load_config
from bot.knowledge import KnowledgeBase
from bot.rag import (
    _contains_blocked_topic,
    _retrieve_hits,
    generate_reply,
    resolve_llm_credentials,
)

Q = """I checked the docs and tested the live services again.
I found the working Routing API at
Mainnet https://example.com
Testnet https://dex-routing.bohr.life
Both return valid calldata targeting the canonical Universal Routers. I also found the external Testnet bridge addresses in the live Bridge config. Finality using the finalized tag works as expected.
Only these integration blockers remain:
BO Wallet
Is there any wallet-specific attestation that lets our backend prove a signature came from BO Wallet and not another EVM wallet? isBoWallet can be spoofed so it is not enough for backend verification.
RPC
We need two independent production RPC/WSS providers. Alchemy and the other major providers do not currently list Delivery Agent. The node deployment repository linked in the docs also returns 404. Can you provide supported providers or the complete node deployment package?
Also BOT Testnet chain ID 968 conflicts with Datagram in the public EIP-155 registry. How should WalletConnect integrations handle this?
Routing
Please confirm the rate limits, quote validity period, SLA and API versioning/deprecation policy for the dex-routing endpoints.
Testnet USDT
The faucet only provides tBOT. Could you fund a Testnet wallet with USDT or provide a supported way to obtain it for swap and LP testing?
Bridge
Please provide the exact confirmation counts, relayer/admin ownership, threshold-change process, upgrade or timelock policy, collateral reconciliation process and pause/incident procedure."""


async def main() -> None:
    cfg = load_config()
    print("blocked quote?", _contains_blocked_topic(Q, cfg.blocked_topics))
    kb = KnowledgeBase(cfg.knowledge_dir, cfg.chunk_size, cfg.chunk_overlap)
    print("chunks", kb.reload())
    creds = resolve_llm_credentials(cfg)
    hits = _retrieve_hits(Q, kb, cfg, creds)
    print("hits", len(hits), "best", hits[0].score if hits else None)
    for h in hits[:5]:
        print(f"  score={h.score:.3f} src={h.source[:80]!r} text={h.text[:120]!r}")
    dec = await generate_reply(Q, kb, cfg)
    print("should_reply", dec.should_reply, "reason", dec.reason, "score", dec.best_score)
    print("answer_preview:", (dec.answer or "")[:800])


if __name__ == "__main__":
    asyncio.run(main())
