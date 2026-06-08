"""Centralised reason codes for scoring, gating, and decision logic.

Every signal addition, penalty, warning, and block throughout the system
maps to one of these codes so that UI, AI commentary, journal, and tests
can consume a stable identifier instead of free-form text.

Phase 9: definition only — no engine integration yet.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Trend / Location / SMC
# ---------------------------------------------------------------------------
TREND_D1_H4_ALIGNED = "TREND_D1_H4_ALIGNED"
PRICE_NEAR_SUPPORT = "PRICE_NEAR_SUPPORT"
PRICE_NEAR_RESISTANCE = "PRICE_NEAR_RESISTANCE"
CHOCH_AGAINST_DIRECTION = "CHOCH_AGAINST_DIRECTION"
ZONE_BROKEN = "ZONE_BROKEN"
SWEEP_DISPLACEMENT_M15_ALIGNED = "SWEEP_DISPLACEMENT_M15_ALIGNED"

# ---------------------------------------------------------------------------
# M15
# ---------------------------------------------------------------------------
M15_STRICT_CONFIRMED = "M15_STRICT_CONFIRMED"
M15_LOOSE_CONFIRMATION = "M15_LOOSE_CONFIRMATION"
M15_NOT_CONFIRMED = "M15_NOT_CONFIRMED"
M15_DATA_UNAVAILABLE = "M15_DATA_UNAVAILABLE"

# ---------------------------------------------------------------------------
# Spread / News / Data / MT5
# ---------------------------------------------------------------------------
SPREAD_NORMAL = "SPREAD_NORMAL"
SPREAD_CAUTION = "SPREAD_CAUTION"
SPREAD_ABNORMAL = "SPREAD_ABNORMAL"
HIGH_IMPACT_NEWS_NEARBY = "HIGH_IMPACT_NEWS_NEARBY"
DATA_QUALITY_WARNING = "DATA_QUALITY_WARNING"
MT5_NOT_READY = "MT5_NOT_READY"

# ---------------------------------------------------------------------------
# Expected effective R:R
# ---------------------------------------------------------------------------
EXPECTED_RR_OK = "EXPECTED_RR_OK"
EXPECTED_RR_TOO_LOW = "EXPECTED_RR_TOO_LOW"

# ---------------------------------------------------------------------------
# Account guard
# ---------------------------------------------------------------------------
DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
WEEKLY_LOSS_LIMIT_REACHED = "WEEKLY_LOSS_LIMIT_REACHED"
MAX_CONSECUTIVE_LOSSES_REACHED = "MAX_CONSECUTIVE_LOSSES_REACHED"
MAX_OPEN_RISK_REACHED = "MAX_OPEN_RISK_REACHED"

# ---------------------------------------------------------------------------
# Macro
# ---------------------------------------------------------------------------
MACRO_ALIGNED = "MACRO_ALIGNED"
MACRO_UNCLEAR = "MACRO_UNCLEAR"
MACRO_CONFLICT = "MACRO_CONFLICT"

# ---------------------------------------------------------------------------
# Score gap
# ---------------------------------------------------------------------------
BUY_SELL_SCORE_GAP_LOW = "BUY_SELL_SCORE_GAP_LOW"

# ---------------------------------------------------------------------------
# Statistical edge (Phase 10+ preparation)
# ---------------------------------------------------------------------------
STAT_EDGE_NOT_ENOUGH_DATA = "STAT_EDGE_NOT_ENOUGH_DATA"
STAT_EDGE_POSITIVE = "STAT_EDGE_POSITIVE"
STAT_EDGE_NEGATIVE = "STAT_EDGE_NEGATIVE"

# ---------------------------------------------------------------------------
# Execution quality (Phase 11)
# ---------------------------------------------------------------------------
EXECUTION_QUALITY_OK = "EXECUTION_QUALITY_OK"
EXECUTION_CHASED_PRICE = "EXECUTION_CHASED_PRICE"
EXECUTION_OVERSIZED = "EXECUTION_OVERSIZED"
EXECUTION_MOVED_SL_FURTHER = "EXECUTION_MOVED_SL_FURTHER"
EXECUTION_REVENGE_CONFIRMED = "EXECUTION_REVENGE_CONFIRMED"
EXECUTION_MANUAL_PENALTY = "EXECUTION_MANUAL_PENALTY"
EXECUTION_DATA_INCOMPLETE = "EXECUTION_DATA_INCOMPLETE"

# ---------------------------------------------------------------------------
# Trade mistake detector (Phase 12)
# ---------------------------------------------------------------------------
MISTAKE_ENTERED_TOO_EARLY = "MISTAKE_ENTERED_TOO_EARLY"
MISTAKE_CHASED_PRICE = "MISTAKE_CHASED_PRICE"
MISTAKE_IGNORED_M15 = "MISTAKE_IGNORED_M15"
MISTAKE_IGNORED_NEWS = "MISTAKE_IGNORED_NEWS"
MISTAKE_MOVED_STOP_LOSS = "MISTAKE_MOVED_STOP_LOSS"
MISTAKE_CLOSED_TOO_EARLY = "MISTAKE_CLOSED_TOO_EARLY"
MISTAKE_OVERSIZED_POSITION = "MISTAKE_OVERSIZED_POSITION"
MISTAKE_REVENGE_TRADE_WARNING = "MISTAKE_REVENGE_TRADE_WARNING"
MISTAKE_REVENGE_TRADE_CONFIRMED = "MISTAKE_REVENGE_TRADE_CONFIRMED"
MISTAKE_DATA_INCOMPLETE = "MISTAKE_DATA_INCOMPLETE"
MISTAKE_DETECTOR_OK = "MISTAKE_DETECTOR_OK"

# ---------------------------------------------------------------------------
# Final score (Phase 13)
# ---------------------------------------------------------------------------
FINAL_SCORE_OK = "FINAL_SCORE_OK"
FINAL_SCORE_DATA_INCOMPLETE = "FINAL_SCORE_DATA_INCOMPLETE"
FINAL_SCORE_SIGNAL_DOMINANT = "FINAL_SCORE_SIGNAL_DOMINANT"
FINAL_SCORE_EVIDENCE_NEUTRAL = "FINAL_SCORE_EVIDENCE_NEUTRAL"
FINAL_SCORE_EVIDENCE_POSITIVE = "FINAL_SCORE_EVIDENCE_POSITIVE"
FINAL_SCORE_EVIDENCE_NEGATIVE = "FINAL_SCORE_EVIDENCE_NEGATIVE"
FINAL_SCORE_EXECUTION_STRONG = "FINAL_SCORE_EXECUTION_STRONG"
FINAL_SCORE_EXECUTION_WEAK = "FINAL_SCORE_EXECUTION_WEAK"

# ---------------------------------------------------------------------------
# Decision engine (Phase 14)
# ---------------------------------------------------------------------------
DECISION_READY_TO_TRADE = "DECISION_READY_TO_TRADE"
DECISION_WAITING_CONFIRMATION = "DECISION_WAITING_CONFIRMATION"
DECISION_AGGRESSIVE_SETUP = "DECISION_AGGRESSIVE_SETUP"
DECISION_WATCH_ONLY = "DECISION_WATCH_ONLY"
DECISION_TRADE_BLOCKED = "DECISION_TRADE_BLOCKED"
DECISION_STAND_ASIDE = "DECISION_STAND_ASIDE"
DECISION_DATA_INCOMPLETE = "DECISION_DATA_INCOMPLETE"
DECISION_GATE_BLOCKED = "DECISION_GATE_BLOCKED"
DECISION_GATE_CAPPED = "DECISION_GATE_CAPPED"
DECISION_SCORE_GAP_LOW = "DECISION_SCORE_GAP_LOW"
DECISION_ENTRY_NOT_CONFIRMED = "DECISION_ENTRY_NOT_CONFIRMED"
DECISION_FINAL_SCORE_STRONG = "DECISION_FINAL_SCORE_STRONG"
DECISION_FINAL_SCORE_MODERATE = "DECISION_FINAL_SCORE_MODERATE"
DECISION_FINAL_SCORE_WEAK = "DECISION_FINAL_SCORE_WEAK"

# ---------------------------------------------------------------------------
# Scanner ranking (Phase 15)
# ---------------------------------------------------------------------------
SCANNER_RANKING_READY_NOW = "SCANNER_RANKING_READY_NOW"
SCANNER_RANKING_WAITING_CONFIRMATION = "SCANNER_RANKING_WAITING_CONFIRMATION"
SCANNER_RANKING_WATCH_ZONE = "SCANNER_RANKING_WATCH_ZONE"
SCANNER_RANKING_BLOCKED = "SCANNER_RANKING_BLOCKED"
SCANNER_OPPORTUNITY_SCORE_OK = "SCANNER_OPPORTUNITY_SCORE_OK"
SCANNER_OPPORTUNITY_DATA_INCOMPLETE = "SCANNER_OPPORTUNITY_DATA_INCOMPLETE"
SCANNER_PROXIMITY_IN_ZONE = "SCANNER_PROXIMITY_IN_ZONE"
SCANNER_PROXIMITY_NEAR_ZONE = "SCANNER_PROXIMITY_NEAR_ZONE"
SCANNER_PROXIMITY_FAR = "SCANNER_PROXIMITY_FAR"
SCANNER_RR_STRONG = "SCANNER_RR_STRONG"
SCANNER_RR_WEAK = "SCANNER_RR_WEAK"
SCANNER_NEWS_PENALTY = "SCANNER_NEWS_PENALTY"
SCANNER_SPREAD_PENALTY = "SCANNER_SPREAD_PENALTY"

# ---------------------------------------------------------------------------
# Vietnamese messages
# ---------------------------------------------------------------------------

REASON_CODE_MESSAGES: dict[str, str] = {
    # Trend / Location / SMC
    TREND_D1_H4_ALIGNED: "Xu hướng D1 và H4 đồng thuận.",
    PRICE_NEAR_SUPPORT: "Giá đang gần vùng hỗ trợ.",
    PRICE_NEAR_RESISTANCE: "Giá đang gần vùng kháng cự.",
    CHOCH_AGAINST_DIRECTION: "CHOCH ngược hướng giao dịch, giới hạn điểm tối đa.",
    ZONE_BROKEN: "Vùng hỗ trợ/kháng cự đã bị phá, không còn đáng tin cậy.",
    SWEEP_DISPLACEMENT_M15_ALIGNED: "Quét thanh khoản + displacement + M15 strict cùng hướng, tăng chất lượng entry.",
    # M15
    M15_STRICT_CONFIRMED: "M15 xác nhận chặt, tín hiệu entry đạt yêu cầu.",
    M15_LOOSE_CONFIRMATION: "M15 xác nhận lỏng, cần theo dõi thêm trước khi vào lệnh.",
    M15_NOT_CONFIRMED: "M15 chưa xác nhận tín hiệu vào lệnh.",
    M15_DATA_UNAVAILABLE: "Thiếu dữ liệu M15, không thể xác nhận entry.",
    # Spread / News / Data / MT5
    SPREAD_NORMAL: "Spread đang ở mức bình thường.",
    SPREAD_CAUTION: "Spread đang cao hơn bình thường, cần thận trọng.",
    SPREAD_ABNORMAL: "Spread đang bất thường, không nên mở lệnh mới.",
    HIGH_IMPACT_NEWS_NEARBY: "Có tin kinh tế tác động cao trong 30 phút tới, không nên vào lệnh.",
    DATA_QUALITY_WARNING: "Cảnh báo chất lượng dữ liệu, cần kiểm tra lại.",
    MT5_NOT_READY: "MT5 chưa sẵn sàng hoặc broker chưa đăng nhập.",
    # R:R
    EXPECTED_RR_OK: "Tỷ lệ R:R kỳ vọng đạt yêu cầu.",
    EXPECTED_RR_TOO_LOW: "Tỷ lệ R:R kỳ vọng thấp hơn mức tối thiểu, chỉ nên theo dõi.",
    # Account guard
    DAILY_LOSS_LIMIT_REACHED: "Đã chạm giới hạn thua lỗ trong ngày, tạm dừng giao dịch mới.",
    WEEKLY_LOSS_LIMIT_REACHED: "Đã chạm giới hạn thua lỗ trong tuần, tạm dừng giao dịch mới.",
    MAX_CONSECUTIVE_LOSSES_REACHED: "Số lệnh thua liên tiếp đã chạm giới hạn, tạm dừng giao dịch mới.",
    MAX_OPEN_RISK_REACHED: "Tổng rủi ro đang mở đã chạm giới hạn, không mở thêm lệnh mới.",
    # Macro
    MACRO_ALIGNED: "Bối cảnh vĩ mô ủng hộ hướng giao dịch.",
    MACRO_UNCLEAR: "Bối cảnh vĩ mô chưa rõ ràng, chưa thể đánh giá.",
    MACRO_CONFLICT: "Bối cảnh vĩ mô xung đột với hướng giao dịch.",
    # Score gap
    BUY_SELL_SCORE_GAP_LOW: "Điểm Buy và Sell quá sát nhau, thị trường chưa rõ hướng.",
    # Statistical edge
    STAT_EDGE_NOT_ENOUGH_DATA: "Chưa đủ dữ liệu thống kê để đánh giá lợi thế.",
    STAT_EDGE_POSITIVE: "Lợi thế thống kê đang tích cực cho setup này.",
    STAT_EDGE_NEGATIVE: "Lợi thế thống kê đang tiêu cực cho setup này.",
    # Execution quality
    EXECUTION_QUALITY_OK: "Chất lượng thực thi lệnh đạt yêu cầu.",
    EXECUTION_CHASED_PRICE: "Đã đuổi giá khi vào lệnh, không đúng kế hoạch.",
    EXECUTION_OVERSIZED: "Khối lượng lệnh vượt quá kế hoạch.",
    EXECUTION_MOVED_SL_FURTHER: "Đã dời SL xa hơn kế hoạch, tăng rủi ro.",
    EXECUTION_REVENGE_CONFIRMED: "Giao dịch trả thù sau lệnh thua, không tuân thủ kế hoạch.",
    EXECUTION_MANUAL_PENALTY: "Hình phạt thủ công từ trader.",
    EXECUTION_DATA_INCOMPLETE: "Dữ liệu thực thi chưa đầy đủ để đánh giá chất lượng.",
    # Trade mistake detector
    MISTAKE_ENTERED_TOO_EARLY: "Vào lệnh quá sớm, chưa đủ xác nhận từ hệ thống.",
    MISTAKE_CHASED_PRICE: "Vào lệnh bị đuổi giá so với kế hoạch.",
    MISTAKE_IGNORED_M15: "Bỏ qua xác nhận M15 khi vào lệnh.",
    MISTAKE_IGNORED_NEWS: "Bỏ qua cảnh báo tin tức khi vào lệnh.",
    MISTAKE_MOVED_STOP_LOSS: "Dời stop loss làm tăng rủi ro so với kế hoạch.",
    MISTAKE_CLOSED_TOO_EARLY: "Chốt lệnh quá sớm, chưa đạt kỳ vọng R:R.",
    MISTAKE_OVERSIZED_POSITION: "Khối lượng thực tế lớn hơn kế hoạch.",
    MISTAKE_REVENGE_TRADE_WARNING: "Có dấu hiệu revenge trade sau lệnh thua.",
    MISTAKE_REVENGE_TRADE_CONFIRMED: "Có dấu hiệu revenge trade rõ ràng sau lệnh thua.",
    MISTAKE_DATA_INCOMPLETE: "Dữ liệu giao dịch chưa đầy đủ để phát hiện lỗi hành vi.",
    MISTAKE_DETECTOR_OK: "Không phát hiện lỗi hành vi giao dịch.",
    # Final score
    FINAL_SCORE_OK: "Đã tính final score từ signal, evidence và execution quality.",
    FINAL_SCORE_DATA_INCOMPLETE: "Thiếu một phần dữ liệu đầu vào, final score dùng fallback an toàn.",
    FINAL_SCORE_SIGNAL_DOMINANT: "Final score chủ yếu dựa trên signal score vì còn thiếu dữ liệu evidence/execution.",
    FINAL_SCORE_EVIDENCE_NEUTRAL: "Evidence score đang trung lập hoặc chưa đủ mẫu.",
    FINAL_SCORE_EVIDENCE_POSITIVE: "Evidence score tích cực, củng cố final score.",
    FINAL_SCORE_EVIDENCE_NEGATIVE: "Evidence score tiêu cực, làm giảm final score.",
    FINAL_SCORE_EXECUTION_STRONG: "Execution quality cao, hỗ trợ final score.",
    FINAL_SCORE_EXECUTION_WEAK: "Execution quality thấp, làm giảm final score.",
    # Decision engine
    DECISION_READY_TO_TRADE: "Đủ điều kiện để cân nhắc vào lệnh.",
    DECISION_WAITING_CONFIRMATION: "Chờ thêm xác nhận trước khi vào lệnh.",
    DECISION_AGGRESSIVE_SETUP: "Setup mạo hiểm, có thể vào lệnh với khối lượng nhỏ hơn.",
    DECISION_WATCH_ONLY: "Chỉ theo dõi, chưa đủ điều kiện vào lệnh.",
    DECISION_TRADE_BLOCKED: "Giao dịch bị chặn, không được phép mở lệnh mới.",
    DECISION_STAND_ASIDE: "Đứng ngoài, không có setup đáng giao dịch.",
    DECISION_DATA_INCOMPLETE: "Thiếu dữ liệu đầu vào cho decision engine.",
    DECISION_GATE_BLOCKED: "Gate đã chặn giao dịch này.",
    DECISION_GATE_CAPPED: "Gate đã giới hạn mức quyết định.",
    DECISION_SCORE_GAP_LOW: "Khoảng cách điểm Buy/Sell quá thấp, thị trường chưa rõ hướng.",
    DECISION_ENTRY_NOT_CONFIRMED: "Entry chưa được xác nhận đầy đủ.",
    DECISION_FINAL_SCORE_STRONG: "Final score đủ mạnh để xem xét vào lệnh.",
    DECISION_FINAL_SCORE_MODERATE: "Final score ở mức trung bình, cần thêm xác nhận.",
    DECISION_FINAL_SCORE_WEAK: "Final score quá thấp, không đủ điều kiện giao dịch.",
    # Scanner ranking
    SCANNER_RANKING_READY_NOW: "Scanner xếp nhóm sẵn sàng giao dịch.",
    SCANNER_RANKING_WAITING_CONFIRMATION: "Scanner xếp nhóm chờ xác nhận.",
    SCANNER_RANKING_WATCH_ZONE: "Scanner xếp nhóm chỉ theo dõi.",
    SCANNER_RANKING_BLOCKED: "Scanner xếp nhóm bị chặn.",
    SCANNER_OPPORTUNITY_SCORE_OK: "Đã tính điểm cơ hội scanner.",
    SCANNER_OPPORTUNITY_DATA_INCOMPLETE: "Thiếu dữ liệu để tính điểm cơ hội scanner.",
    SCANNER_PROXIMITY_IN_ZONE: "Giá đang nằm trong vùng entry.",
    SCANNER_PROXIMITY_NEAR_ZONE: "Giá đang gần vùng entry.",
    SCANNER_PROXIMITY_FAR: "Giá đang xa vùng entry.",
    SCANNER_RR_STRONG: "R:R hấp dẫn, tăng điểm cơ hội scanner.",
    SCANNER_RR_WEAK: "R:R chưa đủ hấp dẫn cho cơ hội scanner.",
    SCANNER_NEWS_PENALTY: "Scanner trừ điểm do tin tức gần.",
    SCANNER_SPREAD_PENALTY: "Scanner trừ điểm do spread bất thường.",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_codes(codes: list[str] | tuple[str, ...] | None) -> list[str]:
    """Return a deduplicated, order-preserving list of valid reason codes.

    - ``None`` input returns ``[]``.
    - Empty strings and ``None`` elements are dropped.
    - First occurrence wins; subsequent duplicates are ignored.
    """
    if codes is None:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for code in codes:
        if code is None:
            continue
        code = str(code)
        if code == "":
            continue
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def codes_to_messages(codes: list[str] | tuple[str, ...] | None) -> list[str]:
    """Map each code to its Vietnamese message.

    Known codes are translated via ``REASON_CODE_MESSAGES``; unknown codes
    are returned as-is so nothing is silently dropped.
    """
    normalized = normalize_codes(codes)
    return [REASON_CODE_MESSAGES.get(code, code) for code in normalized]


def append_code(target: list[str], code: str | None) -> None:
    """Append *code* to *target* if it is valid and not already present."""
    if code is None:
        return
    code = str(code)
    if code == "":
        return
    if code not in target:
        target.append(code)
