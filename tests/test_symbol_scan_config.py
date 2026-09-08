"""Bước 2 + 4b gỡ Backtest (2026-09-08): phân quyền quét / auto-trade độc lập.

Kiểm thử migration legacy → cấu trúc mới (cờ quyền + ngưỡng analysis_min_rr),
vòng lưu/đọc lại, và các gate quyền auto-trade độc lập với kiểm định
Backtest. Toàn bộ dùng file settings tạm (tmp_path) + hàm thuần — không
MT5, không mạng, không gửi lệnh thật.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from config.settings import SymbolScanSettings
from core.symbol_scan_config import (
    DEFAULT_ANALYSIS_MIN_RR,
    analysis_thresholds_for_symbol,
    apply_settings_row,
    build_symbol_auto_trade,
    has_new_permission_keys,
    is_auto_trade_permitted,
    is_scan_enabled,
    migrate_analysis_min_rr,
    migrate_permission_flags,
    reconcile_scan_enabled_symbols,
    resolve_symbol_settings,
    serialize_symbol_auto_trade_config,
)
from services.settings_service import SettingsService


def _configured_symbol_settings() -> SymbolScanSettings:
    """Config chiến lược per-symbol đầy đủ (regime/side/ngưỡng dương).

    Bước 6: model không còn field ``backtest_*`` — evidence chỉ tồn tại
    trong file settings.json cũ (xem ``_legacy_item``).
    """

    return SymbolScanSettings(
        min_score=65,
        auto_trade_regime="range",
        auto_trade_side="buy",
        min_expected_rr=1.5,
    )


def _legacy_item(cfg: SymbolScanSettings) -> dict:
    """Serialize như file settings.json thời kỳ trước Bước 2 (không khóa mới).

    Bước 6: evidence ``backtest_*`` không còn trong model — nạp tường minh
    các khóa legacy vào raw dict, đúng như chúng tồn tại trong file cũ.
    """

    item = asdict(cfg)
    item.pop("scan_enabled", None)
    item.pop("auto_trade_permitted", None)
    item.pop("analysis_min_rr", None)
    expires = datetime.now(timezone.utc) + timedelta(days=365)
    item.update({
        "backtest": True,
        "backtest_config_id": "EURUSD-range-buy-v3",
        "backtest_status": "VALIDATED",
        "backtest_expires_at": expires.isoformat(),
    })
    assert not has_new_permission_keys(item)
    return item


def _save_raw(service: SettingsService, *, enabled: list[str], symbols: dict) -> None:
    service.storage.save({
        "ai": {},
        "trading": {
            "enabled_symbols": enabled,
            "symbol_settings": symbols,
        },
    })


# ---------------------------------------------------------------------------
# Migration legacy → cấu trúc mới
# ---------------------------------------------------------------------------


def test_migrate_permission_flags_defaults_closed():
    # Không có khóa mới, không có cờ legacy → quét giữ nguyên (entry đã tồn
    # tại là được quét theo hành vi cũ), auto-trade mặc định TẮT.
    assert migrate_permission_flags({}) == (True, False)
    assert migrate_permission_flags({"backtest": False}) == (True, False)
    assert migrate_permission_flags({"backtest": None}) == (True, False)
    # Bước 4b: cờ legacy backtest=True MỘT MÌNH không còn đủ — quyền hiệu
    # lực cũ đòi status VALIDATED + expiry còn hạn (không rõ ⇒ tắt).
    assert migrate_permission_flags({"backtest": True}) == (True, False)
    assert migrate_permission_flags({
        "backtest": True,
        "backtest_status": "VALIDATED",
        "backtest_expires_at": "2020-01-01T00:00:00+00:00",
    }) == (True, False)  # hết hạn ⇒ tắt
    future = (
        datetime.now(timezone.utc) + timedelta(days=30)
    ).isoformat()
    assert migrate_permission_flags({
        "backtest": True,
        "backtest_status": "VALIDATED",
        "backtest_expires_at": future,
    }) == (True, True)  # quyền hiệu lực cũ được bảo toàn 1:1


def test_migration_legacy_no_evidence_keeps_scan_denies_auto_trade(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    _save_raw(
        service,
        enabled=["EUR/USD"],
        symbols={
            "EUR/USD": {
                "backtest": True,
                "min_score": 68,
                "auto_trade_regime": "range",
                "auto_trade_side": "buy",
                "min_expected_rr": 1.5,
            },
        },
    )
    trading = service.load().trading
    cfg = trading.symbol_settings["EUR/USD"]
    # Bước 4b/6: dữ liệu legacy đọc nguyên trạng từ file (không tái kiểm
    # định khi load, model không còn field evidence); quyền auto-trade suy
    # dẫn từ trạng thái hiệu lực cũ → TẮT vì không có status VALIDATED+expiry.
    assert cfg.auto_trade_permitted is False
    # Danh sách mã bật quét được bảo toàn.
    assert cfg.scan_enabled is True
    assert trading.enabled_symbols == ["EUR/USD"]
    assert build_symbol_auto_trade(trading.symbol_settings, ["EUR/USD"]) == {}


def test_migration_legacy_validated_preserves_permission(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    _save_raw(
        service,
        enabled=["EUR/USD"],
        symbols={"EUR/USD": _legacy_item(_configured_symbol_settings())},
    )
    trading = service.load().trading
    cfg = trading.symbol_settings["EUR/USD"]
    assert cfg.scan_enabled is True
    assert cfg.auto_trade_permitted is True
    assert trading.enabled_symbols == ["EUR/USD"]
    payloads = build_symbol_auto_trade(trading.symbol_settings, ["EUR/USD"])
    assert set(payloads) == {"EUR/USD"}
    # Bước 4b: payload gọn (không bằng chứng kiểm định) — router lean kiểm
    # tra symbol/side/regime/ngưỡng.
    payload = payloads["EUR/USD"]
    assert payload["symbol"] == "EUR/USD"
    assert payload["side"] == "buy"
    assert payload["regime"] == "range"
    assert payload["allowed_regimes"] == ["range"]
    assert payload["min_score"] == 65
    assert payload["min_rr"] == 1.5
    assert "status" not in payload
    assert "validation_fingerprint" not in payload


def test_migration_is_idempotent_and_persists_new_keys(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    _save_raw(
        service,
        enabled=["EUR/USD"],
        symbols={"EUR/USD": _legacy_item(_configured_symbol_settings())},
    )
    first = service.load()
    second = service.load()
    for loaded in (first, second):
        cfg = loaded.trading.symbol_settings["EUR/USD"]
        assert cfg.scan_enabled is True
        assert cfg.auto_trade_permitted is True
        assert loaded.trading.enabled_symbols == ["EUR/USD"]

    # Save cấu trúc mới rồi nạp lại: khóa mới thắng, kết quả không đổi.
    service.save(first)
    stored = service.storage.load()["trading"]["symbol_settings"]["EUR/USD"]
    assert has_new_permission_keys(stored)
    assert stored["scan_enabled"] is True
    assert stored["auto_trade_permitted"] is True
    third = service.load()
    cfg = third.trading.symbol_settings["EUR/USD"]
    assert cfg.scan_enabled is True
    assert cfg.auto_trade_permitted is True
    assert third.trading.enabled_symbols == ["EUR/USD"]


def test_migration_reruns_safely_on_legacy_file(tmp_path):
    """Migration thuần đọc: nạp lại file legacy nhiều lần cho cùng kết quả."""

    service = SettingsService(tmp_path / "settings.json")
    legacy_item = _legacy_item(_configured_symbol_settings())
    _save_raw(service, enabled=["EUR/USD"], symbols={"EUR/USD": legacy_item})
    results = [service.load() for _ in range(3)]
    for loaded in results:
        cfg = loaded.trading.symbol_settings["EUR/USD"]
        assert (cfg.scan_enabled, cfg.auto_trade_permitted) == (True, True)
    # File legacy không bị ghi lại cho tới khi save() được gọi.
    stored = service.storage.load()["trading"]["symbol_settings"]["EUR/USD"]
    assert not has_new_permission_keys(stored)


# ---------------------------------------------------------------------------
# Vòng lưu / đọc lại cấu trúc mới
# ---------------------------------------------------------------------------


def test_new_structure_round_trip_scan_without_auto_trade(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    settings = service.load()
    cfg = _configured_symbol_settings()
    cfg.scan_enabled = True
    cfg.auto_trade_permitted = False  # quét nhưng KHÔNG cấp quyền giao dịch
    settings.trading.symbol_settings["EUR/USD"] = cfg
    settings.trading.enabled_symbols = ["EUR/USD"]
    service.save(settings)

    trading = service.load().trading
    loaded = trading.symbol_settings["EUR/USD"]
    assert loaded.scan_enabled is True
    assert loaded.auto_trade_permitted is False
    assert trading.enabled_symbols == ["EUR/USD"]
    # Không có quyền → không phát payload auto-trade.
    assert build_symbol_auto_trade(trading.symbol_settings, ["EUR/USD"]) == {}


def test_load_filters_enabled_symbols_by_scan_enabled(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    settings = service.load()
    scanned = _configured_symbol_settings()
    scanned.scan_enabled = True
    scanned.auto_trade_permitted = True
    not_scanned = SymbolScanSettings(scan_enabled=False)
    settings.trading.symbol_settings["EUR/USD"] = scanned
    settings.trading.symbol_settings["GBP/USD"] = not_scanned
    settings.trading.enabled_symbols = ["EUR/USD", "GBP/USD"]
    service.save(settings)

    trading = service.load().trading
    assert trading.enabled_symbols == ["EUR/USD"]


def test_auto_trade_permission_is_independent_of_backtest_expiry(tmp_path):
    """Bước 4b (thay đổi hành vi CÓ CHỦ ĐÍCH): hết hạn bằng chứng Backtest
    không còn tự tước quyền auto-trade — quyền là lựa chọn tường minh của
    người dùng (cấp/từ chối trong Settings). An toàn thực thi vẫn do Router
    lean + order policy + gates đảm nhiệm; dữ liệu evidence đọc nguyên trạng.
    """

    service = SettingsService(tmp_path / "settings.json")
    cfg = _configured_symbol_settings()
    cfg.scan_enabled = True
    cfg.auto_trade_permitted = True
    item = asdict(cfg)
    item["backtest_expires_at"] = "2020-01-01T00:00:00+00:00"
    _save_raw(service, enabled=["EUR/USD"], symbols={"EUR/USD": item})

    trading = service.load().trading
    loaded = trading.symbol_settings["EUR/USD"]
    # Evidence legacy trong file không bị load chỉnh sửa (đọc nguyên trạng).
    stored = service.storage.load()["trading"]["symbol_settings"]["EUR/USD"]
    assert stored["backtest_expires_at"] == "2020-01-01T00:00:00+00:00"
    # Quyền độc lập lifecycle: vẫn do người dùng nắm.
    assert loaded.auto_trade_permitted is True
    assert loaded.scan_enabled is True
    assert trading.enabled_symbols == ["EUR/USD"]
    # Payload gọn vẫn hợp lệ với Router lean (regime/side/ngưỡng đầy đủ).
    payloads = build_symbol_auto_trade(trading.symbol_settings, ["EUR/USD"])
    assert set(payloads) == {"EUR/USD"}


# ---------------------------------------------------------------------------
# Gate quyền auto-trade khi tạo ScannerRequest
# ---------------------------------------------------------------------------


def test_build_symbol_auto_trade_requires_permission_flag():
    validated = _configured_symbol_settings()
    permitted = _configured_symbol_settings()
    permitted.auto_trade_permitted = True
    symbol_settings = {
        "EUR/USD": validated,   # cấu hình đầy đủ nhưng CHƯA cấp quyền
        "GBP/USD": permitted,
    }
    payloads = build_symbol_auto_trade(
        symbol_settings, ["EUR/USD", "GBP/USD"]
    )
    assert set(payloads) == {"GBP/USD"}


def test_build_symbol_auto_trade_resolves_slash_variants():
    permitted = _configured_symbol_settings()
    permitted.auto_trade_permitted = True
    payloads = build_symbol_auto_trade({"EUR/USD": permitted}, ["EURUSD"])
    assert set(payloads) == {"EURUSD"}
    assert payloads["EURUSD"]["symbol"] == "EURUSD"


def test_build_symbol_auto_trade_skips_missing_and_unconfigured():
    # Có quyền nhưng KHÔNG có cấu hình chiến lược dùng được → None (chạy
    # DEFAULT_RULES, không auto-trade — fail-closed, không mở rộng quyền).
    draft = SymbolScanSettings(auto_trade_permitted=True)  # regime/side rỗng
    payloads = build_symbol_auto_trade(
        {"EUR/USD": draft}, ["EUR/USD", "USD/JPY"]
    )
    assert payloads == {}


def test_serialize_symbol_auto_trade_config_fail_closed_shapes():
    assert serialize_symbol_auto_trade_config(None, symbol="EUR/USD") is None
    # Thiếu từng thành phần chiến lược → None.
    assert serialize_symbol_auto_trade_config(
        SymbolScanSettings(auto_trade_side="buy", min_score=65,
                           min_expected_rr=1.5),
        symbol="EUR/USD",
    ) is None  # thiếu regime
    assert serialize_symbol_auto_trade_config(
        SymbolScanSettings(auto_trade_regime="range", min_score=65,
                           min_expected_rr=1.5),
        symbol="EUR/USD",
    ) is None  # thiếu side
    # min_score=0 → fallback decision_ready (parity serialize cũ).
    fallback = serialize_symbol_auto_trade_config(
        SymbolScanSettings(auto_trade_regime="range", auto_trade_side="buy",
                           min_expected_rr=1.5),
        symbol="EUR/USD",
    )
    assert fallback is not None and fallback["min_score"] == 65
    # Không có ngưỡng dương nào → None (fail-closed).
    assert serialize_symbol_auto_trade_config(
        SymbolScanSettings(auto_trade_regime="range", auto_trade_side="buy",
                           decision_ready=0, min_expected_rr=0.0),
        symbol="EUR/USD",
    ) is None
    payload = serialize_symbol_auto_trade_config(
        SymbolScanSettings(
            auto_trade_regime="range", auto_trade_side="best",
            min_score=68, min_expected_rr=1.8,
        ),
        symbol="EUR/USD",
    )
    assert payload == {
        "symbol": "EUR/USD",
        "regime": "range",
        "allowed_regimes": ["range"],
        "side": "best",
        "min_score": 68,
        "min_rr": 1.8,
        "score_metric": payload["score_metric"],
    }


def test_permission_helpers_fail_closed_on_none():
    assert is_scan_enabled(None) is False
    assert is_auto_trade_permitted(None) is False
    assert resolve_symbol_settings({}, "EURUSD") is None
    cfg = SymbolScanSettings()
    assert resolve_symbol_settings({"EUR/USD": cfg}, "EURUSD") is cfg


# ---------------------------------------------------------------------------
# Ghi nhận lựa chọn người dùng + reconcile danh sách quét
# ---------------------------------------------------------------------------


def test_apply_settings_row_records_explicit_user_choices():
    # Bước 4b: quyền là lựa chọn tường minh — không điều kiện kiểm định.
    draft = SymbolScanSettings()
    result = apply_settings_row(
        draft,
        decision_ready=70,
        decision_watch=60,
        decision_wait=55,
        scan_checked=True,
        auto_trade_checked=True,
    )
    assert result.scan_enabled is True
    assert result.auto_trade_permitted is True
    assert (result.decision_ready, result.decision_watch, result.decision_wait) == (70, 60, 55)

    # Không tick ⇒ tắt (mặc định an toàn), evidence cũ giữ nguyên để đọc.
    validated = _configured_symbol_settings()
    result2 = apply_settings_row(
        validated,
        decision_ready=65,
        decision_watch=60,
        decision_wait=55,
        scan_checked=True,
        auto_trade_checked=False,
    )
    assert result2.auto_trade_permitted is False
    # Cấu hình chiến lược (field live) giữ nguyên qua replace().
    assert result2.auto_trade_regime == validated.auto_trade_regime
    assert result2.min_expected_rr == validated.min_expected_rr


def test_analysis_min_rr_migration_preserves_effective_threshold(tmp_path):
    """Req 1: ngưỡng Decision Engine thực tế được bảo toàn khi migration."""

    # Legacy active (quyền hiệu lực cũ) → trước ghim 1.3 → migration 1.3,
    # dù min_expected_rr (RR chiến lược auto-trade) là 1.5.
    active = _legacy_item(_configured_symbol_settings())
    assert migrate_analysis_min_rr(active) == DEFAULT_ANALYSIS_MIN_RR

    # Legacy không active → dùng min_expected_rr như công thức cũ.
    assert migrate_analysis_min_rr({
        "backtest": False, "min_expected_rr": 2.0,
    }) == 2.0
    assert migrate_analysis_min_rr({}) == DEFAULT_ANALYSIS_MIN_RR
    assert migrate_analysis_min_rr({"min_expected_rr": 0}) == (
        DEFAULT_ANALYSIS_MIN_RR
    )

    # File đã có khóa mới → đọc trực tiếp (idempotent).
    assert migrate_analysis_min_rr({"analysis_min_rr": 1.7}) == 1.7
    assert migrate_analysis_min_rr({"analysis_min_rr": "abc"}) == (
        DEFAULT_ANALYSIS_MIN_RR
    )

    # Vòng save/load thực tế qua SettingsService.
    service = SettingsService(tmp_path / "settings.json")
    _save_raw(service, enabled=["EUR/USD"], symbols={"EUR/USD": active})
    cfg = service.load().trading.symbol_settings["EUR/USD"]
    assert cfg.analysis_min_rr == DEFAULT_ANALYSIS_MIN_RR
    assert analysis_thresholds_for_symbol(cfg)["min_rr"] == (
        DEFAULT_ANALYSIS_MIN_RR
    )
    service.save(service.load())
    stored = service.storage.load()["trading"]["symbol_settings"]["EUR/USD"]
    assert stored["analysis_min_rr"] == DEFAULT_ANALYSIS_MIN_RR
    # Nạp lại từ cấu trúc mới: không đổi.
    again = service.load().trading.symbol_settings["EUR/USD"]
    assert again.analysis_min_rr == DEFAULT_ANALYSIS_MIN_RR


def test_analysis_thresholds_use_explicit_analysis_min_rr():
    cfg = SymbolScanSettings(
        decision_ready=70, decision_watch=62, decision_wait=58,
        analysis_min_rr=1.8,
        min_expected_rr=2.5,  # RR chiến lược auto-trade — KHÔNG ảnh hưởng ngưỡng
    )
    assert analysis_thresholds_for_symbol(cfg) == {
        "ready": 70,
        "watch": 62,
        "wait": 58,
        "min_score_gap": 10,
        "min_rr": 1.8,
    }
    assert analysis_thresholds_for_symbol(None) is None
    # analysis_min_rr hỏng/0 → default an toàn.
    broken = SymbolScanSettings(analysis_min_rr=0.0)
    assert analysis_thresholds_for_symbol(broken)["min_rr"] == (
        DEFAULT_ANALYSIS_MIN_RR
    )


def test_reconcile_scan_enabled_symbols_add_remove_dedupe():
    result = reconcile_scan_enabled_symbols(
        ["EUR/USD"], symbol="GBP/USD", scan_enabled=True
    )
    assert result == ["EUR/USD", "GBP/USD"]
    result = reconcile_scan_enabled_symbols(
        result, symbol="GBP/USD", scan_enabled=True
    )
    assert result == ["EUR/USD", "GBP/USD"]  # không nhân bản
    result = reconcile_scan_enabled_symbols(
        result, symbol="EUR/USD", scan_enabled=False
    )
    assert result == ["GBP/USD"]
    result = reconcile_scan_enabled_symbols(
        result, symbol="EUR/USD", scan_enabled=False
    )
    assert result == ["GBP/USD"]  # xóa mã không có trong danh sách: no-op


def test_obsolete_backtest_flags_are_read_compatible_but_not_rewritten(
    tmp_path,
) -> None:
    """Port từ test_backtest_simplification_phase5 (Bước 5 xóa engine):
    khóa feature cũ bị bỏ qua; bằng chứng legacy đọc nguyên trạng; quyền
    auto-trade độc lập mặc định tắt khi trạng thái hiệu lực cũ không rõ."""

    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({
        "features": {
            "scanner_architecture_v2": True,
            "auto_trade_v2": True,
            "backtest_config_v2": True,
            "backtest_engine_v2": True,
            "smc_scoring_mode": "v2",
        },
        "trading": {
            "enabled_symbols": ["EUR/USD"],
            "symbol_settings": {
                "EUR/USD": {
                    "enabled": True,
                    "min_score": 77,
                    "backtest": True,
                    "backtest_status": "VALIDATED",
                    "backtest_validation_fingerprint": "evidence-kept",
                }
            },
        },
    })

    settings = service.load()
    symbol = settings.trading.symbol_settings["EUR/USD"]
    # Removed 2026-08-16: leftover on-disk keys are ignored, not loaded.
    assert not hasattr(settings.features, "scanner_architecture_v2")
    assert not hasattr(settings.features, "auto_trade_v2")
    assert not hasattr(settings.features, "smc_scoring_mode")
    assert not hasattr(settings.features, "backtest_config_v2")
    assert not hasattr(settings.features, "backtest_engine_v2")
    assert symbol.min_score == 77
    # Bước 6 (2026-09-09): field evidence đã gỡ khỏi model — khóa legacy
    # trên disk chỉ được ĐỌC bởi migration (suy dẫn quyền/ngưỡng), không nạp
    # vào model. Entry thiếu expiry ⇒ không xác định được quyền cũ ⇒ TẮT.
    assert not hasattr(symbol, "backtest_status")
    assert not hasattr(symbol, "backtest_validation_fingerprint")
    assert symbol.auto_trade_permitted is False
    assert symbol.scan_enabled is True  # bảo toàn danh sách quét
    # Load thuần đọc: file chưa save vẫn giữ nguyên khóa legacy.
    before = service.storage.load()["trading"]["symbol_settings"]["EUR/USD"]
    assert before["backtest_validation_fingerprint"] == "evidence-kept"

    service.save(settings)
    stored = service.storage.load()
    assert "backtest_config_v2" not in stored["features"]
    assert "backtest_engine_v2" not in stored["features"]
    # Flags removed from the model must also disappear on the next save.
    assert "scanner_architecture_v2" not in stored["features"]
    assert "auto_trade_v2" not in stored["features"]
    stored_symbol = stored["trading"]["symbol_settings"]["EUR/USD"]
    assert stored_symbol["min_score"] == 77
    # Cùng convention: khóa evidence đã gỡ khỏi model biến mất ở lần save kế
    # tiếp (kết quả Backtest lưu trữ ở app_data/backtests KHÔNG bị đụng).
    assert "backtest_validation_fingerprint" not in stored_symbol
    assert stored_symbol["scan_enabled"] is True
    assert stored_symbol["auto_trade_permitted"] is False
