"""Lô B-Ctx (D-LB-01) — canonical CONTEXT cache at the snapshot seam.

What is cached: the canonical context the expensive builder produces, keyed by
the frozen raw input identity.  What is NOT cached: the evaluation.  Every
request still runs ``evaluate_smc_snapshot`` → coordinator → finalizer fresh and
gets a real typed evaluation; a hit only skips the context build.

The suite locks the contract in three directions:

* **identity** — pre-context, and sensitive to every raw input the builder
  really reads (candles incl. a broker correction, cutoff, symbol, tick size,
  tick source, scan interval, builder identity);
* **hit** — the builder is not called again, the evaluator still is, and the
  whole verdict is identical to the fresh path, through the REAL Scanner caller;
* **miss/fail-closed** — corrupt, wrong version, wrong key, wrong input or an
  incomplete payload never yields a context, and a failing write never changes
  the verdict.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from core.smc_context_cache import (
    SMC_CONTEXT_MISS_ABSENT,
    SMC_CONTEXT_MISS_CONTEXT_INVALID,
    SMC_CONTEXT_MISS_IDENTITY_MISMATCH,
    SMC_CONTEXT_MISS_KEY_MISMATCH,
    SMC_CONTEXT_MISS_RECORD_CORRUPTED,
    SMC_CONTEXT_MISS_VERSION_INVALID,
    SMC_CONTEXT_CACHE_VERSION,
    caching_context_builder,
    context_builder_identity,
    context_identity,
    read_smc_context_record,
    smc_context_cache_path,
    write_smc_context_record,
)
from core.scanner_live_producers import derive_live_analysis

_il = importlib
_T113 = importlib.import_module("tests.test_smc_consumer_contract_task113")

_TICK_SOURCE = "broker"


def _case() -> dict[str, Any]:
    return _T113._case("ob_confirmed_sell")


def _inputs() -> tuple[Any, Any, Any, Any, Any]:
    case = _case()
    candles = _T113._candles(case)
    cutoff = _T113._cutoff(candles)
    return candles["D1"], candles["H4"], candles["H1"], cutoff, case


def _identity(
    *,
    d1: Any = None,
    h4: Any = None,
    h1: Any = None,
    cutoff: Any = None,
    tick_size: Any = None,
    scan_interval_min: int = 15,
    tick_size_source: str = _TICK_SOURCE,
    builder: Any = None,
) -> str:
    base_d1, base_h4, base_h1, base_cutoff, case = _inputs()
    return context_identity(
        symbol=str(case["symbol"]),
        as_of=base_cutoff if cutoff is None else cutoff,
        candles_by_timeframe={
            "D1": base_d1 if d1 is None else d1,
            "H4": base_h4 if h4 is None else h4,
            "H1": base_h1 if h1 is None else h1,
        },
        tick_size=float(case["tick_size"]) if tick_size is None else tick_size,
        scan_interval_min=scan_interval_min,
        builder=builder,
        extra_metadata={"tick_size_source": tick_size_source},
    )


class _Counters(dict):
    """Call tally for the seam and for the real producer it wraps."""

    def bump(self, name: str) -> None:
        self[name] = int(self.get(name, 0)) + 1


# ---------------------------------------------------------------------------
# Identity: pre-context, and bound to every real input
# ---------------------------------------------------------------------------


def test_the_identity_is_deterministic_and_pre_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Computing the key needs no context — and never builds one to get it."""

    import core.smc_canonical_context as context_module

    built = _Counters()
    real = context_module.build_canonical_smc_context
    monkeypatch.setattr(
        context_module,
        "build_canonical_smc_context",
        lambda *a, **k: (built.bump("build"), real(*a, **k))[1],
    )

    first = _identity()
    second = _identity()

    assert first == second
    assert not built, "identifying the input must not build the context"


@pytest.mark.parametrize(
    "changed",
    [
        {"tick_size": 0.02},
        {"scan_interval_min": 30},
        {"tick_size_source": "point"},
        {"builder": lambda *a, **k: {}},
    ],
)
def test_the_identity_covers_every_builder_input(changed: dict[str, Any]) -> None:
    """A different tick rule, interval, provenance or builder is a different key."""

    assert _identity(**changed) != _identity()


@pytest.mark.parametrize("index", [0, 1])
def test_a_candle_correction_changes_the_identity(index: int) -> None:
    """A broker correction cannot reuse the context built before it."""

    d1, h4, h1, cutoff, _case_payload = _inputs()
    corrected = list(d1)
    corrected[index] = replace(corrected[index], close=corrected[index].close + 0.0001)

    assert _identity(d1=corrected) != _identity(d1=d1)


def test_a_different_cutoff_changes_the_identity() -> None:
    """The cutoff is part of the frozen input, not an afterthought."""

    from datetime import timedelta

    d1, h4, h1, cutoff, _case_payload = _inputs()
    assert _identity(cutoff=cutoff - timedelta(hours=1)) != _identity()
    assert _identity(cutoff=cutoff - timedelta(days=1)) != _identity()


def test_the_builder_identity_is_part_of_the_key() -> None:
    """Two builders never share a cached context."""

    assert context_builder_identity() != context_builder_identity(lambda *a, **k: {})


# ---------------------------------------------------------------------------
# Positive: hit skips the builder, never the evaluator
# ---------------------------------------------------------------------------


def _derive(root: Path | None, **overrides: Any):
    d1, h4, h1, cutoff, case = _inputs()
    candles = _T113._candles(case)
    kwargs: dict[str, Any] = {
        "symbol": str(case["symbol"]),
        "captured_at": cutoff,
        "m15_candles": candles["M15"],
        "m15_as_of": cutoff,
        "tick_size": float(case["tick_size"]),
        "tick_size_source": _TICK_SOURCE,
        "context_cache_root": root,
    }
    kwargs.update(overrides)
    return derive_live_analysis(d1, h4, h1, **kwargs)


def _instrument(monkeypatch: pytest.MonkeyPatch) -> _Counters:
    """Count the real context build and the real evaluation."""

    import core.smc_canonical_context as context_module
    import core.smc_snapshot as snapshot_module

    tally = _Counters()
    real_context = context_module.build_canonical_smc_context
    real_evaluate = snapshot_module.evaluate_smc_snapshot
    monkeypatch.setattr(
        context_module,
        "build_canonical_smc_context",
        lambda *a, **k: (tally.bump("context"), real_context(*a, **k))[1],
    )
    monkeypatch.setattr(
        snapshot_module,
        "evaluate_smc_snapshot",
        lambda *a, **k: (tally.bump("evaluate"), real_evaluate(*a, **k))[1],
    )
    return tally


def test_a_hit_skips_the_context_build_but_not_the_evaluation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two identical requests: one context build, two real evaluations."""

    tally = _instrument(monkeypatch)

    first = _derive(tmp_path)
    second = _derive(tmp_path)

    assert tally["context"] == 1, "the canonical context must be built once"
    assert tally["evaluate"] == 2, "the evaluator must run fresh every request"
    assert first["canonical_smc"].to_dict() == second["canonical_smc"].to_dict()


def test_without_a_root_the_builder_runs_every_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control: the saving above is the cache, not a coincidence of the fixture."""

    tally = _instrument(monkeypatch)
    _derive(None)
    _derive(None)

    assert tally["context"] == 2
    assert tally["evaluate"] == 2


def test_the_cached_request_still_produces_a_typed_evaluation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A context hit yields a REAL evaluation — nothing is reconstructed."""

    from core.smc_scoring_result import SmcScoringResult
    from core.smc_snapshot import SmcSnapshotEvaluation

    _instrument(monkeypatch)
    _derive(tmp_path)
    hit = _derive(tmp_path)

    evaluation = hit["smc_evaluation"]
    assert isinstance(evaluation, SmcSnapshotEvaluation)
    assert isinstance(evaluation.result, SmcScoringResult)
    assert sorted(evaluation.candidate_sets) == ["buy", "sell"]
    assert sorted(evaluation.selections) == ["buy", "sell"]
    assert evaluation.selection("sell") is not None


def test_the_cached_verdict_matches_the_fresh_path_field_by_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Result, B/Q/L/C, reasons, confirmation and plan are identical."""

    _instrument(monkeypatch)
    fresh = _derive(None)
    _derive(tmp_path)
    cached = _derive(tmp_path)

    left = fresh["canonical_smc"].to_dict()
    right = cached["canonical_smc"].to_dict()
    assert left == right

    for side in ("buy", "sell"):
        a = fresh["smc_evaluation"].result.side(side)
        b = cached["smc_evaluation"].result.side(side)
        assert a.to_dict() == b.to_dict()
        assert a.selection is not None and b.selection is not None
        assert a.selection.b == b.selection.b
        assert a.selection.q == b.selection.q
        assert a.selection.l == b.selection.l
        assert a.selection.c == b.selection.c
        assert a.selection.total == b.selection.total
        assert a.selection.plan == b.selection.plan
        assert a.selection.confirmation == b.selection.confirmation
        assert a.selection.selection_reason_codes == b.selection.selection_reason_codes
        assert a.selection.readiness == b.selection.readiness


def test_the_cached_path_reaches_the_chart_and_the_consumer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Storage → new instance → arrival at the consumer boundary, unchanged."""

    from core.chart_payload import build_smc_overlay
    from core.scanner_release import run_pair_from_live
    from core.scanner_ui_adapter import pair_to_ui_row

    _instrument(monkeypatch)
    d1, h4, h1, cutoff, case = _inputs()
    safety = _T113._safety(str(case["symbol"]), cutoff)

    fresh_analysis = _derive(None)
    _derive(tmp_path)
    cached_analysis = _derive(tmp_path)

    def _row(analysis: dict[str, Any]) -> dict[str, Any]:
        from core.smc_consumer_contract import build_smc_consumer_from_canonical_result
        from core.smc_persistence import build_smc_persistence_block

        pair = run_pair_from_live(
            d1, h4, h1, str(case["symbol"]), safety,
            now=cutoff, captured_at=cutoff, analysis=analysis,
        )
        row = pair_to_ui_row(pair, technical=analysis["technical"])
        # The live controller attaches the canonical block beside the summary
        # (``scanner_controller.py``); the read boundary refuses a carrier
        # without it, so the row must carry both exactly as production does.
        canonical = analysis["canonical_smc"]
        row["analysis_result"]["smc_scoring"] = build_smc_persistence_block(
            canonical,
            build_smc_consumer_from_canonical_result(result=canonical),
            snapshot=analysis["smc_snapshot"],
        )
        return row

    fresh_overlay = build_smc_overlay(_row(fresh_analysis)["analysis_result"])
    cached_overlay = build_smc_overlay(_row(cached_analysis)["analysis_result"])

    assert cached_overlay == fresh_overlay
    assert cached_overlay["available"] is True
    assert cached_overlay["timeframes"], "the chart must still get its SMC layers"


def test_a_new_instance_reads_the_same_context_after_a_restart(tmp_path: Path) -> None:
    """The bytes on disk are the whole state: a fresh wrapper hits them."""

    d1, h4, h1, cutoff, case = _inputs()
    kwargs = dict(
        symbol=str(case["symbol"]),
        as_of=cutoff,
        tick_size=float(case["tick_size"]),
    )
    extra = {"tick_size_source": _TICK_SOURCE}

    first = _Counters()
    caching_context_builder(root=tmp_path, counters=first, extra_metadata=extra)(
        d1, h4, h1, **kwargs
    )
    assert first.get("built") == 1 and first.get("hit") is None

    # A brand-new wrapper over the same root is the "restart": nothing from the
    # writing call is carried over except the bytes.
    restarted = _Counters()
    reused = caching_context_builder(root=tmp_path, counters=restarted, extra_metadata=extra)(
        d1, h4, h1, **kwargs
    )

    assert restarted.get("hit") == 1
    assert restarted.get("built") is None
    assert reused["D1"] and reused["H4"] and reused["H1"]


# ---------------------------------------------------------------------------
# Negative: nothing is served unless it is exactly this input's context
# ---------------------------------------------------------------------------


def _store(root: Path, context: dict[str, Any], identity: str | None = None) -> str:
    """Write an envelope directly, so even an unusable payload can be read back."""

    import gzip
    import json

    from core.smc_persistence import smc_persistence_identity

    key = identity or _identity()
    path = smc_context_cache_path(root, context_identity=key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(
            {
                "cache_contract_version": SMC_CONTEXT_CACHE_VERSION,
                "cache_identity": smc_persistence_identity(),
                "context_identity": key,
                "context": context,
            },
            handle,
        )
    return key


def _read(root: Path, identity: str) -> Any:
    d1, h4, h1, cutoff, case = _inputs()
    return read_smc_context_record(
        root, context_identity=identity, symbol=str(case["symbol"]), as_of=cutoff
    )


def test_an_absent_record_is_a_normal_miss(tmp_path: Path) -> None:
    assert _read(tmp_path, _identity()).reason_codes == (SMC_CONTEXT_MISS_ABSENT,)


def test_corrupted_bytes_never_yield_a_context(tmp_path: Path) -> None:
    identity = _store(tmp_path, {"D1": {}, "H4": {}, "H1": {}, "symbol": "x", "as_of": "y",
                                "domain_version": "d", "contract_version": "c"})
    smc_context_cache_path(tmp_path, context_identity=identity).write_bytes(b"not gzip")

    lookup = _read(tmp_path, identity)
    assert not lookup.usable
    assert lookup.reason_codes == (SMC_CONTEXT_MISS_RECORD_CORRUPTED,)


def test_another_cache_contract_version_is_refused(tmp_path: Path) -> None:
    import gzip
    import json

    identity = _identity()
    path = smc_context_cache_path(tmp_path, context_identity=identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump({"cache_contract_version": "smc-context-cache-v0",
                   "context_identity": identity, "context": {}}, handle)

    assert _read(tmp_path, identity).reason_codes == (SMC_CONTEXT_MISS_VERSION_INVALID,)


def test_another_rule_identity_is_refused(tmp_path: Path) -> None:
    import gzip
    import json

    identity = _identity()
    path = smc_context_cache_path(tmp_path, context_identity=identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump({"cache_contract_version": SMC_CONTEXT_CACHE_VERSION,
                   "cache_identity": {"rule_identity": "other"},
                   "context_identity": identity, "context": {}}, handle)

    lookup = _read(tmp_path, identity)
    assert not lookup.usable
    assert lookup.reason_codes == (SMC_CONTEXT_MISS_IDENTITY_MISMATCH,)
    assert lookup.identity_mismatch_codes


def test_a_record_written_for_another_input_is_refused(tmp_path: Path) -> None:
    import gzip
    import json

    identity = _identity()
    path = smc_context_cache_path(tmp_path, context_identity=identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    from core.smc_persistence import smc_persistence_identity

    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump({"cache_contract_version": SMC_CONTEXT_CACHE_VERSION,
                   "cache_identity": smc_persistence_identity(),
                   "context_identity": "another-input", "context": {}}, handle)

    assert _read(tmp_path, identity).reason_codes == (SMC_CONTEXT_MISS_KEY_MISMATCH,)


@pytest.mark.parametrize(
    "context",
    [
        {},  # empty
        {"D1": {}, "H4": {}, "H1": {}},  # no version/symbol/as_of
        {"D1": {}, "H4": {}, "H1": {}, "domain_version": "d",
         "contract_version": "c", "symbol": "OTHER", "as_of": "2026-01-01T00:00:00+00:00"},
        {"D1": {}, "H4": {}, "H1": {}, "domain_version": "d",
         "contract_version": "c", "symbol": "EUR/USD"},
    ],
)
def test_an_incomplete_context_is_refused(tmp_path: Path, context: dict[str, Any]) -> None:
    identity = _store(tmp_path, context)
    assert _read(tmp_path, identity).reason_codes == (SMC_CONTEXT_MISS_CONTEXT_INVALID,)


def test_a_corrected_candle_is_a_miss_and_rebuilds_fresh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A correction after the cache was written must not reuse the old context."""

    tally = _instrument(monkeypatch)
    _derive(tmp_path)
    assert tally["context"] == 1

    d1, h4, h1, cutoff, case = _inputs()
    corrected = list(d1)
    corrected[-1] = replace(corrected[-1], close=corrected[-1].close + 0.0001)
    candles = _T113._candles(case)
    rebuild = derive_live_analysis(
        corrected, h4, h1, symbol=str(case["symbol"]), captured_at=cutoff,
        m15_candles=candles["M15"], m15_as_of=cutoff,
        tick_size=float(case["tick_size"]), tick_size_source=_TICK_SOURCE,
        context_cache_root=tmp_path,
    )

    assert tally["context"] == 2, "a corrected candle must rebuild the context"
    assert rebuild["canonical_smc"] is not None


def test_a_corrupt_record_rebuilds_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Corruption costs a rebuild, never an error and never a stale context."""

    tally = _instrument(monkeypatch)
    _derive(tmp_path)
    for path in (tmp_path / "cache" / "smc_context").glob("*.json.gz"):
        path.write_bytes(b"corrupted")

    again = _derive(tmp_path)

    assert tally["context"] == 2
    assert again["canonical_smc"] is not None


def test_a_failing_write_never_changes_the_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cache problem must not turn a correct context into an error."""

    import core.smc_context_cache as cache_module

    _instrument(monkeypatch)
    monkeypatch.setattr(
        cache_module,
        "write_smc_context_record",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = _derive(tmp_path)
    fresh = _derive(None)

    assert result["canonical_smc"].to_dict() == fresh["canonical_smc"].to_dict()
    assert list((tmp_path / "cache" / "smc_context").glob("*.json.gz")) == []


def test_a_hit_without_a_record_is_never_served(tmp_path: Path) -> None:
    """A warm directory with another input's record still rebuilds."""

    _store(tmp_path, {"D1": {}, "H4": {}, "H1": {}, "domain_version": "d",
                      "contract_version": "c", "symbol": "X", "as_of": "2026-01-01T00:00:00+00:00"})

    tally = _Counters()
    builder = caching_context_builder(
        root=tmp_path, counters=tally, extra_metadata={"tick_size_source": _TICK_SOURCE}
    )
    d1, h4, h1, cutoff, case = _inputs()
    builder(d1, h4, h1, symbol=str(case["symbol"]), as_of=cutoff,
            tick_size=float(case["tick_size"]))

    assert tally.get("miss") == 1
    assert tally.get("built") == 1


# ---------------------------------------------------------------------------
# Revalidation / dispatch bypass, and the Analyze decision
# ---------------------------------------------------------------------------


def test_the_revalidation_boundary_does_not_use_the_context_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatch always freezes a fresh snapshot; the cache is never consulted.

    The dispatch path imports the producer locally inside the method, so this is
    proved at the seam that would have to be consulted anyway: with a warm cache
    root configured for the LIVE path, a revalidation still neither reads nor
    writes the context cache.
    """

    import controllers.scanner_controller as scanner_module
    import core.smc_context_cache as cache_module

    _R111 = _il.import_module("tests.test_smc_execution_revalidation_task111")

    touched: list[str] = []
    monkeypatch.setattr(
        cache_module,
        "read_smc_context_record",
        lambda *a, **k: (touched.append("read"), None)[1],
    )
    monkeypatch.setattr(
        cache_module,
        "write_smc_context_record",
        lambda *a, **k: (touched.append("write"), None)[1],
    )

    order = {
        "symbol": "XAUUSD",
        "smc_zone_id": "smcz-approved",
        "smc_setup_id": "smcs-approved",
    }
    comparison = _R111._call(order)

    assert touched == [], "the dispatch boundary must not touch the context cache"
    assert comparison is not None
    assert comparison["source"] == "fresh_canonical_snapshot"

    # ... and the source proves why: this call site never asks for the cache.
    source = inspect.getsource(
        scanner_module.ScannerController._smc_revalidation_for_order
    )
    assert "context_cache_root" not in source


def test_the_live_scan_path_is_the_only_production_wiring() -> None:
    """The Analyze route has no runtime caller, so no cache is wired into it.

    A hidden/global cache would be worse than none: analyze_symbol() and
    AnalysisPipeline are reachable only from scripts and tests today, so the
    seam is deliberately wired at the ONE live caller that can inject a root.
    """

    import inspect

    import core.analysis_engine as engine_module
    import core.analysis_pipeline as pipeline_module

    for module in (engine_module, pipeline_module):
        source = inspect.getsource(module)
        assert "smc_context_cache" not in source
        assert "context_cache_root" not in source


@pytest.mark.parametrize(
    "symbol",
    [
        "read_canonical_selection",
        "canonical_selection_of",
        "scenario_preferred_zone_for_side",
        "selected_zone_for_side",
        "selection_payload_for_side",
        "legacy_zone_for_side",
    ],
)
def test_the_compatibility_adapters_are_untouched(symbol: str) -> None:
    """Lô B reviewed them and removed nothing; Lô B-Ctx must not change that."""

    import core.smc_consumer_contract as contract_module
    import core.smc_persistence as persistence_module

    assert hasattr(contract_module, symbol) or hasattr(persistence_module, symbol)


# ---------------------------------------------------------------------------
# F-BCTX-01 — the REAL Scanner workflow has no reuse, so production wiring is off
# ---------------------------------------------------------------------------


def _scan_packet(symbol: str, broker_symbol: str, cutoff: Any) -> dict[str, Any]:
    """A packet shaped exactly like ``_fetch_one_symbol_mt5`` returns.

    The candles are the repo's real live fixtures; the cutoff is the one the
    scan froze (``capture_cutoff``), so the packet is faithful to production in
    everything that feeds the context identity.
    """

    from tests.test_scanner_release import _zoned_candles

    d1, h4, h1 = _zoned_candles()
    m15 = list(h1[-20:])
    return {
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "candles": {"D1": d1, "H4": h4, "H1": h1, "M15": m15},
        "m15_candles": m15,
        "data_quality": {"tick_size": 0.01, "tick_size_source": "trade_tick_size"},
        "macro_context": {},
        "v4_safety": _T113._safety(symbol, cutoff),
        "v4_captured_at": cutoff,
        "location_cutoff": cutoff,
        "account": None,
        "portfolio": None,
        "journal": None,
    }


def _run_real_scans(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    scans: int,
    inject_root: Path | None = None,
) -> tuple[list[dict[str, Any]], _Counters]:
    """Drive ``run_market_scan`` with the REAL analysis path.

    Only the MT5 candle source is faked; ``_analyze_one_symbol``,
    ``derive_live_analysis`` and the whole canonical chain run for real.  The
    runtime root is redirected to ``tmp_path`` so the user's directory is never
    touched, and the seam is counted through its own read/write entry points.
    """

    import controllers.scanner_controller as scanner_module
    import core.smc_context_cache as cache_module
    from tests.test_scanner_performance import _mocked_controller, _request

    monkeypatch.setattr(scanner_module, "app_data_dir", lambda: tmp_path)

    tally = _Counters()

    def fake_fetch(symbol, mt5, available_symbols, bars_by_timeframe, news_service,
                   freshness, **kwargs):
        cutoff = kwargs.get("capture_cutoff")
        tally.bump("fetch")
        return _scan_packet(symbol, "EURUSD", cutoff)

    monkeypatch.setattr(scanner_module, "_fetch_one_symbol_mt5", fake_fetch)

    # Prove the seam is not merely idle but absent: it must never even be built.
    real_caching_builder = cache_module.caching_context_builder
    monkeypatch.setattr(
        cache_module,
        "caching_context_builder",
        lambda **k: (tally.bump("builder_constructed"), real_caching_builder(**k))[1],
    )

    # ... and that the analysis really ran, so the scan is not short-circuiting.
    real_derive = scanner_module.derive_live_analysis
    monkeypatch.setattr(
        scanner_module,
        "derive_live_analysis",
        lambda *a, **k: (tally.bump("derive"), real_derive(*a, **k))[1],
    )

    real_read = cache_module.read_smc_context_record
    real_write = cache_module.write_smc_context_record

    def counted_read(*a, **k):
        tally.bump("read")
        return real_read(*a, **k)

    def counted_write(*a, **k):
        tally.bump("write")
        return real_write(*a, **k)

    monkeypatch.setattr(cache_module, "read_smc_context_record", counted_read)
    monkeypatch.setattr(cache_module, "write_smc_context_record", counted_write)

    if inject_root is not None:
        # Test instrumentation ONLY: pretend a caller injected the seam, to show
        # what the workflow would do if it were wired.  Production does not.
        real_analyze = scanner_module._analyze_one_symbol

        def analyze_with_root(pkt, **kwargs):
            kwargs["context_cache_root"] = inject_root
            return real_analyze(pkt, **kwargs)

        monkeypatch.setattr(scanner_module, "_analyze_one_symbol", analyze_with_root)

    controller = _mocked_controller(tmp_path)
    outputs = [controller.run_market_scan(request=_request()) for _ in range(scans)]
    return outputs, tally


def test_the_real_scan_workflow_writes_no_context_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """F-BCTX-01 (2): production wiring is gone — a scan must leave no cache.

    ``history_cutoff`` is ``now(UTC)`` fresh per scan and each symbol is
    analysed once, so nothing can hit; writing records nobody reads into a
    directory retention does not cover is exactly what was removed.
    """

    outputs, tally = _run_real_scans(monkeypatch, tmp_path, scans=2)

    assert tally.get("fetch") == 2, "both scans must really have fetched"
    assert tally.get("derive") == 2, "both scans must really have analysed a symbol"
    assert tally.get("builder_constructed") is None, (
        "the live scan must not even build the caching seam"
    )
    assert tally.get("read") is None, "the live scan must not consult the cache"
    assert tally.get("write") is None, "the live scan must not write the cache"
    assert not (tmp_path / "cache" / "smc_context").exists()
    assert all(output.get("rows") is not None for output in outputs)


def test_even_when_wired_the_scan_workflow_never_hits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """F-BCTX-01 (1): no two real scans share a (symbol, cutoff, candles) key.

    This reproduces the diagnosis with the seam forced on: the workflow still
    produces zero hits and writes one record per scan, because the cutoff is new
    every scan.  It is the evidence for removing the wiring rather than keeping
    it with a retention policy.
    """

    import core.smc_context_cache as cache_module

    hits: list[str] = []
    real_builder = cache_module.caching_context_builder

    def counting_builder(*, root, **kwargs):
        counters = kwargs.setdefault("counters", {})
        wrapper = real_builder(root=root, **kwargs)

        def wrapped(*a, **k):
            result = wrapper(*a, **k)
            hits.append("hit" if counters.get("hit") else "miss")
            return result

        return wrapped

    monkeypatch.setattr(cache_module, "caching_context_builder", counting_builder)
    cache_root = tmp_path / "injected"
    outputs, tally = _run_real_scans(
        monkeypatch, tmp_path, scans=2, inject_root=cache_root
    )

    assert hits.count("hit") == 0, "two real scans must never share a key"
    assert hits.count("miss") == 2
    written = list((cache_root / "cache" / "smc_context").glob("*.json.gz"))
    assert len(written) == 2, "one unread record per scan is what was removed"
    assert all(output.get("rows") is not None for output in outputs)
