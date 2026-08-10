#!/usr/bin/env python3
import asyncio
import os
from pathlib import Path

for line in Path(".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from bot.config_loader import load_config
from bot.knowledge import KnowledgeBase
from bot.rag import generate_reply

Q = (
    "Is there any wallet-specific attestation that lets our backend prove a "
    "signature came from BO Wallet? isBoWallet can be spoofed. "
    "Also what are dex-routing quote validity and testnet USDT faucet?"
)


async def main() -> None:
    cfg = load_config()
    kb = KnowledgeBase(cfg.knowledge_dir, cfg.chunk_size, cfg.chunk_overlap)
    n = kb.reload()
    sources = {c.source for c in kb._chunks}
    print("chunks", n)
    print("has blockers file", any("integration_blockers" in s for s in sources))
    dec = await generate_reply(Q, kb, cfg)
    print(dec.should_reply, dec.reason, round(dec.best_score, 3))
    print((dec.text or "")[:800])


if __name__ == "__main__":
    asyncio.run(main())
