"""Fail process startup if workflow code imports a missing module.

Lazy ``from bot.workflow_xxx import`` inside functions does not run at import
time, so a half-copied ``bot/`` tree can boot and only crash when a project
goes live. Collect ``bot.workflow_*`` imports from every ``bot/*.py`` and load
them before Telegram connects.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parent
_SKIP_MODULES = frozenset({"bot.main"})


def referenced_bot_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("bot."):
                out.add(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("bot."):
                    out.add(alias.name)
    return out


def discover_required_modules(bot_dir: Path | None = None) -> list[str]:
    root = bot_dir or BOT_DIR
    needed: set[str] = set()
    for path in sorted(root.glob("workflow_*.py")):
        needed.add(f"bot.{path.stem}")
    for path in sorted(root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        needed.update(
            name
            for name in referenced_bot_modules(text)
            if name.startswith("bot.workflow_")
        )
    return sorted(needed)


def assert_bot_imports(bot_dir: Path | None = None) -> list[str]:
    loaded: list[str] = []
    for name in discover_required_modules(bot_dir):
        if name in _SKIP_MODULES:
            continue
        importlib.import_module(name)
        loaded.append(name)
    return loaded
