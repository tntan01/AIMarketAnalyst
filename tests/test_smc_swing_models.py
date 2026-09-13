from dataclasses import replace

import pytest

from core.smc_models import SmcSwing, build_swing_id


PIVOT = "2026-01-01T00:00:00Z"
CONFIRMED = "2026-01-02T00:00:00Z"


def swing(*, confirmed_at=CONFIRMED, pivot_index=7) -> SmcSwing:
    return SmcSwing(
        swing_id=build_swing_id(
            symbol="EURUSD",
            timeframe="H4",
            kind="high",
            pivot_time=PIVOT,
        ),
        symbol="EURUSD",
        timeframe="H4",
        kind="high",
        level=110.0,
        pivot_time=PIVOT,
        confirmed_at=confirmed_at,
        pivot_index=pivot_index,
    )


def test_swing_id_uses_pivot_identity_and_not_rolling_index():
    stable_id = build_swing_id(
        symbol="EURUSD",
        timeframe="H4",
        kind="high",
        pivot_time=PIVOT,
    )
    first = swing(pivot_index=7)
    after_window_shift = swing(pivot_index=107)

    assert first.swing_id == stable_id
    assert after_window_shift.swing_id == stable_id
    assert first.stable_id == stable_id
    assert first.id == first.swing_id


def test_unconfirmed_swing_is_not_usable():
    candidate = swing(confirmed_at=None)

    assert candidate.usable is False
    assert candidate.to_dict()["usable"] is False


def test_confirmed_swing_is_usable_and_round_trips():
    confirmed = swing()

    assert confirmed.usable is True
    restored = SmcSwing.from_dict(confirmed.to_dict())

    assert restored == confirmed
    assert restored.usable is True


def test_confirmation_is_canonicalized_to_utc_and_must_follow_pivot():
    confirmed = SmcSwing(
        swing_id="external-source-id",
        symbol="EURUSD",
        timeframe="H4",
        kind="low",
        level=99.0,
        pivot_time="2026-01-01T00:00:00+00:00",
        confirmed_at="2026-01-01T02:00:00+00:00",
    )

    assert confirmed.pivot_time == "2026-01-01T00:00:00+00:00"
    assert confirmed.confirmed_at == "2026-01-01T02:00:00+00:00"

    with pytest.raises(ValueError, match="cannot precede"):
        replace(confirmed, confirmed_at="2025-12-31T23:00:00Z")


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"kind": "middle"}, "Invalid SMC swing kind"),
        ({"timeframe": "M5"}, "Invalid SMC timeframe"),
        ({"level": float("nan")}, "level must be finite"),
        ({"pivot_time": "2026-01-01T00:00:00"}, "timezone-aware UTC"),
        ({"pivot_index": -1}, "cannot be negative"),
    ],
)
def test_swing_validation_rejects_invalid_fields(changes, message):
    with pytest.raises(ValueError, match=message):
        replace(swing(), **changes)


def test_builder_changes_identity_for_source_coordinates_but_has_no_index_argument():
    base = build_swing_id(
        symbol="EURUSD",
        timeframe="H4",
        kind="high",
        pivot_time=PIVOT,
    )
    different_pivot = build_swing_id(
        symbol="EURUSD",
        timeframe="H4",
        kind="high",
        pivot_time="2026-01-02T00:00:00Z",
    )
    different_kind = build_swing_id(
        symbol="EURUSD",
        timeframe="H4",
        kind="low",
        pivot_time=PIVOT,
    )

    assert base != different_pivot
    assert base != different_kind
