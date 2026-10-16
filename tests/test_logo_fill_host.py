from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from bot.workflow_logo_fill import logo_fill_allowed, logo_fill_on_this_host


def test_logo_fill_on_this_host_skips_delivery_install():
    with patch("bot.workflow_logo_fill.ROOT", "/opt/delivery-agent"):
        assert logo_fill_on_this_host() is False
    with patch("bot.workflow_logo_fill.ROOT", "/opt/delivery-agent/"):
        assert logo_fill_on_this_host() is False


def test_logo_fill_on_this_host_keeps_audit_install():
    with patch("bot.workflow_logo_fill.ROOT", "/opt/botchain-qa-tg-bot"):
        assert logo_fill_on_this_host() is True


def test_logo_fill_allowed_needs_config_and_host():
    cfg_on = SimpleNamespace(workflow_logo_fill_enabled=True)
    cfg_off = SimpleNamespace(workflow_logo_fill_enabled=False)
    with patch("bot.workflow_logo_fill.logo_fill_on_this_host", return_value=True):
        assert logo_fill_allowed(cfg_on) is True
        assert logo_fill_allowed(cfg_off) is False
    with patch("bot.workflow_logo_fill.logo_fill_on_this_host", return_value=False):
        assert logo_fill_allowed(cfg_on) is False
        assert logo_fill_allowed(cfg_off) is False
