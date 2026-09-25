from bot.dashboard_snapshot import form_delivery_sent


def test_unmatched_group_is_never_sent():
    assert form_delivery_sent(
        unique_chat=False,
        has_send_event=False,
        chase_first_sent=False,
        in_processed_ids=True,
        has_skip_event=True,
    ) is False


def test_skip_without_send_is_not_sent():
    assert form_delivery_sent(
        unique_chat=True,
        has_send_event=False,
        chase_first_sent=False,
        in_processed_ids=True,
        has_skip_event=True,
    ) is False


def test_real_send_event_counts():
    assert form_delivery_sent(
        unique_chat=True,
        has_send_event=True,
        chase_first_sent=False,
        in_processed_ids=True,
        has_skip_event=False,
    ) is True


def test_chase_note_counts():
    assert form_delivery_sent(
        unique_chat=True,
        has_send_event=False,
        chase_first_sent=True,
        in_processed_ids=False,
        has_skip_event=False,
    ) is True


def test_historical_processed_id_needs_matched_group():
    assert form_delivery_sent(
        unique_chat=True,
        has_send_event=False,
        chase_first_sent=False,
        in_processed_ids=True,
        has_skip_event=False,
    ) is True
    assert form_delivery_sent(
        unique_chat=False,
        has_send_event=False,
        chase_first_sent=False,
        in_processed_ids=True,
        has_skip_event=False,
    ) is False
