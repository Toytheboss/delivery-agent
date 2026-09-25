from types import SimpleNamespace

from bot.rag import split_reply_bubbles
from bot.workflow_form_chase import field_is_filled, format_missing_list, missing_fields
from bot.workflow_form_dispatch import build_form_messages


def test_live_form_splits_into_three_bubbles():
    cfg = SimpleNamespace(
        workflow_message_template=(
            "🎉 Congratulations! {project_name} is now live on BOT Chain Mainnet.\n\n"
            "Please submit your project info in this form. We will use it for "
            "website showcase / future gas rebates / potential grant support:\n"
            "{form_url}\n\n"
            "---\n"
            "Could you also coordinate a PR announcement on Twitter, mention that "
            "your project is live on BOT Chain. We will help to amplify.\n\n"
            "---\n"
            "You can also have your project displayed on DeFiLlama under the "
            "BOT Chain section if you want. Here's how:\n"
            "https://example.com/defillama\n\n"
            "Thanks for your support ❤️"
        ),
        workflow_google_form_url="https://forms.gle/test",
    )
    bubbles = build_form_messages(cfg, "NovaMint")
    assert len(bubbles) == 3
    assert "NovaMint" in bubbles[0]
    assert "https://forms.gle/test" in bubbles[0]
    assert "PR announcement" in bubbles[1]
    assert "DeFiLlama" in bubbles[2]
    assert split_reply_bubbles("a\n---\nb") == ["a", "b"]


def test_chase_required_fields_include_legacy_contract_name():
    names = [
        "Mainnet Contract Addresss",
        "Link of Project X ( Formerly Twitter) Profile Page",
        "Project logo",
        "A brief introduction of your project",
    ]
    fields = {
        "Contract Addresss/主网合约": "0xabc",
        "Link of Project X ( Formerly Twitter) Profile Page": "https://x.com/n",
        "Project logo": [{"file_token": "tok"}],
        "A brief introduction of your project": "A wallet bot",
    }
    assert missing_fields(fields, names) == []
    assert field_is_filled(fields, "Mainnet Contract Addresss")
    empty = dict(fields)
    empty.pop("Project logo")
    assert missing_fields(empty, names) == ["Project logo"]
    assert "Project logo" in format_missing_list(["Project logo"])
