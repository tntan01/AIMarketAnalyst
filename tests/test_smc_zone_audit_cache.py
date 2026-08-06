"""AI zone-audit cache: backtest replay reads the cache instead of calling
the AI again, and the audit verdict is recorded in the journal."""

from __future__ import annotations

import json

from core.smc_scorer import AI_ZONE_WEAK_REASON, score_smc
from core.smc_zone_ai_review import (
    AI_ZONE_AUDIT_CACHE_KEY,
    get_cached_zone_review,
    parse_zone_review,
    remember_zone_review,
    review_zone_with_cache,
    zone_audit_cache_from_scan_result,
)
from services.journal_service import (
    JournalService,
    journal_entry_from_analysis,
)
from tests.test_smc_scorer import (
    _FakeZoneAuditAIService,
    _smc,
    _technical,
    _zone_audit_response,
)


class _ForbiddenAIService:
    """AI service that must never be called during backtest replay."""

    def __init__(self):
        self.calls = []

    def analyze(self, prompt, *, max_tokens=4000):
        self.calls.append(prompt)
        raise AssertionError("AI must not be called during backtest replay")


def test_zone_audit_cache_embeds_into_scan_result():
    scan_result = {"symbol": "XAU/USD", "rows": []}

    cache = zone_audit_cache_from_scan_result(scan_result)

    assert cache == {}
    assert scan_result[AI_ZONE_AUDIT_CACHE_KEY] is cache
    assert zone_audit_cache_from_scan_result(scan_result) is cache
    # Non-dict scan results are tolerated without raising.
    assert zone_audit_cache_from_scan_result(None) == {}


def test_cache_stores_only_valid_verdicts_keyed_by_zone_id():
    cache = {}
    valid = parse_zone_review(_zone_audit_response())

    assert remember_zone_review(cache, "zone-buy", valid) is True
    assert get_cached_zone_review(cache, "zone-buy") == valid

    uncertain = parse_zone_review("không phải json")
    assert remember_zone_review(cache, "zone-sell", uncertain) is False
    assert get_cached_zone_review(cache, "zone-sell") is None
    assert remember_zone_review(cache, "", valid) is False
    assert get_cached_zone_review(cache, "") is None


def test_cached_review_is_revalidated_fail_closed():
    cache = {
        "zone-corrupt": {
            "status": "valid",
            "zone_validity": "8",
            "liquidity_setup": "strong",
            "displacement_quality": 7,
            "confidence": 0.9,
            "reasons": [],
        },
        "zone-not-dict": "valid",
    }

    assert get_cached_zone_review(cache, "zone-corrupt") is None
    assert get_cached_zone_review(cache, "zone-not-dict") is None


def test_review_zone_with_cache_hit_does_not_call_ai():
    forbidden = _ForbiddenAIService()
    cache = {}
    assert remember_zone_review(
        cache,
        "zone-1",
        parse_zone_review(_zone_audit_response(zone_validity=2)),
    )

    result = review_zone_with_cache({"zone_id": "zone-1"}, cache, forbidden)

    assert result["status"] == "valid"
    assert result["zone_validity"] == 2.0
    assert forbidden.calls == []


def test_review_zone_with_cache_miss_calls_ai_and_stores_verdict():
    ai = _FakeZoneAuditAIService(_zone_audit_response())
    cache = {}

    result = review_zone_with_cache({"zone_id": "zone-2"}, cache, ai)

    assert result["status"] == "valid"
    assert len(ai.calls) == 1
    assert get_cached_zone_review(cache, "zone-2") == result

    # A failed review is not cached, and no AI call happens without one.
    failed = review_zone_with_cache({"zone_id": "zone-3"}, cache, None)
    assert failed["status"] == "uncertain"
    assert get_cached_zone_review(cache, "zone-3") is None


def test_backtest_replay_reads_cache_and_does_not_call_ai():
    # Live scan: the audit verdict is stored in the cache carried by the
    # scan result.
    scan_result = {"symbol": "TEST"}
    cache = zone_audit_cache_from_scan_result(scan_result)
    weak_ai = _FakeZoneAuditAIService(_zone_audit_response(
        zone_validity=2,
        displacement_quality=3,
        confidence=0.9,
    ))
    live = score_smc(
        _smc("buy"),
        _technical("buy"),
        {"primary": "trend_up"},
        ai_service=weak_ai,
        zone_audit_cache=cache,
    ).side("buy")

    assert len(weak_ai.calls) == 1
    assert AI_ZONE_WEAK_REASON in live.breakdown["reason_codes"]
    assert cache, "a valid verdict must be cached by zone id"

    # Persist the scan result (the cache travels with it), then backtest
    # replay over the same data must read the cache, never call the AI,
    # and reproduce the live score.
    persisted = json.loads(json.dumps(scan_result))
    replay_cache = zone_audit_cache_from_scan_result(persisted)

    forbidden = _ForbiddenAIService()
    replay = score_smc(
        _smc("buy"),
        _technical("buy"),
        {"primary": "trend_up"},
        ai_service=forbidden,
        zone_audit_cache=replay_cache,
    ).side("buy")
    assert forbidden.calls == []
    assert replay.score == live.score
    assert replay.breakdown == live.breakdown

    replay_no_ai = score_smc(
        _smc("buy"),
        _technical("buy"),
        {"primary": "trend_up"},
        zone_audit_cache=replay_cache,
    ).side("buy")
    assert replay_no_ai.score == live.score
    assert replay_no_ai.breakdown == live.breakdown


def test_backtest_replay_cache_miss_is_ignored_without_ai():
    baseline = score_smc(
        _smc("buy"),
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy")

    replay = score_smc(
        _smc("buy"),
        _technical("buy"),
        {"primary": "trend_up"},
        zone_audit_cache={},
    ).side("buy")

    assert replay.score == baseline.score
    assert replay.breakdown == baseline.breakdown
    assert AI_ZONE_WEAK_REASON not in replay.breakdown["reason_codes"]


def _analysis_with_ai_review(**review_overrides):
    review = {
        "schema_version": 1,
        "status": "valid",
        "zone_validity": 3,
        "liquidity_setup": "weak",
        "displacement_quality": 2.5,
        "confidence": 0.8,
        "reasons": ["Zone yếu"],
        "review_error": "",
    }
    review.update(review_overrides)
    return {
        "timestamp": "2026-08-06T10:00:00Z",
        "symbol": "XAU/USD",
        "scenario_scores": {"buy": {"total": 9}, "sell": {"total": 2}},
        "scenarios": [{
            "type": "buy",
            "entry_zone_id": "smcz-abc123",
            "entry_zone": [2000.0, 2003.0],
            "stop_loss": 1990.0,
            "take_profit": [2020.0],
            "risk_reward": 2.0,
            "ai_zone_review": review,
        }],
        "decision_summary": {"best_side": "buy", "action": "ready"},
        "trade_permission": {"status": "allowed"},
        "data_quality": {},
        "market_regime": {"primary": "trend_up"},
        "macro": {},
    }


def test_journal_entry_records_ai_zone_review_fields():
    entry = journal_entry_from_analysis(
        _analysis_with_ai_review(),
        mode="scanner_detail",
    )

    assert entry.selected_zone_id == "smcz-abc123"
    assert entry.ai_zone_validity == 3.0
    assert entry.ai_zone_liquidity_setup == "weak"
    assert entry.ai_zone_displacement_quality == 2.5
    assert entry.ai_zone_confidence == 0.8


def test_journal_entry_ignores_uncertain_ai_zone_review():
    entry = journal_entry_from_analysis(
        _analysis_with_ai_review(
            status="uncertain",
            zone_validity=None,
            liquidity_setup=None,
            displacement_quality=None,
            confidence=0.0,
        ),
        mode="scanner_detail",
    )

    assert entry.ai_zone_validity is None
    assert entry.ai_zone_liquidity_setup is None
    assert entry.ai_zone_displacement_quality is None
    assert entry.ai_zone_confidence is None


def test_journal_service_persists_ai_zone_review_fields(temp_db_path):
    service = JournalService(db_path=temp_db_path)

    entry_id = service.create_from_analysis(
        _analysis_with_ai_review(),
        mode="scanner_detail",
    )
    retrieved = service.get_entry(entry_id)

    assert retrieved is not None
    assert retrieved.selected_zone_id == "smcz-abc123"
    assert retrieved.ai_zone_validity == 3.0
    assert retrieved.ai_zone_liquidity_setup == "weak"
    assert retrieved.ai_zone_displacement_quality == 2.5
    assert retrieved.ai_zone_confidence == 0.8
