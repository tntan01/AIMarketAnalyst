"""Task 79 — acceptance matrix for the M15 entry confirmation (tasks 73–79).

Cases required by the checklist and the acceptance dossier: the stale
rejection of task 4, a current/recent entry visit, a new visit that supersedes a
confirmation, price far from the entry, trigger timeout, M15 missing/insufficient,
the BUY/SELL mirror, the typed round-trip and the chain
zone/visit/trigger → evaluator → typed result → caller (scorer).

The candle tables below are written out so every threshold can be checked by
hand against the contract sources: lifecycle spec §11 (R16-02), parameter table
P10 and the acceptance dossier row for tasks 73–79.

Contract under test (all expectations below are derived from those documents,
not from the implementation):

* anchor = close of the first overlapping M15 candle after ``available_at``;
  ``trigger_anchor_at == visit_anchor_at``.
* the confirmation close is valid at ``1 <= delta <= 3`` bars after the anchor.
* the trigger stays alive through ``delta = 12`` and expires when the candle at
  ``delta = 13`` closes.
* a new entry visit, a close beyond the distal boundary plus buffer, a reclaim
  into the zone, or price running more than ``0.50 * ATR`` away from the entry
  boundary cancels the confirmation, each with its own reason.
* M15 owns readiness only: no M15 outcome changes B/Q/L/C or quality.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from core.market_models import Candle
from core.smc_m15_confirmation import (
    M15_CONFIRMATION_REASON,
    SMC_CUTOFF_MISSING_REASON,
    SMC_CUTOFF_NAIVE_REASON,
    SMC_TIMESTAMP_INVALID_REASON,
    M15_DATA_UNAVAILABLE_REASON,
    M15_ENTRY_TOO_FAR_REASON,
    M15_INSUFFICIENT_DATA_REASON,
    M15_NEW_VISIT_REASON,
    M15_NO_CONFIRMATION_REASON,
    M15_RECLAIM_AGAINST_REASON,
    M15_ZONE_NOT_TESTED_REASON,
    TRIGGER_EXPIRED_REASON,
    ZONE_INVALIDATED_REASON,
    evaluate_m15_confirmation,
    evaluate_m15_entry_confirmation,
)
from core.smc_models import M15Confirmation
from core.smc_scorer import score_smc
from tests.test_smc_scorer import _smc, _technical

_REGIME = {"primary": "trend_up"}
_TIME0 = datetime(2026, 8, 6, tzinfo=timezone.utc)
_BUY_ZONE = (90.0, 95.0)
_SELL_ZONE = (105.0, 110.0)
_ZONE_ID = "smcz-task79-buy"
_MIRROR_AXIS = 200.0
_STALE_FIXTURE = Path("tests/fixtures/smc_m15_stale_rejection.json")


# -- Fixture builders --------------------------------------------------------


def _candles(rows, start=0):
    return [
        Candle(
            time=_TIME0 + timedelta(minutes=15 * (start + offset)),
            open=open_,
            high=high,
            low=low,
            close=close,
        )
        for offset, (open_, high, low, close) in enumerate(rows)
    ]


def _warmup(count=20, price=98.0, start=0):
    """Calm oscillation above the demand zone so the ATR window is warm."""

    rows = []
    for index in range(count):
        swing = 0.25 if index % 2 == 0 else -0.2
        close = price + swing
        rows.append(
            (
                price,
                max(price, close) + 0.2,
                min(price, close) - 0.2,
                close,
            )
        )
        price = close
    return _candles(rows, start)


# Buy fixture: a micro pivot high at 96.5 (index 25, confirmed at index 28), the
# zone touch at index 29, the break candle at index 30 closing 97.0 above both
# the pivot and the zone, then a pullback to 95.10 so the entry is still within
# 0.50 * ATR of the zone boundary at the evaluation point.
_MICRO_TAIL = [
    (97.2, 97.3, 96.9, 97.0),
    (97.0, 97.05, 96.65, 96.7),
    (96.7, 96.45, 96.2, 96.3),
    (96.3, 96.35, 96.1, 96.15),
    (96.15, 96.3, 96.05, 96.25),
    (96.25, 96.5, 96.2, 96.45),
    (96.45, 96.4, 96.15, 96.2),
    (96.2, 96.3, 95.95, 96.0),
    (96.0, 96.05, 95.7, 95.75),
    (95.75, 95.8, 94.9, 95.05),
    (95.05, 97.1, 94.95, 97.0),
    (96.5, 96.6, 95.02, 95.10),
]

# Buy fixture: a monotone fall into the zone (no confirmed micro high exists)
# and one strong candle closing back above the zone without a rejection wick.
_UNCONFIRMED_TAIL = [
    (98.0, 98.05, 97.7, 97.8),
    (97.8, 97.85, 97.5, 97.6),
    (97.6, 97.65, 97.3, 97.4),
    (97.4, 97.45, 97.1, 97.2),
    (97.2, 97.25, 96.9, 97.0),
    (97.0, 97.05, 96.7, 96.8),
    (96.8, 96.85, 96.5, 96.6),
    (96.6, 96.65, 96.3, 96.4),
    (96.4, 96.45, 96.1, 96.2),
    (96.2, 96.25, 95.9, 96.0),
    (96.0, 96.05, 95.7, 95.8),
    (95.8, 95.85, 95.5, 95.6),
    (95.6, 95.65, 94.9, 95.05),
    (95.15, 96.4, 95.1, 96.3),
    (96.0, 96.65, 95.95, 96.6),
]

# Buy fixture: a rejection candle that dips deep into the zone and closes back
# above it (lower wick 4.55 >= max(0.80 * 0.25, 0.25 * 4.90) = 1.225).
_REJECTION_TAIL = [
    (97.5, 97.6, 97.2, 97.3),
    (97.3, 97.35, 96.95, 97.05),
    (97.05, 97.1, 96.7, 96.8),
    (96.8, 96.85, 96.45, 96.55),
    (96.55, 96.6, 96.2, 96.3),
    (96.3, 96.35, 95.95, 96.05),
    (96.05, 96.1, 95.7, 95.8),
    (95.8, 95.85, 95.45, 95.55),
    (95.55, 95.6, 95.25, 95.35),
    (95.35, 95.45, 94.95, 95.05),
    (95.05, 95.4, 90.5, 95.3),
]


def _micro_break_candles(extra=()):
    return _warmup() + _candles(list(_MICRO_TAIL) + list(extra), start=20)


def _unconfirmed_level_candles():
    return _warmup() + _candles(list(_UNCONFIRMED_TAIL), start=20)


def _rejection_candles(extra=()):
    return _warmup() + _candles(list(_REJECTION_TAIL) + list(extra), start=20)


def _zone_payload(*, available_at=None):
    """Buy zone payload of the shared scorer fixture, with availability set."""

    zone = _smc("buy")["H4"]["demand_zones"][0]
    zone = dict(zone)
    zone["available_at"] = available_at.isoformat() if available_at else None
    return zone


def _score_with_m15(candles, *, as_of=None, zone_payload=None):
    """Run the real scorer with the M15 window and its snapshot cutoff."""

    smc = _smc("buy")
    if zone_payload is not None:
        smc["H4"]["demand_zones"][0] = zone_payload
    cutoff = as_of if as_of is not None else _close_at(candles[-1])
    return score_smc(
        smc,
        _technical("buy"),
        _REGIME,
        m15_candles=candles,
        m15_as_of=cutoff,
    )


def _flat_inside_zone(count, start=32, price=95.1):
    rows = [(price, price + 0.1, price - 0.05, price) for _ in range(count)]
    return _candles(rows, start)


def _mirror(candles):
    """Reflect prices around the axis so BUY becomes SELL (90↔110, 95↔105)."""

    return [
        Candle(
            time=candle.time,
            open=_MIRROR_AXIS - candle.open,
            high=_MIRROR_AXIS - candle.low,
            low=_MIRROR_AXIS - candle.high,
            close=_MIRROR_AXIS - candle.close,
        )
        for candle in candles
    ]


def _stale_rejection_candles():
    payload = json.loads(_STALE_FIXTURE.read_text(encoding="utf-8"))
    return payload, [SimpleNamespace(**item) for item in payload["candles"]]


def _close_at(candle):
    opened = candle.time
    if isinstance(opened, str):
        text = opened[:-1] + "+00:00" if opened.endswith("Z") else opened
        opened = datetime.fromisoformat(text)
    return opened + timedelta(minutes=15)


def _evaluate(side, zone_low, zone_high, candles, *, zone_id, as_of=None, **kwargs):
    """Evaluate with the snapshot cutoff implied by the candle list.

    Tests that exercise the cutoff itself pass ``as_of`` explicitly.
    """

    if as_of is None and isinstance(candles, (list, tuple)) and candles:
        last = candles[-1]
        if hasattr(last, "time"):
            as_of = _close_at(last)
    return evaluate_m15_entry_confirmation(
        side,
        zone_low,
        zone_high,
        candles,
        zone_id=zone_id,
        as_of=as_of,
        **kwargs,
    )


# -- Task 4 fixture as a regression for the new expected ---------------------


def test_stale_rejection_fixture_is_now_expired_without_confirmation():
    """47 candles in the zone cannot keep the first rejection alive.

    Expected before the fix (recorded in the fixture as the reproduced bug):
    ``status=not_confirmed``, ``penalty=2``, ``reason_codes=[M15_NO_CONFIRMATION]``.
    Expected after the fix (R16-03, P10 expiry row, tasks 73–79): the trigger
    expires at delta 13, so the record is ``expired``/``waiting`` readiness with
    ``M15_NO_CONFIRMATION`` + ``TRIGGER_EXPIRED`` and ``penalty=0``.
    """

    payload, candles = _stale_rejection_candles()
    zone = payload["zone"]
    confirmation = _evaluate(
        payload["side"],
        zone["low"],
        zone["high"],
        candles,
        zone_id=_ZONE_ID,
    )

    assert len(candles) == 48
    assert confirmation.status == "expired"
    assert confirmation.confirmed is False
    assert confirmation.entry_visit_id == f"{_ZONE_ID}:m15-visit-1"
    assert confirmation.bars_since_anchor == 47
    assert confirmation.trigger_event_id is None
    assert confirmation.confirmed_at is None
    assert confirmation.invalidated_at is None
    assert confirmation.reason_codes == (
        M15_NO_CONFIRMATION_REASON,
        TRIGGER_EXPIRED_REASON,
    )
    # Readiness only: the stale rejection never downgrades quality.
    assert confirmation.m15_status == "expired"
    adapter = evaluate_m15_confirmation(
        payload["side"],
        zone["low"],
        zone["high"],
        candles,
        zone_id=_ZONE_ID,
    )
    assert adapter["penalty"] == 0
    assert adapter["confirmed"] is False
    assert adapter["choch"] is False
    assert adapter["reaction"] is False


def test_stale_in_zone_candles_no_longer_subtract_scorer_points():
    """Regression of the old penalty: tested-but-unconfirmed used to cost 2.

    Expected before the fix: ``side.score == baseline.score - 2`` with
    ``M15_NO_CONFIRMATION`` in ``penalties``.  Expected after the fix (R16-03,
    parameter table P10, task 78): the trigger expires, the reason is traced and
    the quality is untouched.
    """

    candles = _warmup(20) + _candles(
        [(95.40, 95.50, 94.90, 95.00)] + [(94.90, 95.10, 94.80, 95.00)] * 30,
        start=20,
    )
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")
    side = _score_with_m15(candles).side("buy")

    assert side.score == baseline.score
    assert side.breakdown["subtotal"] == baseline.breakdown["subtotal"]
    assert side.breakdown["penalty_points"] == baseline.breakdown["penalty_points"]
    assert side.breakdown["penalties"] == baseline.breakdown["penalties"]
    assert M15_NO_CONFIRMATION_REASON in side.breakdown["reason_codes"]
    assert TRIGGER_EXPIRED_REASON in side.breakdown["reason_codes"]
    assert M15_NO_CONFIRMATION_REASON not in side.breakdown["penalties"]


# -- Current / just-completed entry visit -----------------------------------


def test_current_entry_visit_confirms_on_micro_break_and_departure():
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, _micro_break_candles(), zone_id=_ZONE_ID
    )

    assert confirmation.status == "confirmed"
    assert confirmation.confirmed is True
    assert confirmation.trigger_kind == "micro_break"
    assert confirmation.visit_ordinal == 1
    assert confirmation.bars_since_anchor == 2
    # delta 1 is the break candle at index 30 → close time 07:45Z.
    assert confirmation.confirmed_at == "2026-08-06T07:45:00+00:00"
    assert confirmation.confirmed_at == confirmation.trigger_at
    assert confirmation.trigger_anchor_at == confirmation.visit_anchor_at
    assert confirmation.expires_at == "2026-08-06T10:30:00+00:00"
    assert confirmation.reason_codes == (M15_CONFIRMATION_REASON,)
    assert confirmation.m15_status == "confirmed"


def test_current_entry_visit_confirms_on_rejection_with_follow_through():
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, _rejection_candles(), zone_id=_ZONE_ID
    )

    assert confirmation.status == "confirmed"
    assert confirmation.trigger_kind == "rejection"
    assert confirmation.bars_since_anchor == 1
    assert confirmation.confirmed_at == "2026-08-06T07:45:00+00:00"


def test_just_completed_visit_still_confirms_inside_trigger_window():
    """A visit that ended but is still inside its trigger window keeps validity."""

    candles = _micro_break_candles(
        [
            (95.10, 95.40, 95.06, 95.30),
            (95.30, 95.45, 95.20, 95.35),
        ]
    )
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID
    )

    assert confirmation.status == "confirmed"
    assert confirmation.entry_visit_id == f"{_ZONE_ID}:m15-visit-1"
    assert confirmation.bars_since_anchor == 4


# -- Negative branches -------------------------------------------------------


def test_micro_break_needs_a_confirmed_level():
    """A break of a level that is not confirmed yet never qualifies."""

    confirmation = _evaluate(
        "buy", *_BUY_ZONE, _unconfirmed_level_candles(), zone_id=_ZONE_ID
    )

    assert confirmation.status == "waiting"
    assert confirmation.confirmed is False
    assert confirmation.trigger_event_id is None
    assert confirmation.reason_codes[0] == M15_NO_CONFIRMATION_REASON


def test_zone_not_touched_is_waiting_not_confirmation():
    candles = _warmup(48, 100.0)
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID
    )

    assert confirmation.status == "zone_not_tested"
    assert confirmation.m15_status == "waiting"
    assert confirmation.entry_visit_id is None
    assert confirmation.reason_codes == (M15_ZONE_NOT_TESTED_REASON,)


def test_candle_inside_zone_without_trigger_stays_waiting():
    candles = _warmup(30) + _candles(
        [
            (95.40, 95.50, 94.90, 95.00),
            (95.00, 95.10, 94.80, 94.90),
        ],
        start=30,
    )
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID
    )

    assert confirmation.status == "waiting"
    assert confirmation.confirmed is False
    assert TRIGGER_EXPIRED_REASON not in confirmation.reason_codes
    assert confirmation.reason_codes == (M15_NO_CONFIRMATION_REASON,)


# -- Invalidation and expiry -------------------------------------------------


def test_new_entry_visit_supersedes_the_previous_confirmation():
    candles = _micro_break_candles(
        [
            (95.60, 95.70, 95.30, 95.50),
            (95.50, 95.55, 94.90, 95.00),
        ]
    )
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID
    )

    assert confirmation.status == "waiting"
    assert confirmation.entry_visit_id == f"{_ZONE_ID}:m15-visit-2"
    assert confirmation.visit_ordinal == 2
    assert confirmation.confirmed_at is None
    assert confirmation.reason_codes == (
        M15_NO_CONFIRMATION_REASON,
        M15_NEW_VISIT_REASON,
    )


def test_price_running_away_from_entry_invalidates_confirmation():
    candles = _micro_break_candles(
        [
            (97.50, 97.60, 97.40, 97.50),
            (98.00, 98.10, 97.90, 98.00),
        ]
    )
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID
    )

    assert confirmation.status == "invalidated"
    assert confirmation.confirmed is False
    assert confirmation.confirmed_at == "2026-08-06T07:45:00+00:00"
    # The guard is evaluated at the evaluation point (the last closed candle).
    assert confirmation.invalidated_at == _close_at(candles[-1]).isoformat()
    assert confirmation.invalidation_reason == M15_ENTRY_TOO_FAR_REASON
    assert confirmation.reason_codes == (M15_ENTRY_TOO_FAR_REASON,)
    assert confirmation.m15_status == "waiting"


def test_reclaim_back_into_zone_invalidates_confirmation():
    candles = _micro_break_candles([(96.00, 96.10, 94.90, 94.70)])
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID
    )

    assert confirmation.status == "invalidated"
    assert confirmation.invalidation_reason == M15_RECLAIM_AGAINST_REASON
    assert confirmation.reason_codes == (M15_RECLAIM_AGAINST_REASON,)


def test_close_beyond_distal_boundary_invalidates_confirmation():
    candles = _micro_break_candles([(96.00, 96.10, 89.50, 89.80)])
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID
    )

    assert confirmation.status == "invalidated"
    assert confirmation.invalidation_reason == ZONE_INVALIDATED_REASON
    assert confirmation.reason_codes == (ZONE_INVALIDATED_REASON,)


def test_trigger_stays_alive_at_delta_twelve_and_expires_at_delta_thirteen():
    base = _micro_break_candles()

    alive = base + _flat_inside_zone(10)
    alive_confirmation = _evaluate("buy", *_BUY_ZONE, alive, zone_id=_ZONE_ID)
    assert alive_confirmation.bars_since_anchor == 12
    assert alive_confirmation.status == "confirmed"

    expired = base + _flat_inside_zone(11)
    expired_confirmation = _evaluate("buy", *_BUY_ZONE, expired, zone_id=_ZONE_ID)
    assert expired_confirmation.bars_since_anchor == 13
    assert expired_confirmation.status == "expired"
    assert expired_confirmation.confirmed is False
    assert expired_confirmation.confirmed_at == "2026-08-06T07:45:00+00:00"
    assert expired_confirmation.reason_codes == (TRIGGER_EXPIRED_REASON,)


def test_event_before_available_at_cannot_open_or_confirm_a_visit():
    candles = _micro_break_candles()
    available_at = _close_at(candles[30])

    confirmation = _evaluate(
        "buy",
        *_BUY_ZONE,
        candles,
        zone_id=_ZONE_ID,
        available_at=available_at,
    )

    assert confirmation.status == "waiting"
    assert confirmation.confirmed is False
    assert confirmation.bars_since_anchor == 0
    # The pre-availability candles cannot open the visit either: the anchor is
    # the first candle that closed after available_at.
    assert confirmation.visit_anchor_at == _close_at(candles[31]).isoformat()


def test_available_at_keeps_the_trigger_when_the_visit_starts_after_it():
    candles = _micro_break_candles()
    available_at = _close_at(candles[28])

    confirmation = _evaluate(
        "buy",
        *_BUY_ZONE,
        candles,
        zone_id=_ZONE_ID,
        available_at=available_at,
    )

    assert confirmation.status == "confirmed"
    assert confirmation.visit_anchor_at == _close_at(candles[29]).isoformat()


# -- Missing data ------------------------------------------------------------


def test_missing_and_insufficient_m15_report_their_own_state():
    unavailable = _evaluate(
        "buy", *_BUY_ZONE, None, zone_id=_ZONE_ID
    )
    assert unavailable.status == "insufficient_data"
    assert unavailable.m15_status == "missing"
    assert unavailable.reason_codes == (M15_DATA_UNAVAILABLE_REASON,)

    short = _warmup(10)
    insufficient = _evaluate(
        "buy", *_BUY_ZONE, short, zone_id=_ZONE_ID
    )
    assert insufficient.status == "insufficient_data"
    assert insufficient.reason_codes == (M15_INSUFFICIENT_DATA_REASON,)

    invalid_bounds = _evaluate(
        "buy", 95.0, 90.0, _micro_break_candles(), zone_id=_ZONE_ID
    )
    assert invalid_bounds.status == "insufficient_data"
    assert invalid_bounds.reason_codes == (M15_INSUFFICIENT_DATA_REASON,)

    invalid_side = _evaluate(
        "hold", *_BUY_ZONE, _micro_break_candles(), zone_id=_ZONE_ID
    )
    assert invalid_side.status == "insufficient_data"
    assert invalid_side.reason_codes == (M15_DATA_UNAVAILABLE_REASON,)

    # A candle whose open time cannot be parsed cannot be placed on either side
    # of the cutoff, so it is never silently dropped: R73-02 reports the
    # canonical timestamp reason (data spec §6) instead of "not enough candles".
    malformed_candles = [SimpleNamespace(open=1.0) for _ in range(20)]
    malformed = _evaluate(
        "buy",
        *_BUY_ZONE,
        malformed_candles,
        zone_id=_ZONE_ID,
        as_of="2026-08-06T08:00:00+00:00",
    )
    assert malformed.status == "insufficient_data"
    assert malformed.reason_codes == (SMC_TIMESTAMP_INVALID_REASON,)


def test_zone_identity_is_required_for_a_confirmation():
    """A confirmation is a claim about one zone, so the zone must be named."""

    try:
        evaluate_m15_entry_confirmation("buy", *_BUY_ZONE, _micro_break_candles())
    except ValueError as error:
        assert "zone_id" in str(error)
    else:  # pragma: no cover - the contract requires the rejection
        raise AssertionError("M15 evaluation without a zone id must be rejected")


def test_missing_m15_leaves_the_score_untouched():
    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")
    without_m15 = score_smc(
        _smc("buy"), _technical("buy"), _REGIME, m15_candles=None
    ).side("buy")

    assert without_m15.score == baseline.score
    assert without_m15.breakdown == baseline.breakdown


# -- BUY/SELL mirror ---------------------------------------------------------


def test_sell_side_is_the_price_mirror_of_the_buy_side():
    buy_micro = _evaluate("buy", *_BUY_ZONE, _micro_break_candles(), zone_id="smcz-buy")
    sell_micro = _evaluate(
        "sell", *_SELL_ZONE, _mirror(_micro_break_candles()), zone_id="smcz-sell"
    )
    assert sell_micro.status == buy_micro.status == "confirmed"
    assert sell_micro.trigger_kind == buy_micro.trigger_kind == "micro_break"
    assert sell_micro.bars_since_anchor == buy_micro.bars_since_anchor

    buy_rejection = _evaluate(
        "buy", *_BUY_ZONE, _rejection_candles(), zone_id="smcz-buy"
    )
    sell_rejection = _evaluate(
        "sell", *_SELL_ZONE, _mirror(_rejection_candles()), zone_id="smcz-sell"
    )
    assert sell_rejection.status == buy_rejection.status == "confirmed"
    assert sell_rejection.trigger_kind == buy_rejection.trigger_kind == "rejection"

    sell_invalidated = _evaluate(
        "sell",
        *_SELL_ZONE,
        _mirror(_micro_break_candles([(96.00, 96.10, 89.50, 89.80)])),
        zone_id="smcz-sell",
    )
    assert sell_invalidated.status == "invalidated"
    assert sell_invalidated.invalidation_reason == ZONE_INVALIDATED_REASON


# -- R73-01: production caller keeps temporal provenance and the cutoff -----


def test_scorer_does_not_confirm_before_the_zone_was_available():
    """A zone available after every M15 candle can never be confirmed.

    Reproduction of R73-01: `score_smc` used to drop `available_at`, so the
    M15 window was evaluated as if the zone had always existed.
    """

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    available_at = _close_at(candles[-1]) + timedelta(minutes=15)
    zone = _zone_payload(available_at=available_at)

    side = _score_with_m15(candles, as_of=as_of, zone_payload=zone).side("buy")

    assert side.selected_zone is not None
    assert M15_ZONE_NOT_TESTED_REASON in side.breakdown["reason_codes"]
    assert M15_CONFIRMATION_REASON not in side.breakdown["reason_codes"]
    # The provenance travels through the canonical zone, not through a new
    # consumer field: the projected payload keeps its canonical field set.
    assert "available_at" not in side.selected_zone

    # The same provenance, evaluated directly, agrees with the scorer.
    typed = _evaluate(
        "buy",
        side.selected_zone["low"],
        side.selected_zone["high"],
        candles,
        zone_id=side.selected_zone_id,
        as_of=as_of,
        available_at=available_at,
    )
    assert typed.status == "zone_not_tested"
    assert typed.confirmed is False

    # Control: without the availability the very same window does confirm, so
    # the outcome above is caused by the zone provenance and not by the fixture.
    available = _evaluate(
        "buy",
        side.selected_zone["low"],
        side.selected_zone["high"],
        candles,
        zone_id=side.selected_zone_id,
        as_of=as_of,
    )
    assert available.status == "confirmed"


def test_scorer_confirms_after_the_zone_became_available_with_provenance():
    """A valid trigger after ``available_at`` still confirms end to end."""

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    available_at = _close_at(candles[28])
    zone = _zone_payload(available_at=available_at)

    side = _score_with_m15(candles, as_of=as_of, zone_payload=zone).side("buy")

    assert M15_CONFIRMATION_REASON in side.breakdown["reason_codes"]

    zone_id = side.selected_zone_id
    typed = _evaluate(
        "buy",
        side.selected_zone["low"],
        side.selected_zone["high"],
        candles,
        zone_id=zone_id,
        as_of=as_of,
        available_at=available_at,
    )
    assert typed.status == "confirmed"
    assert typed.zone_id == zone_id
    assert typed.entry_visit_id == f"{zone_id}:m15-visit-1"
    assert typed.trigger_event_id == f"{zone_id}:m15-visit-1:trigger-1"
    assert typed.confirmation_id == f"{zone_id}:m15-visit-1:confirm-1"
    assert typed.confirmed_at == "2026-08-06T07:45:00+00:00"
    assert typed.visit_anchor_at == "2026-08-06T07:30:00+00:00"
    assert typed.expires_at == "2026-08-06T10:30:00+00:00"


def test_m15_candle_closing_after_the_cutoff_cannot_change_the_result():
    """Only candles with ``close_at <= as_of`` take part (data spec §1–2).

    The extra candle opens exactly at the cutoff and closes inside the zone, so
    it would reclaim the confirmation if the boundary were not enforced.
    """

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    forming = Candle(
        time=as_of,
        open=96.50,
        high=96.60,
        low=94.70,
        close=94.80,
    )
    extended = candles + [forming]

    prefix_record = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID, as_of=as_of
    )
    extended_record = _evaluate(
        "buy", *_BUY_ZONE, extended, zone_id=_ZONE_ID, as_of=as_of
    )

    assert extended_record.to_dict() == prefix_record.to_dict()
    assert extended_record.status == "confirmed"
    assert extended_record.confirmed_at == "2026-08-06T07:45:00+00:00"
    # Control: at a later cutoff the same candle is closed and does change it,
    # which is why the boundary has to come from the snapshot and not from the
    # last element of the list.
    later_record = _evaluate(
        "buy", *_BUY_ZONE, extended, zone_id=_ZONE_ID, as_of=_close_at(forming)
    )
    assert later_record.status == "invalidated"
    assert later_record.invalidation_reason == M15_RECLAIM_AGAINST_REASON

    prefix_side = _score_with_m15(candles, as_of=as_of).side("buy")
    extended_side = _score_with_m15(extended, as_of=as_of).side("buy")
    assert extended_side.score == prefix_side.score
    assert (
        extended_side.breakdown["reason_codes"]
        == prefix_side.breakdown["reason_codes"]
    )
    assert M15_CONFIRMATION_REASON in extended_side.breakdown["reason_codes"]


def test_nonfinite_candle_after_the_cutoff_cannot_change_the_result():
    """R73-02: an excluded candle is never validated as part of the snapshot.

    The extra candle opens exactly at the cutoff (so it closes after it) and
    carries ``high=nan``.  Eligibility is decided by close time first, so the
    candle never reaches the OHLC check and the confirmed prefix is untouched.
    """

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    forming = Candle(
        time=as_of,
        open=96.50,
        high=float("nan"),
        low=94.70,
        close=94.80,
    )
    extended = candles + [forming]

    # The extra candle really is after the cutoff, and it is not an eligible
    # candle that the evaluator silently skipped.
    assert _close_at(forming) > as_of
    assert len(extended) == len(candles) + 1

    prefix_record = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID, as_of=as_of
    )
    extended_record = _evaluate(
        "buy", *_BUY_ZONE, extended, zone_id=_ZONE_ID, as_of=as_of
    )

    assert prefix_record.status == "confirmed"
    assert extended_record.to_dict() == prefix_record.to_dict()
    assert extended_record.reason_codes == (M15_CONFIRMATION_REASON,)

    # Control: once the candle is inside the cutoff it is eligible, and its
    # non-finite OHLC then fails the snapshot — which is exactly why the
    # boundary has to be applied before any candle content is validated.
    later_record = _evaluate(
        "buy", *_BUY_ZONE, extended, zone_id=_ZONE_ID, as_of=_close_at(forming)
    )
    assert later_record.status == "insufficient_data"
    assert later_record.reason_codes == (M15_INSUFFICIENT_DATA_REASON,)

    # A candle with an unreadable timestamp cannot be placed on either side of
    # the cutoff, so it is reported instead of dropped.
    undecidable = _evaluate(
        "buy",
        *_BUY_ZONE,
        candles + [SimpleNamespace(open=1.0, high=1.0, low=1.0, close=1.0)],
        zone_id=_ZONE_ID,
        as_of=as_of,
    )
    assert undecidable.status == "insufficient_data"
    assert undecidable.reason_codes == (SMC_TIMESTAMP_INVALID_REASON,)


def test_scorer_reasons_are_unchanged_by_a_nonfinite_candle_after_the_cutoff():
    """R73-02 through the real caller: the M15 evidence must not move."""

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    forming = Candle(
        time=as_of,
        open=96.50,
        high=float("nan"),
        low=94.70,
        close=94.80,
    )
    extended = candles + [forming]
    assert _close_at(forming) > as_of

    prefix_side = _score_with_m15(candles, as_of=as_of).side("buy")
    extended_side = _score_with_m15(extended, as_of=as_of).side("buy")

    assert M15_CONFIRMATION_REASON in extended_side.breakdown["reason_codes"]
    assert (
        extended_side.breakdown["reason_codes"]
        == prefix_side.breakdown["reason_codes"]
    )
    assert extended_side.score == prefix_side.score
    assert extended_side.breakdown["subtotal"] == prefix_side.breakdown["subtotal"]
    assert (
        extended_side.breakdown["penalty_points"]
        == prefix_side.breakdown["penalty_points"]
    )


def _with_times(candles, transform):
    """Copy candles with transformed open times (OHLC untouched)."""

    return [
        Candle(
            time=transform(candle.time),
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
        )
        for candle in candles
    ]


def test_naive_candle_timestamps_are_not_usable_on_the_eligibility_path():
    """R73-02 (phần còn lại): a naive candle time fails closed, never assumed UTC.

    Data spec §2/§6: an M15 timestamp that is missing, naive or unparseable is
    ``SMC_TIMESTAMP_INVALID`` — the evaluator must not silently read it as UTC.
    """

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    naive = _with_times(candles, lambda time: time.replace(tzinfo=None))

    aware_record = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID, as_of=as_of
    )
    naive_record = _evaluate(
        "buy", *_BUY_ZONE, naive, zone_id=_ZONE_ID, as_of=as_of
    )

    assert aware_record.status == "confirmed"
    assert aware_record.reason_codes == (M15_CONFIRMATION_REASON,)
    assert naive_record.status == "insufficient_data"
    assert naive_record.confirmed is False
    assert naive_record.reason_codes == (SMC_TIMESTAMP_INVALID_REASON,)
    assert naive_record.m15_status == "missing"
    # The naive copy differs only in tzinfo, never in price content.
    assert [candle.close for candle in naive] == [
        candle.close for candle in candles
    ]


def test_naive_candle_timestamps_never_reach_the_scorer_as_a_confirmation():
    """Same case through the real caller: no M15_CONFIRMATION for naive times."""

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    naive = _with_times(candles, lambda time: time.replace(tzinfo=None))

    aware_side = _score_with_m15(candles, as_of=as_of).side("buy")
    naive_side = _score_with_m15(naive, as_of=as_of).side("buy")

    assert M15_CONFIRMATION_REASON in aware_side.breakdown["reason_codes"]
    assert M15_CONFIRMATION_REASON not in naive_side.breakdown["reason_codes"]
    assert SMC_TIMESTAMP_INVALID_REASON in naive_side.breakdown["reason_codes"]
    # Readiness only: the reason changes, the quality does not.
    assert naive_side.score == aware_side.score
    assert naive_side.breakdown["subtotal"] == aware_side.breakdown["subtotal"]
    assert (
        naive_side.breakdown["penalty_points"]
        == aware_side.breakdown["penalty_points"]
    )


def test_timezone_aware_candle_timestamps_keep_their_offset_normalization():
    """A non-UTC offset is normalized, not rejected as invalid."""

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    offset = timezone(timedelta(hours=7))
    shifted = _with_times(candles, lambda time: time.astimezone(offset))

    utc_record = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID, as_of=as_of
    )
    shifted_record = _evaluate(
        "buy", *_BUY_ZONE, shifted, zone_id=_ZONE_ID, as_of=as_of
    )

    assert shifted_record.status == "confirmed"
    assert SMC_TIMESTAMP_INVALID_REASON not in shifted_record.reason_codes
    # Same instants, same record — including every timestamp it reports.
    assert shifted_record.to_dict() == utc_record.to_dict()
    assert shifted_record.confirmed_at == "2026-08-06T07:45:00+00:00"


def test_missing_or_invalid_cutoff_fails_closed_with_the_canonical_reason():
    candles = _micro_break_candles()

    # The evaluator itself is called without a cutoff here: the test helper
    # derives one from the candle list, which is exactly what must not happen
    # on the production seam.
    missing = evaluate_m15_entry_confirmation(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID
    )
    assert missing.status == "insufficient_data"
    assert missing.m15_status == "missing"
    assert missing.confirmed is False
    assert missing.reason_codes == (SMC_CUTOFF_MISSING_REASON,)

    naive = evaluate_m15_entry_confirmation(
        "buy",
        *_BUY_ZONE,
        candles,
        zone_id=_ZONE_ID,
        as_of=datetime(2026, 8, 6, 8, 0),
    )
    assert naive.status == "insufficient_data"
    assert naive.reason_codes == (SMC_CUTOFF_NAIVE_REASON,)

    unparseable = _evaluate(
        "buy", *_BUY_ZONE, candles, zone_id=_ZONE_ID, as_of="not-a-timestamp"
    )
    assert unparseable.status == "insufficient_data"
    assert unparseable.reason_codes == (SMC_CUTOFF_MISSING_REASON,)

    # A cutoff before enough closed candles is insufficient data, not a
    # confirmation from the candles that remain.
    early = _evaluate(
        "buy",
        *_BUY_ZONE,
        candles,
        zone_id=_ZONE_ID,
        as_of=_close_at(candles[9]),
    )
    assert early.status == "insufficient_data"
    assert early.reason_codes == (M15_INSUFFICIENT_DATA_REASON,)


def test_scorer_without_a_cutoff_never_claims_a_confirmation():
    """The production seam fails closed when the cutoff is not supplied yet."""

    side = score_smc(
        _smc("buy"),
        _technical("buy"),
        _REGIME,
        m15_candles=_micro_break_candles(),
    ).side("buy")

    assert SMC_CUTOFF_MISSING_REASON in side.breakdown["reason_codes"]
    assert M15_CONFIRMATION_REASON not in side.breakdown["reason_codes"]


# -- Serialization and the caller chain --------------------------------------


def test_confirmation_survives_typed_round_trip():
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, _micro_break_candles(), zone_id=_ZONE_ID
    )
    payload = json.loads(json.dumps(confirmation.to_dict()))
    restored = M15Confirmation.from_dict(payload)

    assert restored == confirmation
    assert restored.confirmed is True
    assert restored.confirmation_id == confirmation.confirmation_id
    assert restored.m15_status == "confirmed"


def test_typed_record_is_bound_to_zone_visit_and_trigger():
    confirmation = _evaluate(
        "buy", *_BUY_ZONE, _micro_break_candles(), zone_id=_ZONE_ID
    )

    assert confirmation.zone_id == _ZONE_ID
    assert confirmation.entry_visit_id == f"{_ZONE_ID}:m15-visit-1"
    assert confirmation.trigger_event_id == f"{_ZONE_ID}:m15-visit-1:trigger-1"
    assert confirmation.confirmation_id == f"{_ZONE_ID}:m15-visit-1:confirm-1"
    assert confirmation.zone_low == _BUY_ZONE[0]
    assert confirmation.zone_high == _BUY_ZONE[1]
    # `confirmed` is derived from status; there is no stored boolean.
    assert "confirmed" not in confirmation.to_dict()
    assert confirmation.confirmed is (confirmation.status == "confirmed")


def test_zone_visit_trigger_chain_reaches_the_scorer_caller():
    """Chain test: zone -> evaluator -> typed result -> scorer reasons."""

    baseline = score_smc(_smc("buy"), _technical("buy"), _REGIME).side("buy")
    confirmed = _score_with_m15(_micro_break_candles()).side("buy")
    waiting = _score_with_m15(_unconfirmed_level_candles()).side("buy")
    stale = _score_with_m15(_warmup(48, 100.0)).side("buy")

    # The scorer reads the canonical record of the selected zone.
    selected_zone_id = baseline.breakdown["selected_zone_id"]
    assert selected_zone_id
    record = _evaluate(
        "buy",
        baseline.selected_zone["low"],
        baseline.selected_zone["high"],
        _micro_break_candles(),
        zone_id=selected_zone_id,
    )
    assert record.confirmed is True

    assert M15_CONFIRMATION_REASON in confirmed.breakdown["reason_codes"]
    assert M15_NO_CONFIRMATION_REASON in waiting.breakdown["reason_codes"]
    assert M15_ZONE_NOT_TESTED_REASON in stale.breakdown["reason_codes"]
    # Readiness only: every M15 outcome leaves the quality untouched.
    for side in (confirmed, waiting, stale):
        assert side.score == baseline.score
        assert side.breakdown["subtotal"] == baseline.breakdown["subtotal"]
        assert side.breakdown["penalty_points"] == baseline.breakdown["penalty_points"]
        assert side.breakdown["penalties"] == baseline.breakdown["penalties"]
