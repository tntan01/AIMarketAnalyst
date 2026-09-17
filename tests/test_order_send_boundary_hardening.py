"""Gói hardening sau Lô C — F-C-01 (kill switch tại send boundary) và F-C-02.

**F-C-01.** `RuntimeOrderPolicy.order_enabled`/`certified()` nói cấu hình đã
ĐẦY ĐỦ; `live_order_permitted` nói người sở hữu đã CHO PHÉP gửi thật. Hai thứ
độc lập, và cái thứ hai mặc định tắt — nên một cấu hình đã certified vẫn không
gửi được gì. Rào chắn được kiểm ở `execute_order_candidate` ngay trước lệnh gọi
broker duy nhất, đọc policy HIỆN HÀNH, và không bao giờ cấp quyền — chỉ chặn.

**F-C-02.** `revalidate_execution` chỉ nhận `now` là datetime timezone-aware có
offset xác định; naive/không-phải-datetime bị chặn bằng mã riêng với
`checked_at=None` (không bịa mốc audit, không coerce, không ném ra ngoài). Cùng
luật cho `snapshot.tick_time`, và cho timestamp naive ở safety context.

Các test dưới đây chạy qua **caller thật** `ScannerController.execute_order_candidate`
với mọi gate khác đã PASS, nên "blocked" ở đây là do đúng rào chắn mới.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any

import pytest

from core.execution_revalidation_engine import revalidate_execution
from core.reason_codes import (
    LIVE_ORDER_DISABLED,
    ORDER_INTENT_ONLY,
    ORDER_POLICY_UNAVAILABLE,
    REVALIDATION_CLOCK_INVALID,
    SENDS_REAL_ORDER_NOT_FALSE,
    TICK_TIME_INVALID,
)
from core.scanner_order_policy import (
    DEFAULT_RUNTIME_ORDER_POLICY,
    load_runtime_order_policy,
)

_R = pytest.importorskip("tests.test_scanner_execution_controller")
_EX = pytest.importorskip("tests.test_execution_revalidation")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONTROLLER_SOURCE = _PROJECT_ROOT / "controllers" / "scanner_controller.py"


# ---------------------------------------------------------------------------
# F-C-01 / F-HC-01 / F-HC-02 — the send boundary
#
# The boundary is UNCONDITIONALLY closed in the no-rollout state: every Scanner
# proposal is blocked, whatever the config says and whatever the payload says.
# The codes report why; none of them grants.
# ---------------------------------------------------------------------------

_SHIPPED_CONFIG = _PROJECT_ROOT / "config" / "scanner_order_policy.json"


def _write_config(directory: Path, **overrides: Any) -> Path:
    """A copy of the shipped owner config, optionally flipped."""

    import json

    data = json.loads(_SHIPPED_CONFIG.read_text(encoding="utf-8"))
    data.update(overrides)
    target = directory / "scanner_order_policy.json"
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def _point_the_loader_at(directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the boundary's config reload at a temp directory.

    The loader resolves ``config.paths.CONFIG_DIR`` at call time, so this changes
    WHERE the boundary reads the policy from — it does not touch the boundary,
    the checks or the reason codes.
    """

    import config.paths as paths

    monkeypatch.setattr(paths, "CONFIG_DIR", directory)


def _dispatch(controller: Any, proposal: Any = None):
    mt5 = _R._MT5()
    controller.mt5 = mt5
    result = controller.execute_order_candidate(
        _R._proposal() if proposal is None else proposal
    )
    return result, mt5


def test_the_shipped_config_is_certified_but_the_boundary_is_still_closed() -> None:
    """Two independent things: a complete config, and a dispatch nobody permitted."""

    shipped = load_runtime_order_policy()

    assert shipped.certified() is True, "the shipped config is complete"
    assert shipped.order_enabled is True
    assert shipped.live_order_permitted is False


def test_the_config_says_no_and_the_payload_is_intent_only() -> None:
    """The shipped combination: blocked, nothing sent."""

    result, mt5 = _dispatch(_R._controller(None, _R._News()))

    assert result["success"] is False and result["blocked"] is True
    assert LIVE_ORDER_DISABLED in result["reason_codes"]
    assert ORDER_INTENT_ONLY in result["reason_codes"]
    assert mt5.place_calls == []


def test_a_permitted_config_and_an_intent_only_payload_STILL_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-HC-02: ``live_order_permitted=true`` is not a permission.

    This is the bypass the reviewer reproduced: with the switch on, an
    intent-only payload used to reach ``place_market_order``.  It no longer can
    — the switch is evidence/config for a future cutover, and the payload says
    "intent only", which is exactly why it is not sent.
    """

    _point_the_loader_at(tmp_path, monkeypatch)
    _write_config(tmp_path, live_order_permitted=True)

    result, mt5 = _dispatch(_R._controller(None, _R._News()))

    assert result["success"] is False and result["blocked"] is True
    assert ORDER_INTENT_ONLY in result["reason_codes"]
    assert LIVE_ORDER_DISABLED not in result["reason_codes"], "the config says permitted"
    assert mt5.place_calls == [], "a permitted switch must not open the boundary"


@pytest.mark.parametrize("value", [True, None, "false", 0, 1, [], {}])
def test_a_payload_that_does_not_declare_intent_only_is_blocked(value: Any) -> None:
    """``True``, a missing field or a wrong type can never become permission."""

    proposal = dict(_R._proposal())
    if value is None:
        proposal.pop("sends_real_order", None)
    else:
        proposal["sends_real_order"] = value

    result, mt5 = _dispatch(_R._controller(None, _R._News()), proposal)

    assert result["success"] is False
    assert SENDS_REAL_ORDER_NOT_FALSE in result["reason_codes"]
    assert mt5.place_calls == []


def test_the_boundary_reads_the_config_file_AS_IT_IS_NOW(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-HC-01: the reload happens at the boundary, not only at scan.

    The controller's ``_active_order_policy`` is deliberately left describing a
    PERMITTED config while the file on disk says otherwise; the boundary must
    report what the FILE says.
    """

    _point_the_loader_at(tmp_path, monkeypatch)
    _write_config(tmp_path, live_order_permitted=False)

    controller = _R._controller(None, _R._News())
    # Stale, and wrong on purpose: the boundary must not consult this.
    controller._active_order_policy = replace(
        DEFAULT_RUNTIME_ORDER_POLICY, live_order_permitted=True
    )

    result, mt5 = _dispatch(controller)

    assert LIVE_ORDER_DISABLED in result["reason_codes"], (
        "the boundary must describe the config on disk, not the stale attribute"
    )
    assert mt5.place_calls == []


def test_the_boundary_sees_a_config_that_changed_after_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-HC-01: flipping the file after the scan changes what the boundary reports."""

    _point_the_loader_at(tmp_path, monkeypatch)
    _write_config(tmp_path, live_order_permitted=False)
    controller = _R._controller(None, _R._News())  # the "scan"

    before, mt5 = _dispatch(controller)
    assert LIVE_ORDER_DISABLED in before["reason_codes"]

    _write_config(tmp_path, live_order_permitted=True)  # changed AFTER the scan
    after, _ = _dispatch(controller)

    assert LIVE_ORDER_DISABLED not in after["reason_codes"], (
        "the boundary must have re-read the changed file"
    )
    assert ORDER_INTENT_ONLY in after["reason_codes"]
    assert mt5.place_calls == [], "and it still must not send"


@pytest.mark.parametrize("broken", ["missing", "not-json", "non-bool"])
def test_a_missing_broken_or_malformed_config_blocks_with_its_own_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    """F-HC-01: a config that cannot be validated closes the boundary.

    There is deliberately no fallback to the policy loaded at scan time.
    """

    _point_the_loader_at(tmp_path, monkeypatch)
    if broken == "not-json":
        (tmp_path / "scanner_order_policy.json").write_text("{", encoding="utf-8")
    elif broken == "non-bool":
        _write_config(tmp_path, live_order_permitted="yes")

    controller = _R._controller(None, _R._News())
    # A perfectly valid stale policy must NOT rescue the request.
    controller._active_order_policy = replace(
        DEFAULT_RUNTIME_ORDER_POLICY, live_order_permitted=True
    )

    result, mt5 = _dispatch(controller)

    assert result["success"] is False and result["blocked"] is True
    assert ORDER_POLICY_UNAVAILABLE in result["reason_codes"]
    assert mt5.place_calls == []


def test_the_policy_is_reloaded_from_the_owner_config_every_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boundary calls the loader itself — it is not carrying a cached copy."""

    import core.scanner_order_policy as policy_module

    loads: list[int] = []
    real = policy_module.load_runtime_order_policy

    def counting(*args: Any, **kwargs: Any):
        loads.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(
        "controllers.scanner_controller.load_runtime_order_policy", counting
    )

    controller = _R._controller(None, _R._News())
    _dispatch(controller)

    assert loads == [1], "exactly one reload per dispatch"


def test_the_boundary_check_precedes_the_single_broker_call() -> None:
    """AST guard: the barrier is written before the ONE dispatch in the method."""

    tree = ast.parse(_CONTROLLER_SOURCE.read_text(encoding="utf-8"))
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "execute_order_candidate":
            target = node
    assert target is not None, "execute_order_candidate must exist"

    order: list[tuple[str, int]] = []
    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "_order_send_boundary_blocks":
                order.append(("boundary", node.lineno))
            elif node.func.attr == "place_market_order":
                order.append(("place", node.lineno))
    order.sort(key=lambda item: item[1])

    names = [name for name, _ in order]
    assert names == ["boundary", "place"], (
        "the send-boundary check must run before the single broker dispatch"
    )


def _xfail_marked(tree: ast.Module) -> set[str]:
    """Test functions/classes under an xfail-style marker (legacy, not live).

    ``_execute_auto_trades`` and its contract tests are marked
    ``xfail(strict=True)`` precisely because they are NOT the execution boundary
    any more; their expectations describe retired behaviour.
    """

    marked: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            continue
        for decorator in node.decorator_list:
            if "xfail" in ast.unparse(decorator) or "LEGACY" in ast.unparse(decorator):
                marked.add(node.name)
                for child in ast.walk(node):
                    if isinstance(child, (ast.FunctionDef, ast.ClassDef)):
                        marked.add(child.name)
    return marked


def test_no_live_test_expects_a_broker_dispatch() -> None:
    """Guard: no runnable test may expect a send that the boundary forbids.

    A successful dispatch is not a reachable outcome in the no-rollout state, so
    a test asserting one would be asserting a path that must not exist yet.
    Tests already marked xfail describe retired behaviour and are excluded — the
    point is that nothing EXPECTED TO PASS expects a send.
    """

    offenders: list[str] = []
    for path in sorted((_PROJECT_ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        marked = _xfail_marked(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name in marked:
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Compare) or len(sub.ops) != 1:
                    continue
                if not isinstance(sub.ops[0], ast.Eq):
                    continue
                operands = [sub.left, *sub.comparators]
                reads_calls = any(
                    getattr(item, "attr", None) == "place_calls" for item in operands
                )
                equals_one = any(
                    isinstance(item, ast.Constant) and item.value == 1
                    for item in operands
                )
                if reads_calls and equals_one:
                    offenders.append(f"{path.name}:{sub.lineno} ({node.name})")

    assert offenders == [], (
        "these runnable tests expect a broker dispatch the boundary forbids: "
        + ", ".join(offenders)
    )


# ---------------------------------------------------------------------------
# F-C-02 — execution clock and tick time
# ---------------------------------------------------------------------------


class _UnknownOffset(tzinfo):
    """A tz whose offset cannot be established (present but unusable)."""

    def utcoffset(self, dt):  # noqa: D102 - test double
        return None

    def dst(self, dt):  # noqa: D102 - test double
        return None

    def tzname(self, dt):  # noqa: D102 - test double
        return None


@pytest.mark.parametrize(
    "value",
    [
        lambda: "2026-08-13T18:00:00Z",
        lambda: 1755100000.0,
        lambda: datetime(2026, 8, 13, 18, 0),
        lambda: datetime(2026, 8, 13, 18, 0, tzinfo=_UnknownOffset(timedelta(0))),
    ],
)
def test_an_unusable_clock_blocks_with_a_typed_code_and_no_invented_stamp(
    value,
) -> None:
    result = revalidate_execution(
        _R._proposal(),
        _R._snapshot(),
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        now=value(),
    )

    assert result.allowed is False
    assert REVALIDATION_CLOCK_INVALID in result.block_codes
    assert result.checked_at is None, "no audit timestamp may be fabricated"
    assert result.to_dict()["checked_at"] is None


def test_an_aware_clock_in_another_offset_is_normalised_not_rejected() -> None:
    """Control: a real instant in +07 is the same instant, and still passes."""

    observed = _EX.NOW

    result = revalidate_execution(
        _EX._proposal(),
        _EX._snapshot(),
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        smc_revalidation=_EX._MATCHING_SMC_REVALIDATION,
        now=observed.astimezone(timezone(timedelta(hours=7))),
    )

    assert result.allowed is True
    assert result.block_codes == ()
    assert result.checked_at == observed


def test_none_uses_the_production_utc_clock() -> None:
    before = datetime.now(timezone.utc)
    result = revalidate_execution(
        _R._proposal(),
        _R._snapshot(),
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        now=None,
    )
    after = datetime.now(timezone.utc)

    assert result.checked_at is not None
    assert before - timedelta(seconds=1) <= result.checked_at <= after + timedelta(
        seconds=1
    )


@pytest.mark.parametrize(
    "value",
    [lambda: "2026-07-24T08:00:00+00:00", lambda: datetime(2026, 7, 24, 8, 0)],
)
def test_an_unusable_tick_time_blocks_with_its_own_code(value) -> None:
    snapshot = replace(_R._snapshot(), tick_time=value())

    result = revalidate_execution(
        _R._proposal(),
        snapshot,
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        now=_R._OBSERVED_AT,
    )

    assert result.allowed is False
    assert TICK_TIME_INVALID in result.block_codes
    assert result.checked_at is not None, "a valid clock is still reported honestly"


def test_an_aware_tick_in_another_offset_is_accepted() -> None:
    snapshot = replace(
        _EX._snapshot(),
        tick_time=_EX.NOW.astimezone(timezone(timedelta(hours=7))),
    )

    result = revalidate_execution(
        _EX._proposal(),
        snapshot,
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        smc_revalidation=_EX._MATCHING_SMC_REVALIDATION,
        now=_EX.NOW,
    )

    assert result.allowed is True


def test_no_exception_escapes_the_boundary() -> None:
    """Whatever is injected, the engine returns a verdict instead of raising."""

    for bad in ("2026-08-13T18:00:00Z", 1755100000.0, datetime(2026, 8, 13, 18, 0)):
        result = revalidate_execution(
            _R._proposal(),
            replace(_R._snapshot(), tick_time=bad),
            news_blackout=False,
            account_allowed=True,
            portfolio_allowed=True,
            now=bad,
        )
        assert result.allowed is False
        assert result.block_codes


def test_an_unusable_clock_blocks_the_real_dispatch_and_sends_nothing() -> None:
    """Through the controller: the boundary returns a verdict, never an exception.

    The adapter the fetch uses must also turn an unusable timestamp into a
    fail-closed stamp rather than raising into the row.
    """

    mt5 = _R._MT5()
    controller = _R._controller(mt5, _R._News())

    result = controller.execute_order_candidate(_R._proposal())

    # The fixture's clock is aware, so the revalidation verdict is unaffected —
    # and the request still stops at the send boundary, nothing is sent.
    assert result["revalidation"]["allowed"] is True
    assert result["blocked"] is True
    assert mt5.place_calls == []


# ---------------------------------------------------------------------------
# F-C-02 — safety context timestamps
# ---------------------------------------------------------------------------


def _safety_context(**overrides: Any):
    from core.scanner_live_producers import build_live_market_safety_context

    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    arguments: dict[str, Any] = {
        "symbol": "EURUSD",
        "captured_at": now,
        "terminal_connected": True,
        "broker_logged_in": True,
        "connectivity_checked_at": now,
        "last_candle_time_utc": now,
        "last_tick_time_utc": None,
        "spread_points": 5.0,
        "spread_checked_at": now,
        "news_source_verified": True,
        "news_checked_at": now,
        "volatility_ratio": 1.0,
        "volatility_checked_at": now,
        "connectivity_max_age_minutes": 5,
        "max_candle_age_minutes": 3,
    }
    arguments.update(overrides)
    return build_live_market_safety_context(**arguments), now


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-17T12:00:00+00:00",
        datetime(2026, 9, 17, 12, 0),
    ],
)
def test_an_unusable_candle_time_becomes_a_fail_closed_verdict(value: Any) -> None:
    """Naive / non-datetime must not raise ``TypeError`` out of the producer."""

    from core.market_safety_gate import MarketSafetyGate
    from core.reason_codes import SAFETY_DATA_FRESHNESS_UNKNOWN

    context, now = _safety_context(last_candle_time_utc=value)
    policy = load_runtime_order_policy().safety

    result = MarketSafetyGate().evaluate(context, policy, now=now)

    assert result.status == "UNKNOWN"
    assert SAFETY_DATA_FRESHNESS_UNKNOWN in result.reason_codes


def test_a_healthy_safety_context_still_passes() -> None:
    """Control: the guard did not change the valid path."""

    from core.market_safety_gate import MarketSafetyGate

    context, now = _safety_context()
    policy = load_runtime_order_policy().safety

    result = MarketSafetyGate().evaluate(context, policy, now=now)

    assert result.status == "PASS"


def test_an_aware_candle_in_another_offset_is_still_fresh() -> None:
    """A real instant in +07 is the same instant, so it is not aged away."""

    from core.market_safety_gate import MarketSafetyGate

    context, now = _safety_context(
        last_candle_time_utc=now_in_offset_7()
    )
    policy = load_runtime_order_policy().safety

    result = MarketSafetyGate().evaluate(context, policy, now=now)
    assert result.status == "PASS"


def now_in_offset_7() -> datetime:
    return datetime(2026, 9, 17, 19, 0, tzinfo=timezone(timedelta(hours=7)))


def test_a_naive_candle_stamps_the_source_fail_closed() -> None:
    """The adapter behind the producer must not raise on an unusable instant."""

    from core.market_safety_gate import AVAILABILITY_MISSING, AVAILABILITY_VALID
    from core.scanner_live_producers import _mark_availability

    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)

    # Control: a real instant is aged normally and stays usable.
    assert _mark_availability(True, now, now, 3) == AVAILABILITY_VALID
    # Naive / non-datetime: fail closed, and never by raising TypeError.
    assert (
        _mark_availability(True, datetime(2026, 9, 17, 12, 0), now, 3)
        == AVAILABILITY_MISSING
    )
    assert (
        _mark_availability(True, "2026-09-17T12:00:00+00:00", now, 3)
        == AVAILABILITY_MISSING
    )
    # A non-UTC offset is a real instant and is still aged normally.
    assert (
        _mark_availability(
            True, now.astimezone(timezone(timedelta(hours=7))), now, 3
        )
        == AVAILABILITY_VALID
    )


# ---------------------------------------------------------------------------
# P10 / M15 — characterisation of BOTH max-run branches
#
# Tech Lead decision: the maximum-run guard (0.50 x ATR) stays in force BOTH
# before the trigger and after the confirmation; the documentation is what was
# out of step.  These lock the two branches as they really are, and assert the
# guard never touches B/Q/L/C, quality or selection.
# ---------------------------------------------------------------------------


_M15 = pytest.importorskip("tests.test_smc_m15_confirmation_task79")
_Q88 = pytest.importorskip("tests.test_smc_quality_task88")

_BUY_ZONE = (90.0, 95.0)


def _m15(candles, **kwargs):
    return _M15._evaluate(
        "buy", _BUY_ZONE[0], _BUY_ZONE[1], candles, zone_id=_M15._ZONE_ID, **kwargs
    )


def test_the_confirmed_control_still_confirms() -> None:
    result = _m15(_M15._micro_break_candles())

    assert result.status == "confirmed"
    assert "M15_ENTRY_TOO_FAR" not in result.reason_codes


def test_max_run_applies_BEFORE_the_trigger() -> None:
    """Pre-trigger branch: a visited-but-unconfirmed zone whose price ran away."""

    result = _m15(_M15._unconfirmed_level_candles())

    assert result.status == "waiting"
    assert "M15_NO_CONFIRMATION" in result.reason_codes
    assert "M15_ENTRY_TOO_FAR" in result.reason_codes


def test_max_run_applies_AFTER_the_confirmation() -> None:
    """Post-confirmation branch: a confirmed setup invalidated by running away."""

    result = _m15(
        _M15._micro_break_candles(extra=[(96.9, 120.0, 96.8, 119.0)])
    )

    assert result.status == "invalidated"
    assert result.reason_codes == ("M15_ENTRY_TOO_FAR",)


@pytest.mark.parametrize(
    "window",
    [None, "far", "absent"],
)
def test_the_max_run_guard_never_touches_quality(window: Any) -> None:
    """Same candidate, different M15 window: B/Q/L/C and quality are identical."""

    from core.smc_quality import evaluate_candidate_sets

    candles = _M15._unconfirmed_level_candles()
    as_of = _M15._close_at(candles[-1])

    if window is None:
        arguments: dict[str, Any] = {"m15_candles": None}
    elif window == "far":
        arguments = {"m15_candles": candles, "m15_as_of": as_of}
    else:
        arguments = {}

    evaluated = evaluate_candidate_sets(
        _Q88._context(_Q88._zone()), _Q88._technical(), as_of=_Q88._AS_OF, **arguments
    )["buy"]

    baseline = evaluate_candidate_sets(
        _Q88._context(_Q88._zone()), _Q88._technical(), as_of=_Q88._AS_OF
    )["buy"]

    if window == "far":
        # The window must REALLY change the readiness verdict, otherwise the
        # quality comparison below would be true for a trivial reason.
        assert (
            evaluated.candidates[0].m15_status,
            evaluated.candidates[0].confirmation_state,
        ) != (
            baseline.candidates[0].m15_status,
            baseline.candidates[0].confirmation_state,
        )

    assert evaluated.candidates[0].quality.to_dict() == (
        baseline.candidates[0].quality.to_dict()
    )
    assert evaluated.quality == baseline.quality
