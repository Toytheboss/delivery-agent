from bot.boot_check import discover_required_modules, referenced_bot_modules


def test_referenced_bot_modules_finds_lazy_from_import():
    src = "def f():\n    from bot.workflow_form_claim import begin_form_send\n"
    assert "bot.workflow_form_claim" in referenced_bot_modules(src)


def test_discover_includes_form_claim_from_live_onboard():
    mods = discover_required_modules()
    assert "bot.workflow_form_claim" in mods
    assert "bot.workflow_live_onboard" in mods
    assert "bot.folder_title_cache" not in mods


def test_form_claim_module_is_importable():
    import bot.workflow_form_claim as claim

    assert callable(claim.begin_form_send)


def test_discover_flags_lazy_workflow_even_if_file_missing(tmp_path):
    (tmp_path / "workflow_live_onboard.py").write_text(
        "def f():\n    from bot.workflow_form_claim import begin_form_send\n",
        encoding="utf-8",
    )
    mods = discover_required_modules(tmp_path)
    assert "bot.workflow_form_claim" in mods
    assert "bot.workflow_live_onboard" in mods
    assert not (tmp_path / "workflow_form_claim.py").exists()


def test_assert_fails_when_lazy_workflow_file_is_missing(tmp_path):
    from bot.boot_check import assert_bot_imports

    (tmp_path / "workflow_live_onboard.py").write_text(
        "def f():\n    from bot.workflow_form_claim import begin_form_send\n",
        encoding="utf-8",
    )
    try:
        assert_bot_imports(tmp_path)
    except ModuleNotFoundError as exc:
        assert "workflow_form_claim" in str(exc)
    else:
        raise AssertionError("expected missing workflow_form_claim to fail startup")
