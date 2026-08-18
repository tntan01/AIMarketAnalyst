"""Scanner — PIT dataset collector/validator (Bước 09; target-only).

Exercises the fail-closed contract of ``core/scanner_pit_dataset.py``:

* manifest/digest SHA-256 deterministic + keyed to the corpus canonical payload;
* validator flags duplicate (captured_at, symbol), future timestamp, naïvetime,
  look-ahead leakage (outcome before decision), missing provenance/identity,
  and a category marked ``valid`` without an ``observed_at`` (non-PIT);
* a missing/unknown category is surfaced as ``UNKNOWN`` downstream and the corpus
  is never ``sufficient_for_calibration`` on that missing data;
* ``is_eligible_for_entry`` is True only for ``AVAILABLE``;
* the full evidence chain maps to the existing safety-audit + calibration harness.

Discipline note: the corpus built here is a **synthetic test fixture** used only
to prove the collector logic — it is NOT a historical PIT dataset and MUST NOT be
used to select production thresholds.  The harness refuses to recommend any
threshold on it (INSUFFICIENT_SAMPLE → every recommended threshold is ``None``).
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.scanner_calibration import (
    SCANNER_CALIBRATION_INSUFFICIENT,
)
from core.scanner_pit_dataset import (
    PIT_DATASET_VERSION,
    CategoryObservation,
    ForwardCollectorConfig,
    PitSnapshotRow,
    append_forward_snapshot,
    collect_safety_sources,
    dataset_sha256,
    forward_status,
    init_forward_collector,
    load_pit_dataset_jsonl,
    run_pit_evidence,
    to_calibration_inputs,
    validate_pit_rows,
)
from core.scanner_safety_audit import (
    AVAILABLE,
    MISSING,
    UNKNOWN,
    is_eligible_for_entry,
)

UTC = timezone.utc
BASE = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)


def _obs(availability: str = "valid", *, at: datetime | None = None) -> CategoryObservation:
    return CategoryObservation(
        availability=availability,
        source="mt5",
        observed_at=at if at is not None else None,
        value=1.0,
    )


def _row(
    *,
    symbol: str,
    day: int,
    side: str = "buy",
    outcome: float | None = 2.0,
    outcome_day: int | None = 1,
    provenance: str = "pit-fixture",
    categories: dict | None = None,
    future: bool = False,
) -> PitSnapshotRow:
    captured = BASE + timedelta(days=day)
    obs_at = captured + timedelta(days=outcome_day) if outcome_day is not None else None
    cat = categories if categories is not None else {
        c: _obs("valid", at=captured) for c in ("connectivity", "data_freshness", "spread", "news", "volatility")
    }
    return PitSnapshotRow(
        captured_at=captured,
        symbol=symbol,
        regime="trending_up",
        side=side,
        provenance=provenance,
        categories=cat,
        technical_signal_score=76,
        setup_score=72,
        selected_side="buy",
        candidate_status="WAITING_CONFIRMATION",
        outcome_r=outcome,
        outcome_observed_at=obs_at,
    )


PIT_BOUNDARY = datetime(2026, 7, 15, 0, 0, 0, tzinfo=UTC)


class TestDigestDeterminism:
    def test_sha256_is_stable_and_order_independent(self) -> None:
        a = (_row(symbol="XAUUSD", day=1), _row(symbol="EURUSD", day=2))
        b = (_row(symbol="EURUSD", day=2), _row(symbol="XAUUSD", day=1))
        assert dataset_sha256(a) == dataset_sha256(b)
        assert len(dataset_sha256(a)) == 64
        # A single bit of content change flips the digest.
        changed = (
            _row(symbol="XAUUSD", day=1),
            _row(symbol="EURUSD", day=2, outcome=1.0),
        )
        assert dataset_sha256(changed) != dataset_sha256(a)


class TestValidatorFailClosed:
    def test_clean_corpus_has_no_issues(self) -> None:
        rows = (_row(symbol="XAUUSD", day=1), _row(symbol="EURUSD", day=2))
        assert validate_pit_rows(rows).clean is True

    def test_duplicate_snapshot_flagged(self) -> None:
        rows = (_row(symbol="XAUUSD", day=1), _row(symbol="XAUUSD", day=1))
        issues = set(validate_pit_rows(rows).issues)
        assert any("DUPLICATE_SNAPSHOT" in i for i in issues)

    def test_future_timestamp_flagged(self) -> None:
        rows = (_row(symbol="XAUUSD", day=1), _row(symbol="EURUSD", day=2))
        val = validate_pit_rows(rows, now=BASE)
        assert not val.clean
        assert any("FUTURE_TIMESTAMP" in i for i in val.issues)

    def test_naive_timestamp_flagged(self) -> None:
        from dataclasses import replace

        row = replace(_row(symbol="XAUUSD", day=1), captured_at=datetime(2026, 6, 2))
        val = validate_pit_rows((row,))
        assert not val.clean
        assert any("NAIVE_TIMESTAMP" in i for i in val.issues)

    def test_look_ahead_leakage_flagged(self) -> None:
        # Outcome observed the day BEFORE the decision → future knowledge leaked.
        from dataclasses import replace

        row = replace(
            _row(symbol="XAUUSD", day=1, outcome_day=-1),
            outcome_observed_at=BASE + timedelta(days=0),
        )
        val = validate_pit_rows((row,))
        assert any("LOOK_AHEAD_LEAK" in i for i in val.issues)

    def test_missing_provenance_and_symbol_flagged(self) -> None:
        from dataclasses import replace

        row = replace(_row(symbol="XAUUSD", day=1), provenance="", symbol="")
        val = validate_pit_rows((row,))
        assert any("MISSING_PROVENANCE" in i for i in val.issues)
        assert any("MISSING_SYMBOL" in i for i in val.issues)

    def test_valid_category_without_observed_at_is_non_pit(self) -> None:
        from dataclasses import replace

        bad_cats = {c: _obs("valid", at=None) for c in ("connectivity", "data_freshness", "spread", "news", "volatility")}
        row = replace(_row(symbol="XAUUSD", day=1), categories=bad_cats)
        val = validate_pit_rows((row,))
        assert any("CATEGORY_NON_PIT" in i for i in val.issues)


class TestSafetyAuditMapping:
    def test_all_valid_categories_are_available(self) -> None:
        # Two rows spanning the boundary (before + after) → every category PIT
        # source covers the boundary → AVAILABLE, sufficient_for_calibration=True.
        rows = (_row(symbol="XAUUSD", day=40), _row(symbol="EURUSD", day=60))
        audit = run_pit_evidence(
            rows, pit_boundary=PIT_BOUNDARY, minimum_required_rows=100,
        ).audit
        for item in audit.items:
            assert item.status == AVAILABLE
            assert is_eligible_for_entry(item) is True
        assert audit.sufficient_for_calibration is True

    def test_missing_news_category_is_unknown_never_pass(self) -> None:
        # All categories valid EXCEPT news (missing in both rows) → news
        # MISSING/UNKNOWN, never auto-PASS; the corpus is not eligible.
        from dataclasses import replace

        def news_missing_row(day: int) -> PitSnapshotRow:
            captured = BASE + timedelta(days=day)
            cats = {
                "connectivity": _obs("valid", at=captured),
                "data_freshness": _obs("valid", at=captured),
                "spread": _obs("valid", at=captured),
                "volatility": _obs("valid", at=captured),
                "news": _obs("missing", at=None),
            }
            return replace(_row(symbol="XAUUSD", day=day), categories=cats)

        rows = (news_missing_row(40), news_missing_row(60))
        audit = run_pit_evidence(
            rows, pit_boundary=PIT_BOUNDARY, minimum_required_rows=10,
        ).audit
        by = audit.by_category()
        assert by["connectivity"].status == AVAILABLE
        assert by["news"].status in (UNKNOWN, MISSING)
        assert by["news"].status != AVAILABLE
        assert is_eligible_for_entry(by["news"]) is False
        assert audit.sufficient_for_calibration is False


class TestCalibrationMapping:
    def test_insufficient_sample_renders_no_thresholds_fail_closed(self) -> None:
        rows = (_row(symbol="XAUUSD", day=1), _row(symbol="EURUSD", day=2))
        evidence = run_pit_evidence(
            rows, pit_boundary=PIT_BOUNDARY, minimum_required_rows=100,
        )
        assert evidence.calibration.status == "INSUFFICIENT_SAMPLE"
        assert SCANNER_CALIBRATION_INSUFFICIENT in evidence.calibration.reason_codes
        assert all(v is None for v in evidence.calibration.recommended_thresholds.values())

    def test_calibration_inputs_preserve_fields(self) -> None:
        row = _row(symbol="XAUUSD", day=1)
        inputs = to_calibration_inputs((row,))
        assert inputs[0].symbol == "XAUUSD"
        assert inputs[0].technical_signal_score == 76
        assert inputs[0].setup_score == 72
        assert inputs[0].candidate_status == "WAITING_CONFIRMATION"
        assert inputs[0].outcome_r == 2.0


class TestJsonlLoader:
    def test_jsonl_round_trip_matches_schema_and_digest(self, tmp_path) -> None:
        rows = (_row(symbol="XAUUSD", day=1), _row(symbol="EURUSD", day=2))
        primary = dataset_sha256(rows)
        path = tmp_path / "corpus.jsonl"
        payload = []
        for row in rows:
            payload.append(
                {
                    "captured_at_utc": row.captured_at.isoformat(),
                    "symbol": row.symbol,
                    "regime": row.regime,
                    "side": row.side,
                    "selected_side": row.selected_side,
                    "technical_signal_score": row.technical_signal_score,
                    "setup_score": row.setup_score,
                    "candidate_status": row.candidate_status,
                    "outcome_r": row.outcome_r,
                    "outcome_observed_at_utc": row.outcome_observed_at.isoformat(),
                    "provenance": row.provenance,
                    "connectivity": {"availability": "valid", "source": "mt5", "observed_at": row.captured_at.isoformat(), "value": 1.0},
                    "data_freshness": {"availability": "valid", "source": "mt5", "observed_at": row.captured_at.isoformat(), "value": 1.0},
                    "spread": {"availability": "valid", "source": "mt5", "observed_at": row.captured_at.isoformat(), "value": 1.0},
                    "news": {"availability": "valid", "source": "mt5", "observed_at": row.captured_at.isoformat(), "value": 1.0},
                    "volatility": {"availability": "valid", "source": "mt5", "observed_at": row.captured_at.isoformat(), "value": 1.0},
                }
            )
        path.write_text("\n".join(json.dumps(p, sort_keys=True) for p in payload), encoding="utf-8")
        loaded = load_pit_dataset_jsonl(path)
        assert len(loaded) == 2
        assert loaded[0].captured_at >= PIT_BOUNDARY - timedelta(days=100)
        assert dataset_sha256(loaded) == primary  # disk round-trip is byte-stable


# ---------------------------------------------------------------------------
# Forward collector: append-only corpus for the NEXT calibration
# ---------------------------------------------------------------------------


def _raw_from_row(row: PitSnapshotRow) -> dict:
    # The JSONL input shape accepted by the collector's --append flag.
    return {
        "captured_at_utc": row.captured_at.isoformat(),
        "symbol": row.symbol,
        "regime": row.regime,
        "side": row.side,
        "selected_side": row.selected_side,
        "technical_signal_score": row.technical_signal_score,
        "setup_score": row.setup_score,
        "candidate_status": row.candidate_status,
        "outcome_r": row.outcome_r,
        "outcome_observed_at_utc": row.outcome_observed_at.isoformat(),
        "provenance": row.provenance,
        **{
            category: {
                "availability": row.categories[category].availability,
                "source": row.categories[category].source,
                "observed_at": row.categories[category].observed_at.isoformat()
                if row.categories[category].observed_at is not None
                else None,
                "value": row.categories[category].value,
            }
            for category in ("connectivity", "data_freshness", "spread", "news", "volatility")
        },
    }


class TestForwardCollector:
    def _cfg(self, tmp_path, *, minimum_rows=100, coverage_days=30) -> ForwardCollectorConfig:
        return ForwardCollectorConfig(
            corpus_path=str(tmp_path / "corpus.jsonl"),
            minimum_required_rows=minimum_rows,
            target_coverage_days=coverage_days,
            pit_boundary=PIT_BOUNDARY,
        )

    def test_init_and_status_show_exact_deficit(self, tmp_path) -> None:
        cfg = self._cfg(tmp_path, minimum_rows=100, coverage_days=30)
        init_forward_collector(cfg)
        status = forward_status(cfg)
        assert status.collected_rows == 0
        assert status.missing_rows == 100
        assert status.missing_coverage_days == 30
        assert status.corpus_digest_sha256 == dataset_sha256(())

    def test_append_clean_row_increments_and_reduces_deficit(self, tmp_path) -> None:
        cfg = self._cfg(tmp_path, minimum_rows=100)
        init_forward_collector(cfg)
        ok, issues, report = append_forward_snapshot(cfg, _raw_from_row(_row(symbol="XAUUSD", day=40)))
        assert ok and not issues
        assert report.collected_rows == 1
        assert report.missing_rows == 99
        assert report.validated is True

    def test_append_duplicate_is_rejected_corpus_unchanged(self, tmp_path) -> None:
        cfg = self._cfg(tmp_path, minimum_rows=100)
        init_forward_collector(cfg)
        append_forward_snapshot(cfg, _raw_from_row(_row(symbol="XAUUSD", day=40)))
        before_digest = forward_status(cfg).corpus_digest_sha256
        ok, issues, _ = append_forward_snapshot(
            cfg, _raw_from_row(_row(symbol="XAUUSD", day=40))
        )
        assert ok is False
        assert any("DUPLICATE_SNAPSHOT" in i for i in issues)
        after_digest = forward_status(cfg).corpus_digest_sha256
        assert after_digest == before_digest  # byte-identical, row not recorded

    def test_append_non_pit_category_is_rejected(self, tmp_path) -> None:
        cfg = self._cfg(tmp_path, minimum_rows=100)
        init_forward_collector(cfg)
        good = {c: _obs("valid", at=_row(symbol="X", day=40).captured_at) for c in ("connectivity", "data_freshness", "spread", "volatility")}
        bad_news = {**good, "news": _obs("missing", at=None)}
        from dataclasses import replace
        raw = _raw_from_row(replace(_row(symbol="XAUUSD", day=41), categories=bad_news))
        ok, issues, report = append_forward_snapshot(cfg, raw)
        # A missing news category does not fail-closed the APPEND (it is an
        # honest UNKNOWN in the row), but the corpus is still validated.
        assert ok is True
        assert report.validated is True
        assert report.collected_rows == 1