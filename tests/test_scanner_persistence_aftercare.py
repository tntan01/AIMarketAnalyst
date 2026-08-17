"""Phase 5 — persistence aftercare and bounded shutdown.

Covers: compact-summary-first ordering, atomic writes, the persistence delta
contract, snapshot replay, legacy-schema backward compatibility and the
app-closes-mid-scan flow (bounded wait + interrupted job marker, no data
lost/corrupted).
"""

from __future__ import annotations

import gzip
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import controllers.scanner_controller as scanner_module
from controllers.scanner_controller import ScannerController
from core.scanner import ScannerRequest, blocked_scanner_row, build_scanner_output
from core.scanner_candidate_engine import (
    build_candidate_order_payload,
    evaluate_scanner_candidate,
)
from core.scanner_observability import (
    attach_row_observability,
    create_scan_context,
    replay_candidate_decision,
)
from core.scanner_ranking_engine import rank_scanner_rows
from services.runtime_retention_service import RuntimeRetentionService
from services.scanner_job_state import ScannerJobState
from services.scanner_persistence_service import atomic_json_save


# ---------------------------------------------------------------------------
# Fixtures: a full observed row (candidate decision + observability) and a
# minimal controller wired to a temporary runtime root.
# ---------------------------------------------------------------------------


def _scenario(side: str) -> dict:
    return {
        "type": side,
        "entry_zone": [1.0850, 1.0875],
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "m15_quality": "strict",
        "stop_loss": 1.0820 if side == "buy" else 1.0910,
        "take_profit": [1.0940] if side == "buy" else [1.0800],
        "expected_effective_rr": 2.0 if side == "buy" else 1.6,
    }


def _row(symbol: str = "EUR/USD") -> dict:
    return {
        "symbol": symbol,
        "broker_symbol": symbol.replace("/", ""),
        "best_side": "buy",
        "buy_score": 78,
        "sell_score": 61,
        "best_score": 78,
        "setup_score": 72,
        "final_score": 72,
        "min_score": 65,
        "min_rr": 1.3,
        "market_regime": "range",
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "scanner_group": "ready_now",
        "trade_permission": "allowed",
        "price_vs_zone": "in_zone",
        "direction_bias": {
            "best_side": "buy",
            "score_gap": 17,
            "is_clear_bias": True,
            "min_gap": 10,
        },
        "score_gap": 17,
        "analysis_result": {
            "timestamp": "2026-07-24T08:00:00+00:00",
            "side_scores": {
                "buy": {"signal_score": 78, "setup_score": 72},
                "sell": {"signal_score": 61, "setup_score": 64},
            },
            "scenario_scores": {
                "buy": {"signal_score": 78},
                "sell": {"signal_score": 61},
            },
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "trade_gate": {"allowed": True, "block_codes": []},
            "data_quality": {
                "spread_status": "normal",
                "terminal_connected": True,
                "broker_logged_in": True,
                "macro_freshness": {"confidence_multiplier": 1.0},
            },
            "technical": {"price": 1.0860},
            "scenarios": [_scenario("buy"), _scenario("sell")],
            "final_score_detail": {
                "final_score": 72,
                "weighted_components": {"signal": 40},
            },
        },
        "input_timestamps": {
            "D1": "2026-07-23T00:00:00+00:00",
            "H4": "2026-07-24T04:00:00+00:00",
            "H1": "2026-07-24T07:00:00+00:00",
            "M15": "2026-07-24T07:45:00+00:00",
        },
    }


def _observed_row(symbol: str = "EUR/USD") -> tuple[dict, object]:
    row = _row(symbol)
    decision = evaluate_scanner_candidate(
        row,
        None,
        now=datetime(2026, 7, 24, 8, tzinfo=timezone.utc),
    )
    row.update({
        "candidate_status": decision.status,
        "selected_side": decision.selected_side,
        "auto_trade_branch": decision.branch,
        "strategy_config_status": decision.strategy.config_status,
        "expected_effective_rr": decision.strategy.expected_effective_rr,
        "execution_ready": decision.execution_ready,
        "trade_allowed": decision.trade_allowed,
        "scanner_candidate_decision": decision.to_dict(),
    })
    row["candidate_order_payload"] = build_candidate_order_payload(row, decision)
    ranked = rank_scanner_rows([row])[0]
    context = create_scan_context(
        {"trading": {"max_risk_percent": 2}, "ai": {"api_key": "secret-a"}},
        {
            "symbols": [symbol],
            "feature_flags": {},
            "smc_scoring_mode": "v2",
        },
        now=datetime(2026, 7, 24, 8, tzinfo=timezone.utc),
    )
    observed = attach_row_observability(
        ranked,
        context,
        portfolio_state={"available": True, "account_balance": 10_000},
    )
    return observed, context


def _settings():
    return SimpleNamespace(
        trading=SimpleNamespace(
            max_risk_percent=2.0,
            account_currency="USD",
            lot_step=0.01,
            minimum_lot=0.01,
            contract_size_override={},
            default_risk_percent=1.0,
            max_daily_loss_pct=2.0,
            max_weekly_loss_pct=5.0,
            max_consecutive_losses=3,
            max_open_risk_pct=3.0,
        ),
        advanced=SimpleNamespace(
            d1_bars=500,
            h4_bars=500,
            h1_bars=500,
            scanner_ai_detail_limit=3,
            high_impact_news_block_before_minutes=30,
            high_impact_news_block_after_minutes=30,
            block_high_impact_news=True,
        ),
        display=SimpleNamespace(timezone="Asia/Ho_Chi_Minh"),
        ai=SimpleNamespace(active_provider=lambda: None),
        notifications=SimpleNamespace(
            telegram_bot_token="", telegram_chat_ids=[]
        ),
    )


class _SettingsService:
    def __init__(self, settings=None):
        self._settings = settings or _settings()

    def load(self):
        return self._settings


class _ScanHealth:
    def record_scan(self, **kwargs):
        return {"recorded": True}


def _make_controller(tmp_path, *, job_state=None):
    ctrl = ScannerController(
        settings_service=_SettingsService(),
        mt5=MagicMock(),
        news_service=MagicMock(),
        journal_service=MagicMock(),
        telegram_service=MagicMock(),
        scan_health_service=_ScanHealth(),
        retention_service=RuntimeRetentionService(tmp_path),
        job_state=job_state or ScannerJobState(runtime_root=tmp_path),
    )
    ctrl.observability = MagicMock()
    return ctrl


def _result(rows, context, *, mode: str | None = None) -> dict:
    result = {
        "scan_id": context.scan_id,
        "timestamp": context.started_at,
        "scan_context": context.to_dict(),
        "rows": rows,
        "summary": {"ready_now_count": len(rows)},
    }
    if mode is not None:
        result["persistence_mode"] = mode
    return result


def _snapshot_path(tmp_path, scan_id: str) -> Path:
    return tmp_path / "scanner_snapshots" / f"scanner_{scan_id}.json"


# ---------------------------------------------------------------------------
# Ordering, atomicity and the persistence delta contract
# ---------------------------------------------------------------------------


def test_compact_summary_written_before_full_analysis_files(tmp_path, monkeypatch):
    ctrl = _make_controller(tmp_path)
    row, context = _observed_row()
    result = _result([row], context)
    calls: list[Path] = []
    real = scanner_module.atomic_json_save

    def recording(path, data, *, indent=None):
        calls.append(Path(path))
        return real(path, data, indent=indent)

    monkeypatch.setattr(scanner_module, "atomic_json_save", recording)

    ctrl.persist_scan(result, runtime_root=tmp_path)

    snapshot = _snapshot_path(tmp_path, context.scan_id)
    analysis = (
        tmp_path / "scanner_analysis" / context.scan_id / "EURUSD.json.gz"
    )
    assert calls[0] == snapshot  # compact summary first (durable immediately)
    assert analysis in calls  # full evidence after
    assert calls[-1] == snapshot  # final summary rewrite last
    assert calls.index(analysis) > calls.index(snapshot)


def test_persist_scan_delta_contract(tmp_path):
    ctrl = _make_controller(tmp_path)
    rows = [_observed_row("EUR/USD")[0], _observed_row("GBP/USD")[0]]
    scan_context = create_scan_context(
        {"trading": {"max_risk_percent": 2}},
        {"symbols": ["EUR/USD", "GBP/USD"], "feature_flags": {}},
    )
    result = _result(rows, scan_context)

    info = ctrl.persist_scan(result, runtime_root=tmp_path)

    assert info["snapshot_mode"] == "full"
    assert info["snapshot_write_count"] == 2
    assert set(info["snapshot_manifest"]) == {"EUR/USD", "GBP/USD"}
    assert info["snapshot_duration_ms"] >= 0
    assert info["snapshot_errors"] == []
    assert info["snapshot_status"] == "completed"
    assert info["snapshot_path"] == _snapshot_path(tmp_path, scan_context.scan_id)
    snapshot = json.loads(Path(info["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["persistence_schema_version"] == 1
    assert snapshot["persistence_status"] == "completed"
    assert snapshot["persistence_mode"] == "full"
    assert snapshot["analysis_manifest"]["EUR/USD"] == str(
        tmp_path / "scanner_analysis" / scan_context.scan_id / "EURUSD.json.gz"
    )


def test_analysis_write_failure_is_recorded_not_silent(tmp_path, monkeypatch):
    ctrl = _make_controller(tmp_path)
    ctrl.retention = MagicMock()
    row, context = _observed_row()
    result = _result([row], context)
    real = scanner_module.atomic_json_save

    def failing(path, data, *, indent=None):
        if Path(path).suffix == ".gz":
            raise OSError("disk full")
        return real(path, data, indent=indent)

    monkeypatch.setattr(scanner_module, "atomic_json_save", failing)

    info = ctrl.persist_scan(result, runtime_root=tmp_path)

    assert info["snapshot_write_count"] == 0
    assert info["snapshot_manifest"] == {}
    assert any("EUR/USD" in error for error in info["snapshot_errors"])
    assert info["snapshot_status"] == "completed_with_errors"
    # The compact summary still landed and loads.
    snapshot = json.loads(Path(info["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["persistence_status"] == "completed_with_errors"
    assert snapshot["rows"][0]["analysis_ref"] == ""
    assert ctrl._scanner_job_state().load_marker(context.scan_id)["state"] == (
        "interrupted"
    )
    ctrl.retention.prune.assert_not_called()
    ctrl.observability.emit.assert_called()
    assert any(
        call.args[0] == "SNAPSHOT_WRITE_FAILURE"
        for call in ctrl.observability.emit.call_args_list
    )
    assert any(
        call.args[0] == "RETENTION_PRUNE_SKIPPED"
        and call.kwargs["payload"]["reason"]
        == "persistence_write_incomplete"
        for call in ctrl.observability.emit.call_args_list
    )


@pytest.mark.parametrize("failed_snapshot_write", [1, 2])
def test_snapshot_write_failure_skips_retention_prune(
    tmp_path,
    monkeypatch,
    failed_snapshot_write,
):
    """mục 22 #14: failed persistence must not delete older artifacts."""
    ctrl = _make_controller(tmp_path)
    ctrl.retention = MagicMock()
    row, context = _observed_row()
    result = _result([row], context, mode="none")
    real = scanner_module.atomic_json_save
    snapshot_writes = 0

    def failing(path, data, *, indent=None):
        nonlocal snapshot_writes
        if Path(path) == _snapshot_path(tmp_path, context.scan_id):
            snapshot_writes += 1
            if snapshot_writes == failed_snapshot_write:
                raise OSError("snapshot disk full")
        return real(path, data, indent=indent)

    monkeypatch.setattr(scanner_module, "atomic_json_save", failing)

    with pytest.raises(OSError, match="snapshot disk full"):
        ctrl.persist_scan(result, runtime_root=tmp_path)

    ctrl.retention.prune.assert_not_called()
    assert ctrl._scanner_job_state().load_marker(context.scan_id)["state"] == (
        "interrupted"
    )
    assert any(
        call.args[0] == "RETENTION_PRUNE_SKIPPED"
        and call.kwargs["payload"]["reason"] == "persistence_write_failed"
        and call.kwargs["payload"]["error"] == "snapshot disk full"
        for call in ctrl.observability.emit.call_args_list
    )


def test_save_snapshot_wrapper_returns_path(tmp_path):
    ctrl = _make_controller(tmp_path)
    row, context = _observed_row()
    result = _result([row], context)

    path = ctrl.save_snapshot(result, runtime_root=tmp_path)

    assert isinstance(path, Path)
    assert path.name == f"scanner_{context.scan_id}.json"
    assert path.exists()


def test_atomic_write_interrupted_mid_write_leaves_target_intact(tmp_path, monkeypatch):
    target = tmp_path / "scanner_scan.json"
    atomic_json_save(target, {"state": "old"})
    before = target.read_bytes()

    def broken_replace(self, other):
        raise OSError("killed mid-write")

    monkeypatch.setattr(Path, "replace", broken_replace)
    with pytest.raises(OSError, match="killed mid-write"):
        atomic_json_save(target, {"state": "new"})

    assert target.read_bytes() == before
    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "old"}


def test_atomic_gzip_write_interrupted_leaves_no_truncated_file(tmp_path, monkeypatch):
    target = tmp_path / "EURUSD.json.gz"
    atomic_json_save(target, {"symbol": "EURUSD"})
    before = target.read_bytes()

    def broken_replace(self, other):
        raise OSError("killed mid-write")

    monkeypatch.setattr(Path, "replace", broken_replace)
    with pytest.raises(OSError):
        atomic_json_save(target, {"symbol": "GBPUSD"})

    assert target.read_bytes() == before
    loaded = json.loads(gzip.open(target, "rt", encoding="utf-8").read())
    assert loaded == {"symbol": "EURUSD"}


# ---------------------------------------------------------------------------
# Snapshot replay and backward compatibility (mục 22 #11, mục 20.3)
# ---------------------------------------------------------------------------


def test_snapshot_replay_roundtrip(tmp_path):
    ctrl = _make_controller(tmp_path)
    row, context = _observed_row()
    result = _result([row], context)

    info = ctrl.persist_scan(result, runtime_root=tmp_path)

    analysis_path = Path(info["snapshot_manifest"]["EUR/USD"])
    document = json.loads(gzip.open(analysis_path, "rt", encoding="utf-8").read())
    replay = replay_candidate_decision(document)
    assert replay["replayable"] is True
    assert replay["match"] is True

    snapshot = json.loads(Path(info["snapshot_path"]).read_text(encoding="utf-8"))
    assert snapshot["rows"][0]["symbol"] == "EUR/USD"
    assert snapshot["rows"][0]["analysis_ref"] == str(analysis_path)
    assert "analysis_result" not in snapshot["rows"][0]


def test_snapshot_backward_compatible_with_legacy_schema(tmp_path):
    snapshot_dir = tmp_path / "scanner_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    legacy = {
        "persistence_schema_version": 1,
        "persistence_mode": "full",
        "scan_id": "legacy-scan",
        "rows": [{"symbol": "EUR/USD", "best_score": 78, "analysis_ref": ""}],
        "summary": {"ready_now_count": 1},
    }
    legacy_path = snapshot_dir / "scanner_legacy-scan.json"
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")

    # A legacy snapshot without the Phase-5 fields still loads cleanly.
    loaded = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert loaded["rows"][0]["symbol"] == "EUR/USD"
    assert "persistence_status" not in loaded

    # The new writer's output is a superset: every legacy key is preserved and
    # only optional keys are added, so old readers keep working.
    ctrl = _make_controller(tmp_path)
    row, context = _observed_row()
    info = ctrl.persist_scan(_result([row], context), runtime_root=tmp_path)
    new_doc = json.loads(Path(info["snapshot_path"]).read_text(encoding="utf-8"))
    assert new_doc["persistence_schema_version"] == 1
    for key in legacy:
        assert key in new_doc
    assert new_doc["persistence_status"] == "completed"


# ---------------------------------------------------------------------------
# Job status markers and bounded shutdown wait (mục 19.2)
# ---------------------------------------------------------------------------


def test_job_marker_lifecycle(tmp_path):
    job_state = ScannerJobState(runtime_root=tmp_path)

    job_state.begin_aftercare("scan-1")

    assert job_state.active_jobs() == ("scan-1",)
    marker = job_state.load_marker("scan-1")
    assert marker is not None
    assert marker["state"] == "running"
    assert marker["scan_id"] == "scan-1"
    assert marker["schema_version"] == 1

    job_state.complete_aftercare("scan-1")

    assert job_state.active_jobs() == ()
    assert job_state.load_marker("scan-1")["state"] == "completed"
    assert job_state.load_marker("scan-1")["completed_at"]


def test_interrupted_marker_survives_late_completion(tmp_path):
    job_state = ScannerJobState(runtime_root=tmp_path)
    job_state.begin_aftercare("scan-1")

    job_state.mark_interrupted("scan-1", reason="shutdown_timeout")
    assert job_state.load_marker("scan-1")["state"] == "interrupted"
    assert job_state.load_marker("scan-1")["reason"] == "shutdown_timeout"

    # The interrupted job leaves the in-memory waiting set immediately, so a
    # second wait no longer times out for it.
    assert job_state.active_jobs() == ()
    assert job_state.wait_for_aftercare(0.01) is True

    # The worker finishing late must not downgrade the interruption record.
    job_state.complete_aftercare("scan-1")
    assert job_state.load_marker("scan-1")["state"] == "interrupted"


def test_app_close_without_active_job_returns_immediately(tmp_path):
    ctrl = _make_controller(tmp_path)

    assert ctrl.wait_for_aftercare_shutdown(timeout=0.01) is True
    assert ctrl.wait_for_aftercare_shutdown(timeout=0) is True


def test_app_close_wait_returns_true_when_aftercare_finishes_in_time(tmp_path):
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    row, context = _observed_row()
    result = _result([row], context)

    thread = threading.Thread(
        target=ctrl.persist_scan,
        kwargs={"result": result, "runtime_root": tmp_path},
    )
    thread.start()

    completed = ctrl.wait_for_aftercare_shutdown(timeout=5)
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert completed is True
    assert job_state.active_jobs() == ()
    assert job_state.load_marker(context.scan_id)["state"] == "completed"


def test_app_close_mid_persistence_marks_interrupted_and_data_survives(
    tmp_path,
    monkeypatch,
):
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    row, context = _observed_row()
    result = _result([row], context)
    real = scanner_module.atomic_json_save

    def slow_analysis(path, data, *, indent=None):
        if Path(path).suffix == ".gz":
            time.sleep(0.08)
        return real(path, data, indent=indent)

    monkeypatch.setattr(scanner_module, "atomic_json_save", slow_analysis)

    thread = threading.Thread(
        target=ctrl.persist_scan,
        kwargs={"result": result, "runtime_root": tmp_path},
    )
    thread.start()

    # Wait until the compact summary is durable and the job is in flight.
    snapshot = _snapshot_path(tmp_path, context.scan_id)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not snapshot.exists():
        time.sleep(0.01)
    assert snapshot.exists()
    assert job_state.active_jobs() == (context.scan_id,)

    # The app closes: the bounded wait expires while persistence is running.
    completed = ctrl.wait_for_aftercare_shutdown(timeout=0.05)
    assert completed is False
    marker = job_state.load_marker(context.scan_id)
    assert marker is not None
    assert marker["state"] == "interrupted"

    thread.join(timeout=10)
    assert not thread.is_alive()

    # No data lost or corrupted: snapshot and every written gzip load cleanly,
    # and the marker stays interrupted even though the worker finished late.
    doc = json.loads(snapshot.read_text(encoding="utf-8"))
    assert doc["scan_id"] == context.scan_id
    for ref in doc.get("analysis_manifest", {}).values():
        loaded = json.loads(gzip.open(ref, "rt", encoding="utf-8").read())
        assert loaded["symbol"] == "EUR/USD"
    assert job_state.load_marker(context.scan_id)["state"] == "interrupted"
    # The interrupted job is out of the in-memory waiting set: a second
    # shutdown call returns immediately instead of timing out again.
    assert job_state.active_jobs() == ()
    assert ctrl.wait_for_aftercare_shutdown(timeout=0.01) is True


# ---------------------------------------------------------------------------
# Aftercare delta exposes the persistence contract
# ---------------------------------------------------------------------------


def test_aftercare_delta_exposes_persistence_contract(monkeypatch, tmp_path):
    # Phase 5: aftercare writes the compact summary before market brief; keep
    # those artifacts in the test dir, never the real runtime.
    monkeypatch.setattr(scanner_module, "app_data_dir", lambda: tmp_path)
    ctrl = _make_controller(tmp_path)
    settings = _settings()
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        auto_trade_enabled=False,
        persistence_mode="full",
        feature_flags={"scanner_core_result_early": True},
    )
    scan_context = create_scan_context(settings, request)
    rows = [blocked_scanner_row("EUR/USD", "test")]
    core_output = build_scanner_output(rows, request, 0)
    core_output["scan_id"] = scan_context.scan_id
    core_output["scan_context"] = scan_context.to_dict()
    ctx = {
        "scan_context": scan_context,
        "settings": settings,
        "correlation_context": {},
        "freshness": {},
        "closed_trades": [],
        "rows": rows,
        "portfolio_state": {},
    }
    info = {
        "snapshot_path": Path("/tmp/scan-snapshot.json"),
        "snapshot_mode": "full",
        "snapshot_manifest": {"EUR/USD": "/tmp/EURUSD.json.gz"},
        "snapshot_write_count": 1,
        "snapshot_duration_ms": 7.25,
        "snapshot_errors": [],
        "snapshot_status": "completed",
    }
    monkeypatch.setattr(ctrl, "persist_scan", lambda result, **kwargs: info)

    delta = ctrl._run_market_scan_aftercare(
        core_output, request, lambda p, m: None, ctx=ctx
    )

    assert delta["snapshot_path"] == str(info["snapshot_path"])
    assert delta["persistence"] == {
        "mode": "full",
        "manifest": {"EUR/USD": "/tmp/EURUSD.json.gz"},
        "write_count": 1,
        "duration_ms": 7.25,
        "errors": [],
        "status": "completed",
    }


# ---------------------------------------------------------------------------
# App closes mid-aftercare (mục 19.2): job + compact summary exist before
# market brief/Telegram, shutdown waits bounded, marker says interrupted.
# ---------------------------------------------------------------------------


def test_app_close_during_market_brief_keeps_compact_snapshot_and_marks_interrupted(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(scanner_module, "app_data_dir", lambda: tmp_path)
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    settings = _settings()
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        auto_trade_enabled=False,
        persistence_mode="full",
        feature_flags={"scanner_core_result_early": True},
    )
    scan_context = create_scan_context(settings, request)
    rows = [blocked_scanner_row("EUR/USD", "test")]
    core_output = build_scanner_output(rows, request, 0)
    core_output["scan_id"] = scan_context.scan_id
    core_output["scan_context"] = scan_context.to_dict()
    ctx = {
        "scan_context": scan_context,
        "settings": settings,
        "correlation_context": {},
        "freshness": {},
        "closed_trades": [],
        "rows": rows,
        "portfolio_state": {},
    }

    def slow_brief(rows, *, correlation_context, freshness, settings):
        time.sleep(0.3)
        return "brief", ""

    monkeypatch.setattr(ctrl, "_generate_market_brief", slow_brief)

    thread = threading.Thread(
        target=ctrl._run_market_scan_aftercare,
        kwargs={
            "core_output": core_output,
            "request": request,
            "progress": lambda p, m: None,
            "ctx": ctx,
        },
    )
    thread.start()

    # The job and the compact summary are registered BEFORE market brief:
    # both must exist while the brief is still running.
    snapshot = _snapshot_path(tmp_path, scan_context.scan_id)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not snapshot.exists():
        time.sleep(0.01)
    assert snapshot.exists()
    assert job_state.active_jobs() == (scan_context.scan_id,)
    marker = job_state.load_marker(scan_context.scan_id)
    assert marker is not None
    assert marker["state"] == "running"
    compact = json.loads(snapshot.read_text(encoding="utf-8"))
    assert compact["persistence_status"] == "writing"

    # App closes while the brief is still in flight: the bounded wait must NOT
    # report completion, and the job is recorded as interrupted.
    completed = ctrl.wait_for_aftercare_shutdown(timeout=0.05)
    assert completed is False
    assert job_state.load_marker(scan_context.scan_id)["state"] == "interrupted"

    # A second shutdown after the timeout returns immediately: the interrupted
    # job already left the in-memory waiting set.
    assert job_state.active_jobs() == ()
    assert ctrl.wait_for_aftercare_shutdown(timeout=0.01) is True

    thread.join(timeout=10)
    assert not thread.is_alive()

    # The worker eventually finished: snapshot and analysis files load cleanly,
    # and the marker stays interrupted.
    final = json.loads(snapshot.read_text(encoding="utf-8"))
    assert final["scan_id"] == scan_context.scan_id
    for ref in final.get("analysis_manifest", {}).values():
        loaded = json.loads(gzip.open(ref, "rt", encoding="utf-8").read())
        assert loaded["symbol"] == "EUR/USD"
    assert job_state.load_marker(scan_context.scan_id)["state"] == "interrupted"


def test_app_close_during_telegram_keeps_snapshot_and_late_completion_interrupted(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(scanner_module, "app_data_dir", lambda: tmp_path)
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    settings = _settings()
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        auto_trade_enabled=False,
        persistence_mode="full",
        feature_flags={"scanner_core_result_early": True},
    )
    scan_context = create_scan_context(settings, request)
    rows = [blocked_scanner_row("EUR/USD", "test")]
    core_output = build_scanner_output(rows, request, 0)
    core_output["scan_id"] = scan_context.scan_id
    core_output["scan_context"] = scan_context.to_dict()
    ctx = {
        "scan_context": scan_context,
        "settings": settings,
        "correlation_context": {},
        "freshness": {},
        "closed_trades": [],
        "rows": rows,
        "portfolio_state": {},
    }
    telegram_started = threading.Event()
    release_telegram = threading.Event()

    def blocking_telegram(_rows):
        telegram_started.set()
        release_telegram.wait()
        return {
            "attempted": 0,
            "sent": 0,
            "errors": [],
            "summary_sent": 0,
        }

    monkeypatch.setattr(ctrl, "_send_telegram_alerts", blocking_telegram)
    thread = threading.Thread(
        target=ctrl._run_market_scan_aftercare,
        kwargs={
            "core_output": core_output,
            "request": request,
            "progress": lambda p, m: None,
            "ctx": ctx,
        },
    )
    thread.start()

    try:
        assert telegram_started.wait(timeout=5)
        snapshot = _snapshot_path(tmp_path, scan_context.scan_id)
        assert snapshot.exists()
        compact = json.loads(snapshot.read_text(encoding="utf-8"))
        assert compact["persistence_status"] == "writing"
        assert job_state.active_jobs() == (scan_context.scan_id,)
        assert job_state.load_marker(scan_context.scan_id)["state"] == "running"

        assert ctrl.wait_for_aftercare_shutdown(timeout=0.01) is False
        assert job_state.active_jobs() == ()
        assert job_state.load_marker(scan_context.scan_id)["state"] == "interrupted"

        def unexpected_wait(timeout=None):
            raise AssertionError("second shutdown waited again")

        monkeypatch.setattr(job_state._condition, "wait", unexpected_wait)
        assert ctrl.wait_for_aftercare_shutdown(timeout=10) is True
    finally:
        release_telegram.set()
        thread.join(timeout=10)

    assert not thread.is_alive()
    final = json.loads(snapshot.read_text(encoding="utf-8"))
    assert final["scan_id"] == scan_context.scan_id
    assert final["analysis_manifest"]
    for ref in final["analysis_manifest"].values():
        loaded = json.loads(gzip.open(ref, "rt", encoding="utf-8").read())
        assert loaded["symbol"] == "EUR/USD"
    assert job_state.load_marker(scan_context.scan_id)["state"] == "interrupted"


def test_complete_marker_write_failure_clears_active_job_and_keeps_incomplete_marker(
    tmp_path,
    monkeypatch,
):
    """mục 22 #14: marker failure cannot keep a finished worker active."""
    job_state = ScannerJobState(runtime_root=tmp_path)
    job_state.begin_aftercare("scan-1", durable=True)
    assert job_state.load_marker("scan-1")["state"] == "running"
    running_marker = job_state.marker_path("scan-1").read_bytes()

    def always_fail(self, scan_id, state, *, started_at=None, reason=None):
        raise OSError("disk full")

    monkeypatch.setattr(ScannerJobState, "_write_marker", always_fail)

    # Completion is real even when its durable transition cannot be written.
    # The old atomic marker remains readable as an incomplete-job signal.
    job_state.complete_aftercare("scan-1")
    assert job_state.active_jobs() == ()
    assert job_state.wait_for_aftercare(10) is True
    marker = job_state.load_marker("scan-1")
    assert marker is not None
    assert marker["state"] == "running"
    assert job_state.marker_path("scan-1").read_bytes() == running_marker


def test_shutdown_marker_write_failure_clears_job_after_first_timeout(
    tmp_path,
    monkeypatch,
):
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    job_state.begin_aftercare("scan-1", durable=True)
    assert job_state.load_marker("scan-1")["state"] == "running"
    running_marker = job_state.marker_path("scan-1").read_bytes()

    def always_fail(self, scan_id, state, *, started_at=None, reason=None):
        raise OSError("disk full")

    monkeypatch.setattr(ScannerJobState, "_write_marker", always_fail)

    # The first call consumes its bounded wait and reports the timeout, while
    # interruption removes the no-longer-waitable job even if its marker fails.
    assert ctrl.wait_for_aftercare_shutdown(timeout=0.01) is False
    assert job_state.active_jobs() == ()
    marker = job_state.load_marker("scan-1")
    assert marker is not None
    assert marker["state"] == "running"
    assert job_state.marker_path("scan-1").read_bytes() == running_marker

    # An empty liveness set must bypass Condition.wait entirely, proving that
    # a repeated shutdown does not consume another wait budget.
    def unexpected_wait(timeout=None):
        raise AssertionError("second shutdown waited again")

    monkeypatch.setattr(job_state._condition, "wait", unexpected_wait)
    assert ctrl.wait_for_aftercare_shutdown(timeout=10) is True


def test_second_shutdown_after_timeout_returns_immediately(tmp_path):
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    job_state.begin_aftercare("scan-1", durable=True)

    # First shutdown: budget expires while the job is still running.
    assert ctrl.wait_for_aftercare_shutdown(timeout=0.01) is False
    assert job_state.load_marker("scan-1")["state"] == "interrupted"
    assert job_state.active_jobs() == ()

    # Second shutdown must not wait another bounded budget for a job that is
    # no longer in flight.
    assert ctrl.wait_for_aftercare_shutdown(timeout=0.01) is True


def test_blocked_interrupted_marker_write_does_not_extend_shutdown_budget(
    tmp_path,
    monkeypatch,
):
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    job_state.begin_aftercare("scan-1", durable=True)
    running_marker = job_state.marker_path("scan-1").read_bytes()

    # A compact snapshot already made durable before aftercare must remain
    # readable while the best-effort interruption marker is stalled.
    snapshot = tmp_path / "scanner_snapshots" / "scanner_scan-1.json"
    atomic_json_save(
        snapshot,
        {"scan_id": "scan-1", "persistence_status": "writing"},
    )
    snapshot_bytes = snapshot.read_bytes()

    marker_started = threading.Event()
    release_marker = threading.Event()
    marker_finished = threading.Event()
    real_write_marker = job_state._write_marker

    def blocking_interrupted_marker(
        self,
        scan_id,
        state,
        *,
        started_at=None,
        reason=None,
    ):
        if state == "interrupted":
            marker_started.set()
            release_marker.wait(timeout=5)
        try:
            return real_write_marker(
                scan_id,
                state,
                started_at=started_at,
                reason=reason,
            )
        finally:
            if state == "interrupted":
                marker_finished.set()

    monkeypatch.setattr(
        ScannerJobState,
        "_write_marker",
        blocking_interrupted_marker,
    )

    try:
        started = time.monotonic()
        assert ctrl.wait_for_aftercare_shutdown(timeout=0.05) is False
        elapsed = time.monotonic() - started

        # The timeout plus the short fast-write grace stays well below the
        # blocked writer's duration.  Its in-memory transition is already
        # terminal, so a second shutdown cannot spend the budget again.
        assert elapsed < 0.15
        assert marker_started.wait(timeout=1)
        assert job_state.active_jobs() == ()
        assert job_state.marker_path("scan-1").read_bytes() == running_marker
        assert job_state.load_marker("scan-1")["state"] == "running"
        assert snapshot.read_bytes() == snapshot_bytes
        assert json.loads(snapshot.read_text(encoding="utf-8"))["scan_id"] == "scan-1"

        second_started = time.monotonic()
        assert ctrl.wait_for_aftercare_shutdown(timeout=0.05) is True
        assert time.monotonic() - second_started < 0.05

        # A worker completing late cannot overwrite the interruption selected
        # atomically when the first shutdown timed out.
        job_state.complete_aftercare("scan-1")
    finally:
        release_marker.set()

    assert marker_finished.wait(timeout=5)
    assert job_state.load_marker("scan-1")["state"] == "interrupted"
    assert snapshot.read_bytes() == snapshot_bytes


def test_blocked_completed_marker_write_does_not_hold_job_condition(
    tmp_path,
    monkeypatch,
):
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    job_state.begin_aftercare("scan-1", durable=True)
    running_marker = job_state.marker_path("scan-1").read_bytes()

    marker_started = threading.Event()
    release_marker = threading.Event()
    real_write_marker = job_state._write_marker

    def blocking_completed_marker(
        self,
        scan_id,
        state,
        *,
        started_at=None,
        reason=None,
    ):
        if state == "completed":
            marker_started.set()
            release_marker.wait(timeout=5)
        return real_write_marker(
            scan_id,
            state,
            started_at=started_at,
            reason=reason,
        )

    monkeypatch.setattr(
        ScannerJobState,
        "_write_marker",
        blocking_completed_marker,
    )
    worker = threading.Thread(target=job_state.complete_aftercare, args=("scan-1",))
    worker.start()

    try:
        assert marker_started.wait(timeout=5)
        started = time.monotonic()
        assert ctrl.wait_for_aftercare_shutdown(timeout=0.05) is True
        assert time.monotonic() - started < 0.05
        assert job_state.active_jobs() == ()
        assert job_state.marker_path("scan-1").read_bytes() == running_marker
    finally:
        release_marker.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert job_state.load_marker("scan-1")["state"] == "completed"


def test_shutdown_timeout_atomically_claims_job_before_late_completion(tmp_path):
    job_state = ScannerJobState(runtime_root=tmp_path)
    ctrl = _make_controller(tmp_path, job_state=job_state)
    job_state.begin_aftercare("scan-1", durable=True)
    completion_attempted = threading.Event()

    def complete_immediately_after_timeout() -> None:
        completion_attempted.set()
        job_state.complete_aftercare("scan-1")

    # Hold the re-entrant condition so the shutdown caller can make its
    # timeout decision while the worker is already queued for the same lock.
    # Timeout + terminal claim must be one critical section: once released,
    # the late completion observes that the interrupted job is already gone.
    with job_state._condition:
        worker = threading.Thread(target=complete_immediately_after_timeout)
        worker.start()
        assert completion_attempted.wait(timeout=1)
        assert ctrl.wait_for_aftercare_shutdown(timeout=0) is False
        assert job_state.active_jobs() == ()

    worker.join(timeout=5)
    assert not worker.is_alive()

    deadline = time.monotonic() + 1
    marker = job_state.load_marker("scan-1")
    while marker is not None and marker.get("state") != "interrupted":
        assert time.monotonic() < deadline
        time.sleep(0.005)
        marker = job_state.load_marker("scan-1")
    assert marker is not None
    assert marker["state"] == "interrupted"
    assert marker["reason"] == "shutdown_timeout"
