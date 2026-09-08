"""Cấu hình quét & quyền auto-trade per-symbol — module live, độc lập Backtest.

Lịch sử tách (Backtest removal, 2026-09-08):
- Bước 2: tách ``scan_enabled`` / ``auto_trade_permitted`` khỏi cờ legacy
  ``backtest``; migration idempotent, fail-closed.
- Bước 4b: quyền auto-trade KHÔNG còn phụ thuộc lifecycle kiểm định Backtest
  (hết hạn/version-mismatch không tự tước quyền — quyền là lựa chọn tường
  minh của người dùng, mặc định tắt khi không xác định). Payload chiến lược
  gửi Strategy Router là bản gọn (regime/side/min_score/min_rr) — không bằng
  chứng kiểm định; ``analysis_min_rr`` thay cho việc ghim cứng min_rr=1.3
  theo cờ ``backtest`` trong Decision Engine.

Nguyên tắc an toàn giữ nguyên:
- Không tự bật quyền, không mở rộng danh sách mã khi migration.
- Payload chỉ phát khi CÓ quyền VÀ có cấu hình chiến lược dùng được
  (regime/side hợp lệ, ngưỡng dương) — thiếu một trong hai ⇒ mã chạy
  DEFAULT_RULES, không auto-trade (fail-closed).
- Các cổng an toàn thực thi (order policy, trade gate, entry confirmation,
  execution revalidation, account guard) không nằm ở đây và không đổi.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from config.settings import SymbolScanSettings
from core.scanner_models import SETUP_SCORE_METRIC

# Khóa JSON của cấu trúc phân quyền (Bước 2). Nếu thiếu CẢ HAI trong một
# entry legacy thì entry đó chưa từng được lưu bằng cấu trúc mới → migration.
SCAN_ENABLED_KEY = "scan_enabled"
AUTO_TRADE_PERMITTED_KEY = "auto_trade_permitted"
ANALYSIS_MIN_RR_KEY = "analysis_min_rr"

DEFAULT_ANALYSIS_MIN_RR = 1.3


def has_new_permission_keys(item: dict) -> bool:
    """Entry settings.json đã được lưu bằng cấu trúc phân quyền mới chưa."""

    return SCAN_ENABLED_KEY in item or AUTO_TRADE_PERMITTED_KEY in item


def _legacy_auto_trade_effective(item: dict) -> bool:
    """Quyền auto-trade HIỆU LỰC của entry legacy tại thời điểm lưu.

    Trước Bước 4b, quyền = cờ legacy ``backtest`` sau khi SettingsService tái
    kiểm định fail-closed mỗi lần load (status phải VALIDATED và chưa hết
    hạn). Migration không chạy validator evidence (engine-side), nên dùng
    trạng thái đã lưu làm xấp xỉ best-effort: ``backtest=True`` +
    ``backtest_status=VALIDATED`` + ``backtest_expires_at`` còn hiệu lực.
    Không xác định được ⇒ False (mặc định tắt, không mở rộng quyền).
    """

    if item.get("backtest") is not True:
        return False
    status = str(item.get("backtest_status", "") or "").strip().upper()
    if status != "VALIDATED":
        return False
    expires = str(item.get("backtest_expires_at", "") or "").strip()
    try:
        expiry = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry > datetime.now(timezone.utc)


def migrate_permission_flags(item: dict) -> tuple[bool, bool]:
    """Suy dẫn cờ phân quyền từ entry legacy (chỉ gọi khi thiếu khóa mới).

    - ``scan_enabled = True``: trước Bước 2, mọi mã có entry trong
      ``symbol_settings`` đều nằm trong danh sách quét (bảo toàn danh sách).
    - ``auto_trade_permitted`` = quyền hiệu lực cũ (xem
      ``_legacy_auto_trade_effective``) — bảo toàn 1:1, không mở rộng.

    Trả về ``(scan_enabled, auto_trade_permitted)``.
    """

    return True, _legacy_auto_trade_effective(item)


def migrate_analysis_min_rr(item: dict) -> float:
    """Ngưỡng min_rr Decision Engine THỰC TẾ đang áp dụng cho mã.

    Trước Bước 4b: ``analysis_thresholds_for_symbol`` ghim ``min_rr=1.3`` khi
    cờ mirror ``backtest`` True (config kiểm định active), ngược lại dùng
    ``min_expected_rr or 1.3``. Migration bảo toàn đúng ngưỡng hiệu lực đó:
    - Entry đã có khóa mới (lưu từ Bước 2): cờ mirror ``backtest`` trong file
      là trạng thái sau tái kiểm định tại lần load cuối → dùng trực tiếp.
    - Entry legacy thuần: dùng xấp xỉ quyền hiệu lực (như trên).
    - Entry đã lưu ``analysis_min_rr``: đọc trực tiếp (idempotent).
    """

    if ANALYSIS_MIN_RR_KEY in item:
        try:
            value = float(item.get(ANALYSIS_MIN_RR_KEY))
        except (TypeError, ValueError):
            return DEFAULT_ANALYSIS_MIN_RR
        return value if value > 0 else DEFAULT_ANALYSIS_MIN_RR

    if has_new_permission_keys(item):
        pinned = item.get("backtest") is True
    else:
        pinned = _legacy_auto_trade_effective(item)
    if pinned:
        return DEFAULT_ANALYSIS_MIN_RR
    try:
        value = float(item.get("min_expected_rr") or DEFAULT_ANALYSIS_MIN_RR)
    except (TypeError, ValueError):
        return DEFAULT_ANALYSIS_MIN_RR
    return value if value > 0 else DEFAULT_ANALYSIS_MIN_RR


def apply_settings_row(
    existing: SymbolScanSettings | None,
    *,
    decision_ready: int,
    decision_watch: int,
    decision_wait: int,
    scan_checked: bool,
    auto_trade_checked: bool,
) -> SymbolScanSettings:
    """Ghi nhận lựa chọn người dùng từ bảng Settings (Bước 4b).

    Ready/Watch/Wait thuộc Decision Engine, luôn sửa được. Quyền quét và
    quyền auto-trade là lựa chọn tường minh — KHÔNG kèm điều kiện kiểm định
    Backtest; dữ liệu bằng chứng cũ (nếu có) được giữ nguyên để đọc lịch sử.
    """

    result = replace(existing) if existing is not None else SymbolScanSettings()
    result.decision_ready = int(decision_ready)
    result.decision_watch = int(decision_watch)
    result.decision_wait = int(decision_wait)
    result.scan_enabled = bool(scan_checked)
    result.auto_trade_permitted = bool(auto_trade_checked)
    return result


def resolve_symbol_settings(
    symbol_settings: dict[str, SymbolScanSettings],
    symbol: str,
) -> SymbolScanSettings | None:
    """Tra cứu config theo mã, chấp nhận cả dạng 'USD/CAD' và 'USDCAD'."""

    cfg = symbol_settings.get(symbol)
    if cfg is None and "/" not in symbol and len(symbol) == 6:
        cfg = symbol_settings.get(symbol[:3] + "/" + symbol[3:])
    return cfg


def is_scan_enabled(settings: SymbolScanSettings | None) -> bool:
    # getattr phòng vệ: công cụ UI/test có thể truyền stub không phải
    # SymbolScanSettings — thiếu thuộc tính ⇒ fail-closed (không quét).
    return bool(getattr(settings, "scan_enabled", False))


def is_auto_trade_permitted(settings: SymbolScanSettings | None) -> bool:
    """Quyền auto-trade per-symbol (điều kiện cần, chưa phải điều kiện đủ).

    Điều kiện đủ gồm: toggle auto-trade toàn cục trên màn Scanner, cấu hình
    chiến lược hợp lệ được Strategy Router chấp nhận (đúng mã, side/regime
    hợp lệ, ngưỡng dương), order policy và các safety gate khi vào lệnh.
    """

    return bool(getattr(settings, "auto_trade_permitted", False))


def analysis_thresholds_for_symbol(
    settings: SymbolScanSettings | None,
) -> dict[str, int | float] | None:
    """Ngưỡng Decision Engine per-symbol — độc lập Backtest (Bước 4b).

    ``min_rr`` đọc từ cấu hình tường minh ``analysis_min_rr`` (migration bảo
    toàn ngưỡng thực tế cũ); không còn ghim 1.3 theo cờ legacy ``backtest``.
    """

    if settings is None:
        return None
    try:
        min_rr = float(getattr(settings, "analysis_min_rr", 0) or 0)
    except (TypeError, ValueError):
        min_rr = 0.0
    return {
        "ready": settings.decision_ready,
        "watch": settings.decision_watch,
        "wait": settings.decision_wait,
        "min_score_gap": 10,
        "min_rr": min_rr if min_rr > 0 else DEFAULT_ANALYSIS_MIN_RR,
    }


def serialize_symbol_auto_trade_config(
    settings: SymbolScanSettings | None,
    *,
    symbol: str,
) -> dict[str, object] | None:
    """Payload chiến lược gọn cho Strategy Router — không bằng chứng Backtest.

    Trả None khi không có cấu hình chiến lược dùng được (thiếu regime/side
    hợp lệ hoặc ngưỡng không dương) ⇒ mã chạy DEFAULT_RULES, không
    auto-trade (fail-closed). Bước 6: key ``config_id`` (provenance legacy)
    đã gỡ cùng field evidence trong model — observability đọc ``config.get
    ("config_id", "")`` vẫn an toàn (nhận rỗng).
    """

    if settings is None:
        return None
    regime = str(settings.auto_trade_regime or "").strip().lower()
    side = str(settings.auto_trade_side or "").strip().lower()
    min_score = int(settings.min_score or settings.decision_ready or 0)
    try:
        min_rr = float(settings.min_expected_rr or 0)
    except (TypeError, ValueError):
        min_rr = 0.0
    if side not in {"buy", "sell", "best"}:
        return None
    if not regime:
        return None
    if min_score <= 0 or min_rr <= 0:
        return None
    return {
        "symbol": symbol,
        "regime": regime,
        "allowed_regimes": [regime],
        "side": side,
        "min_score": min_score,
        "min_rr": min_rr,
        "score_metric": SETUP_SCORE_METRIC,
    }


def build_symbol_auto_trade(
    symbol_settings: dict[str, SymbolScanSettings],
    symbols: list[str],
) -> dict[str, dict]:
    """Build ``ScannerRequest.symbol_auto_trade`` theo quyền độc lập.

    Chỉ phát payload cho mã CÓ quyền auto-trade (``auto_trade_permitted`` —
    lựa chọn tường minh của người dùng) VÀ có cấu hình chiến lược dùng được.
    Không điều kiện kiểm định/hết hạn Backtest (Bước 4b); mọi kiểm tra an
    toàn thực thi vẫn nằm ở Router/order policy/gates như trước.
    """

    result: dict[str, dict] = {}
    for symbol in symbols:
        cfg = resolve_symbol_settings(symbol_settings, symbol)
        if not is_auto_trade_permitted(cfg):
            continue
        payload = serialize_symbol_auto_trade_config(cfg, symbol=symbol)
        if payload is not None:
            result[symbol] = payload
    return result


def reconcile_scan_enabled_symbols(
    enabled_symbols: list[str],
    *,
    symbol: str,
    scan_enabled: bool,
) -> list[str]:
    """Cập nhật danh sách mã bật quét theo lựa chọn tường minh của người dùng.

    Thành viên danh sách chỉ phụ thuộc cờ ``scan_enabled``: tick ⇒ thêm,
    bỏ tick ⇒ xóa. Quyền auto-trade không ảnh hưởng danh sách này.
    """

    result = list(dict.fromkeys(enabled_symbols))
    if scan_enabled:
        if symbol not in result:
            result.append(symbol)
    else:
        result = [item for item in result if item != symbol]
    return result
