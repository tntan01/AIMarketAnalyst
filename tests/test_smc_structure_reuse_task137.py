"""Task 137 — the window reuse must be invisible in the canonical result.

The performance fix reuses, inside one evaluation, work that used to be redone
for every prefix of the same closed window: the candle validation, the pivot
detection, the ATR distance filter and the ATR reference.  A change like that is
only acceptable if it changes NOTHING else, so this file proves it the strict
way: it evaluates the same inputs twice — once with the reuse on and once with
it off (``core.smc_structure_window.ENABLED``) — and requires byte-identical
canonical results, identity, reason codes, lifecycle and replay payload.

With the reuse off, every accessor takes the fallback path, which is exactly the
recompute-per-prefix code the optimisation replaced.  That makes the "before"
arm a real oracle rather than a second copy of the same logic.

The corpus arm runs on the real frozen task-131 snapshots when they are present
and is skipped, not weakened, when they are not: a synthetic window cannot stand
in for real data, and the note in the skip says so.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path

import pytest

import core.smc_structure_window as window_module
from core.market_models import Candle
from core.scanner_live_producers import derive_live_analysis
from core.smc_canonical_context import build_canonical_timeframe_context
from core.smc_structure_replay import replay_smc_structure
from core.smc_validation import replay_canonical_snapshot
from tests.test_scanner_release import NOW, _zoned_candles

CORPUS = (
    Path(__file__).resolve().parents[1]
    / "reports"
    / "scanner"
    / "smc_real_snapshots"
    / "corpus.jsonl.gz"
)


@pytest.fixture
def reuse_enabled():
    """Run the body with the reuse on, then restore the module flag."""

    original = window_module.ENABLED
    window_module.ENABLED = True
    try:
        yield
    finally:
        window_module.ENABLED = original


def _evaluate(candles, *, symbol: str, cutoff: datetime):
    return replay_smc_structure(
        candles,
        symbol=symbol,
        timeframe="H4",
        as_of=cutoff,
        tick_size=0.01,
    )


def _structure_payload(result) -> str:
    return json.dumps(result, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# The replay itself, on a real-shaped window
# ---------------------------------------------------------------------------


def test_the_replay_is_identical_with_the_reuse_off(reuse_enabled):
    """Events, snapshots and final state must not depend on how they were cached."""

    d1, h4, h1 = _zoned_candles()
    cutoff = NOW

    with_reuse = _evaluate(h4, symbol="XAU/USD", cutoff=cutoff)
    window_module.ENABLED = False
    try:
        without_reuse = _evaluate(h4, symbol="XAU/USD", cutoff=cutoff)
    finally:
        window_module.ENABLED = True

    assert _structure_payload(with_reuse) == _structure_payload(without_reuse)
    assert with_reuse["structure_state"] == without_reuse["structure_state"]
    assert with_reuse["events"] == without_reuse["events"]


def test_every_prefix_sees_the_same_pivots_and_atr(reuse_enabled):
    """The reuse primitives equal the plain functions at every prefix length."""

    from core.smc_context import _confirmed_swing_points, _filter_swings_by_atr

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")

    checked = 0
    for length in range(1, len(window) + 1):
        prefix = window[:length]
        cached = reuse.swings(
            prefix,
            symbol="XAU/USD",
            lookback=5,
            provisional=False,
            scope="external",
            equal_tolerance=0.0,
        )
        plain = _confirmed_swing_points(
            prefix,
            symbol="XAU/USD",
            timeframe="H4",
            lookback=5,
            provisional=False,
            scope="external",
            equal_tolerance=0.0,
        )
        assert cached == plain, f"pivots differ at prefix length {length}"
        assert reuse.filter_swings_by_atr(prefix, cached) == _filter_swings_by_atr(
            prefix, plain
        ), f"ATR filter differs at prefix length {length}"
        checked += 1
    assert checked == len(window)


def test_the_reuse_refuses_a_sequence_it_does_not_own(reuse_enabled):
    """A rebuilt or unrelated sequence is never answered from the window."""

    from core.smc_context import _confirmed_swing_points

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")
    assert reuse.owns(window[:10])
    assert reuse.is_window(window)
    # Ownership is about the candle OBJECTS, not the list wrapper: re-slicing the
    # same window is the same data and is reused, a different slice is not.
    assert reuse.owns(list(window))
    assert reuse.owns(window[5:]) is False
    assert not reuse.owns(window[5:15])
    assert not reuse.is_window(window[:10])
    # A rebuilt sequence holding equal-valued but different candles is refused.
    rebuilt = [
        Candle(time=c.time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume)
        for c in window[:10]
    ]
    assert not reuse.owns(rebuilt)
    # And the refusal is a correct answer, not a failure.
    cached = reuse.swings(
        rebuilt,
        symbol="XAU/USD",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    )
    plain = _confirmed_swing_points(
        rebuilt,
        symbol="XAU/USD",
        timeframe="H4",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    )
    assert cached == plain


def test_the_history_assessment_is_identical_with_the_reuse_off(reuse_enabled):
    """Coverage, reason codes and freshness must not change with the reuse."""

    from core.smc_history import assess_smc_history

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")
    origin = window[-10].time

    for require_lifetime in (True, False):
        for origin_time in (None, origin):
            with_reuse = assess_smc_history(
                window,
                "H4",
                symbol="XAU/USD",
                origin_time=origin_time,
                require_lifetime=require_lifetime,
                window=reuse,
            ).to_dict()
            without_reuse = assess_smc_history(
                window,
                "H4",
                symbol="XAU/USD",
                origin_time=origin_time,
                require_lifetime=require_lifetime,
            ).to_dict()
            assert with_reuse == without_reuse


def test_a_prefix_is_never_answered_from_the_whole_window_history(reuse_enabled):
    """The coverage scan describes the window, so a prefix must not read it."""

    from core.smc_history import assess_smc_history

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")
    prefix = window[:40]
    assert not reuse.is_window(prefix)
    assert assess_smc_history(prefix, "H4", window=reuse).to_dict() == (
        assess_smc_history(prefix, "H4").to_dict()
    )


# ---------------------------------------------------------------------------
# The whole canonical context, and the documented replay of its snapshot
# ---------------------------------------------------------------------------


def _context(candles, *, timeframe: str, symbol: str, cutoff: datetime):
    return build_canonical_timeframe_context(
        candles,
        symbol=symbol,
        timeframe=timeframe,
        as_of=cutoff,
        tick_size=0.01,
    )


def test_the_canonical_context_is_identical_with_the_reuse_off(reuse_enabled):
    """The whole timeframe context — zones, lifecycle, vocabulary — is unchanged."""

    d1, h4, h1 = _zoned_candles()
    for timeframe, candles in (("D1", d1), ("H4", h4), ("H1", h1)):
        with_reuse = _context(candles, timeframe=timeframe, symbol="XAU/USD", cutoff=NOW)
        window_module.ENABLED = False
        try:
            without_reuse = _context(
                candles, timeframe=timeframe, symbol="XAU/USD", cutoff=NOW
            )
        finally:
            window_module.ENABLED = True
        assert json.dumps(with_reuse, sort_keys=True, default=str) == json.dumps(
            without_reuse, sort_keys=True, default=str
        ), f"{timeframe} context differs"


def _corpus_rows(limit: int) -> list[dict]:
    with gzip.open(CORPUS, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return rows[:limit]


def _corpus_candles(row, timeframe: str) -> list[Candle]:
    return [
        Candle(
            time=datetime.fromisoformat(item["t"]),
            open=float(item["o"]),
            high=float(item["h"]),
            low=float(item["l"]),
            close=float(item["c"]),
            volume=float(item.get("v") or 0.0),
        )
        for item in row["candles"][timeframe]
    ]


@pytest.mark.skipif(
    not CORPUS.exists(),
    reason=(
        "the real task-131 corpus is not present; the equivalence proof for the "
        "performance change must run on it, and a synthetic window is not a "
        "substitute for real data"
    ),
)
def test_the_real_snapshot_evaluation_is_identical_with_the_reuse_off(reuse_enabled):
    """On real frozen snapshots: result, identity, reasons, lifecycle and replay."""

    from core.smc_snapshot_cache import smc_snapshot_identity
    from core.smc_scoring_result import smc_selection_of

    def fingerprint(row) -> str:
        candles = {tf: _corpus_candles(row, tf) for tf in ("D1", "H4", "H1", "M15")}
        cutoff = datetime.fromisoformat(row["as_of"])
        analysis = derive_live_analysis(
            candles["D1"],
            candles["H4"],
            candles["H1"],
            symbol=row["symbol"],
            captured_at=cutoff,
            news_in_3h=False,
            m15_candles=candles["M15"],
            m15_as_of=cutoff,
            tick_size=row["tick_size"],
            tick_size_source=row["tick_size_source"],
            min_rr=row.get("min_rr"),
        )
        evaluation = analysis["smc_evaluation"]
        sides = {}
        for side in ("buy", "sell"):
            final = smc_selection_of(evaluation.result.side(side))
            sides[side] = None if final is None else final.to_dict()
        return json.dumps(
            {
                "identity": smc_snapshot_identity(
                    symbol=row["symbol"],
                    as_of=cutoff,
                    candles_by_timeframe=candles,
                    metadata={
                        "tick_size": analysis["smc_snapshot"].tick_size,
                        "tick_size_source": analysis["smc_snapshot"].tick_size_source,
                    },
                ),
                "core_reason_codes": list(analysis["smc_snapshot"].core_reason_codes),
                "sides": sides,
                "structure": json.loads(
                    json.dumps(
                        {
                            tf: {
                                "structure": (analysis["smc_snapshot"].smc or {})
                                .get(tf, {})
                                .get("structure"),
                                "bos": (analysis["smc_snapshot"].smc or {})
                                .get(tf, {})
                                .get("bos"),
                                "choch_confirmed": (analysis["smc_snapshot"].smc or {})
                                .get(tf, {})
                                .get("choch_confirmed"),
                            }
                            for tf in ("D1", "H4", "H1")
                        },
                        default=str,
                    )
                ),
                "replay": replay_canonical_snapshot(
                    analysis["smc_snapshot"], min_rr=row.get("min_rr")
                ),
            },
            sort_keys=True,
            default=str,
        )

    rows = _corpus_rows(6)
    assert rows, "the corpus must carry rows"
    for row in rows:
        with_reuse = fingerprint(row)
        window_module.ENABLED = False
        try:
            without_reuse = fingerprint(row)
        finally:
            window_module.ENABLED = True
        assert with_reuse == without_reuse, f"{row['symbol']}@{row['as_of']} differs"


# ---------------------------------------------------------------------------
# Ownership: endpoints are not a proof
# ---------------------------------------------------------------------------


def _with_swapped_candle(candles: list, index: int, *, shift: float):
    """A copy of *candles* with one candle in the middle replaced.

    The endpoints are untouched, so an endpoint-only ownership check would still
    answer "mine" and serve the window's cached pivots/ATR for data it does not
    hold.  ``shift`` moves the replacement's prices so a leaked answer is also
    numerically wrong, not merely stale.
    """

    changed = list(candles)
    original = changed[index]
    changed[index] = Candle(
        time=original.time,
        open=original.open + shift,
        high=original.high + shift,
        low=original.low + shift,
        close=original.close + shift,
        volume=original.volume,
    )
    return changed


def test_a_prefix_whose_middle_changed_is_not_owned(reuse_enabled):
    """Keeping the two endpoints does not make a sequence the window's."""

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")
    assert reuse.is_window(window)

    for index in (1, len(window) // 2, len(window) - 2):
        tampered = _with_swapped_candle(window, index, shift=5.0)
        assert tampered[0] is window[0], "the first endpoint must be unchanged"
        assert tampered[-1] is window[-1], "the last endpoint must be unchanged"
        assert reuse.owns(tampered[: index + 1]) is False, f"index {index}"
        assert reuse.owns(tampered) is False, f"index {index}"
        assert reuse.is_window(tampered) is False, f"index {index}"

    # Several middle candles at once are refused the same way.
    many = list(window)
    for index in (2, 7, 11):
        many[index] = _with_swapped_candle(window, index, shift=3.0)[index]
    assert reuse.owns(many) is False
    assert reuse.is_window(many) is False


def test_an_equal_valued_rebuild_is_refused_by_identity(reuse_enabled):
    """Identity, not equality: a rebuilt sequence is a different input."""

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")
    rebuilt = [
        Candle(time=c.time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume)
        for c in window
    ]
    assert rebuilt == window, "the rebuild holds equal values"
    assert reuse.owns(rebuilt) is False
    assert reuse.is_window(rebuilt) is False


def test_a_changed_prefix_gets_the_plain_answers_everywhere(reuse_enabled):
    """A refused sequence must be answered by the plain path, on its own data."""

    from core.smc_context import (
        _confirmed_swing_points,
        _filter_swings_by_atr,
        atr_value_before_event,
    )
    from core.smc_history import assess_smc_history

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")
    tampered = _with_swapped_candle(window, len(window) // 2, shift=5.0)
    prefix = tampered[: len(window) // 2 + 1]

    # Pivots and the ATR filter: the reuse must not answer for the changed list.
    assert reuse.swings(
        prefix,
        symbol="XAU/USD",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    ) == _confirmed_swing_points(
        prefix,
        symbol="XAU/USD",
        timeframe="H4",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    )
    swings = _confirmed_swing_points(
        prefix,
        symbol="XAU/USD",
        timeframe="H4",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    )
    assert reuse.filter_swings_by_atr(prefix, swings) == _filter_swings_by_atr(
        prefix, swings
    )

    # The ATR reference before an event.
    index = len(tampered) - 1
    assert atr_value_before_event(
        tampered, timeframe="H4", event_index=index, window=reuse
    ) == atr_value_before_event(tampered, timeframe="H4", event_index=index)
    assert reuse.atr_before_index(tampered, index) is None

    # History coverage, including the whole-window check.
    assert assess_smc_history(tampered, "H4", symbol="XAU/USD", window=reuse).to_dict() == (
        assess_smc_history(tampered, "H4", symbol="XAU/USD").to_dict()
    )
    assert assess_smc_history(
        tampered, "H4", symbol="XAU/USD", require_lifetime=True, window=reuse
    ).to_dict() == assess_smc_history(
        tampered, "H4", symbol="XAU/USD", require_lifetime=True
    ).to_dict()

    # The replay: passing a foreign window must not change its result.
    cutoff = NOW
    with_foreign_window = replay_smc_structure(
        tampered,
        symbol="XAU/USD",
        timeframe="H4",
        as_of=cutoff,
        tick_size=0.01,
        window=reuse,
    )
    plain = replay_smc_structure(
        tampered, symbol="XAU/USD", timeframe="H4", as_of=cutoff, tick_size=0.01
    )
    assert json.dumps(with_foreign_window, sort_keys=True, default=str) == json.dumps(
        plain, sort_keys=True, default=str
    )


def test_a_genuine_slice_is_still_reused(reuse_enabled):
    """Control: the refusals above must not cost the reuse its real case."""

    from core.smc_context import _confirmed_swing_points

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")

    for length in (1, 5, 40, len(window)):
        slice_ = window[:length]
        assert reuse.owns(slice_) is True, f"length {length}"
    assert reuse.is_window(window) is True
    assert reuse.is_window(window[:10]) is False

    # And the reused answer is still the plain answer.
    prefix = window[:40]
    assert reuse.swings(
        prefix,
        symbol="XAU/USD",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    ) == _confirmed_swing_points(
        prefix,
        symbol="XAU/USD",
        timeframe="H4",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    )


def _swings_of(candles):
    from core.smc_context import _confirmed_swing_points

    return _confirmed_swing_points(
        list(candles),
        symbol="XAU/USD",
        timeframe="H4",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    )


def _index_that_changes_the_answer(window, *, shift: float = 5.0):
    """A middle-candle swap that really changes the pivot set — read from the data.

    Not every swap changes the answer (a shifted candle only matters when it
    lands on a pivot boundary), so the index is searched rather than hard-coded:
    hard-coding one would make the test a statement about this fixture's shape
    instead of about the ownership rule.
    """

    original = _swings_of(window)
    for index in range(6, len(window) - 6):
        tampered = _with_swapped_candle(window, index, shift=shift)
        if _swings_of(tampered) != original:
            return index, tampered
    raise AssertionError("no middle swap changes the answer; unusable fixture")


def test_a_middle_swap_that_changes_the_answer_is_never_served_from_the_window(
    reuse_enabled,
):
    """The reported defect, reproduced on its own data.

    The swap keeps the first and last candle, so an endpoint-only ownership
    check answers "mine" and the caller is handed the window's pivots — which
    are pivots of *different* data.  This asserts that answer is not reachable:
    the sequence is refused, and what the reuse returns is the answer to the
    input it was actually given.
    """

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")
    index, tampered = _index_that_changes_the_answer(window)

    assert tampered[0] is window[0] and tampered[-1] is window[-1], "endpoints kept"
    assert index not in (0, len(window) - 1), "the swapped candle is in the middle"

    window_answer = _swings_of(window)
    input_answer = _swings_of(tampered)
    assert window_answer != input_answer, (
        "this swap must change the answer, otherwise the test proves nothing"
    )

    assert reuse.owns(tampered) is False
    assert reuse.is_window(tampered) is False
    # What the reuse returns is the input's own answer — never the window's.
    assert reuse.swings(
        tampered,
        symbol="XAU/USD",
        lookback=5,
        provisional=False,
        scope="external",
        equal_tolerance=0.0,
    ) == input_answer


def test_a_prefix_swap_shifts_the_atr_answers_too(reuse_enabled):
    """The ATR reference and the distance filter follow the input, not the window."""

    from core.smc_context import atr_value_before_event

    d1, h4, h1 = _zoned_candles()
    window = list(h4)
    reuse = window_module.StructureWindowReuse(window, "H4", symbol="XAU/USD")

    shift = 5.0
    prefix_length = 40
    changed = False
    for index in range(6, prefix_length - 6):
        tampered = _with_swapped_candle(window, index, shift=shift)
        prefix = tampered[:prefix_length]
        if atr_value_before_event(
            prefix, timeframe="H4", event_index=prefix_length - 1
        ) != atr_value_before_event(
            window[:prefix_length], timeframe="H4", event_index=prefix_length - 1
        ):
            changed = True
            break
    assert changed, "no prefix swap changed the ATR reference; unusable fixture"

    assert reuse.owns(prefix) is False
    assert reuse.atr_before_index(prefix, prefix_length - 1) is None
    assert atr_value_before_event(
        prefix, timeframe="H4", event_index=prefix_length - 1, window=reuse
    ) == atr_value_before_event(prefix, timeframe="H4", event_index=prefix_length - 1)
