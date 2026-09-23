#!/usr/bin/env python3
"""Fail if critical AppConfig fields were dropped from config_loader.

Does not import bot.config_loader (avoids needing PyYAML locally). Parses the
source with AST so it can run as a pre-deploy gate:

  python3 scripts/check_critical_config_fields.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOADER = ROOT / "bot" / "config_loader.py"

# Keep in sync with CRITICAL_CONFIG_FIELDS in bot/config_loader.py
CRITICAL_CONFIG_FIELDS: tuple[str, ...] = (
    "workflow_verify_alert_enabled",
    "workflow_verify_alert_lark_chat_id",
    "workflow_verify_alert_cooldown_hours",
    "workflow_verify_alert_state_file",
    "workflow_blake_weekly_enabled",
    "workflow_blake_weekly_chat_id",
    "trusted_auto_learn_enabled",
    "trusted_auto_learn_user_ids",
    "trusted_auto_learn_usernames",
    "trusted_auto_learn_min_chars",
    "trusted_auto_learn_state_file",
    "tech_support_enabled",
    "tech_support_lark_chat_id",
)


def _class_ann_assigns(tree: ast.AST, class_name: str) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    names.add(item.target.id)
            break
    return names


def _constant_tuple_names(tree: ast.AST, const_name: str) -> list[str] | None:
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            if node.targets[0].id != const_name:
                continue
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or node.target.id != const_name:
                continue
            value = node.value
        else:
            continue
        if value is None or not isinstance(value, (ast.Tuple, ast.List)):
            return None
        out: list[str] = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
            else:
                return None
        return out
    return None


def _kwargs_in_load_config(tree: ast.AST) -> set[str]:
    """Collect keyword names passed to AppConfig(...) inside load_config."""
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "load_config":
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                if sub.func.id == "AppConfig":
                    for kw in sub.keywords:
                        if kw.arg:
                            names.add(kw.arg)
        break
    return names


def main() -> int:
    src = LOADER.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(LOADER))

    declared_const = _constant_tuple_names(tree, "CRITICAL_CONFIG_FIELDS")
    if declared_const is None:
        print("FAIL: CRITICAL_CONFIG_FIELDS constant missing or malformed in config_loader.py")
        return 1
    if tuple(declared_const) != CRITICAL_CONFIG_FIELDS:
        print("FAIL: scripts/check_critical_config_fields.py list drift vs config_loader.py")
        print(f"  script: {CRITICAL_CONFIG_FIELDS}")
        print(f"  loader: {tuple(declared_const)}")
        return 1

    class_fields = _class_ann_assigns(tree, "AppConfig")
    missing_class = [n for n in CRITICAL_CONFIG_FIELDS if n not in class_fields]
    if missing_class:
        print("FAIL: AppConfig dataclass missing critical fields:")
        for name in missing_class:
            print(f"  - {name}")
        return 1

    kwargs = _kwargs_in_load_config(tree)
    missing_kwargs = [n for n in CRITICAL_CONFIG_FIELDS if n not in kwargs]
    if missing_kwargs:
        print("FAIL: load_config() AppConfig(...) missing critical kwargs:")
        for name in missing_kwargs:
            print(f"  - {name}")
        return 1

    if "assert_critical_config_fields" not in src:
        print("FAIL: load_config must call assert_critical_config_fields")
        return 1

    print("OK: critical config fields declared, loaded, and asserted:")
    for name in CRITICAL_CONFIG_FIELDS:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
