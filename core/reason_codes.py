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
ZONE_QUALITY_LOW = "ZONE_QUALITY_LOW"
ZONE_RELEVANCE_LOW = "ZONE_RELEVANCE_LOW"
ZONE_PRICE_RELATION_INVALID = "ZONE_PRICE_RELATION_INVALID"
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
EXECUTION_ZONE_RR_EMPTY = "EXECUTION_ZONE_RR_EMPTY"

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
MACRO_DATA_PARTIAL = "MACRO_DATA_PARTIAL"
MACRO_DATA_UNAVAILABLE = "MACRO_DATA_UNAVAILABLE"
MACRO_HIGH_IMPACT_EVENT_NEARBY = "MACRO_HIGH_IMPACT_EVENT_NEARBY"
# MacroGate (Step 05; target-only, not live-wired yet).  Missing/error/OPEN
# policy values fail closed to UNKNOWN instead of being coerced to PASS/neutral.
MACRO_NEUTRAL = "MACRO_NEUTRAL"
MACRO_DEADBAND_UNSET = "MACRO_DEADBAND_UNSET"
MACRO_CONFIDENCE_THRESHOLD_UNSET = "MACRO_CONFIDENCE_THRESHOLD_UNSET"
MACRO_LOW_CONFIDENCE = "MACRO_LOW_CONFIDENCE"
MACRO_CONFLICT_CAP_UNSET = "MACRO_CONFLICT_CAP_UNSET"
MACRO_UNKNOWN_CAP_UNSET = "MACRO_UNKNOWN_CAP_UNSET"
MACRO_SIDE_MISSING = "MACRO_SIDE_MISSING"

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
# FinalScore (Step 06; target-only, not live-wired yet).  Technical data
# missing/invalid must raise a typed error instead of legacy's optimistic fallbacks;
# evidence/execution missing/invalid fall back to exactly 50 neutral with a
# warning + source proving the fallback (never copied from technical).
FINAL_SCORE_DATA_UNAVAILABLE = "FINAL_SCORE_DATA_UNAVAILABLE"
FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK = "FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK"
FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK = "FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK"

# ---------------------------------------------------------------------------
# Composition (Step 07; target-only, not live-wired yet).  Deterministic
# pipeline: immutable snapshot -> safety + per-side technical -> gap/best side ->
# scenario -> evidence/execution -> FinalScore -> gates -> decision.  Gates never
# mutate scores; missing data/policy fails closed to UNKNOWN; stale/future
# snapshots are DATA_UNAVAILABLE.  No order payload, no READY_NOW (Step 08).
# ---------------------------------------------------------------------------
SNAPSHOT_STALE = "SNAPSHOT_STALE"
SNAPSHOT_FRESHNESS_UNKNOWN = "SNAPSHOT_FRESHNESS_UNKNOWN"
GATE_SCENARIO_PLAN_MISSING = "GATE_SCENARIO_PLAN_MISSING"
GATE_SCENARIO_POLICY_OPEN = "GATE_SCENARIO_POLICY_OPEN"
GATE_SCENARIO_RR_BLOCK = "GATE_SCENARIO_RR_BLOCK"
GATE_ACCOUNT_DATA_MISSING = "GATE_ACCOUNT_DATA_MISSING"
GATE_ACCOUNT_MARGIN_BLOCK = "GATE_ACCOUNT_MARGIN_BLOCK"
GATE_PORTFOLIO_DATA_MISSING = "GATE_PORTFOLIO_DATA_MISSING"
GATE_PORTFOLIO_POLICY_OPEN = "GATE_PORTFOLIO_POLICY_OPEN"
GATE_PORTFOLIO_LIMIT_BLOCK = "GATE_PORTFOLIO_LIMIT_BLOCK"
GATE_JOURNAL_DATA_MISSING = "GATE_JOURNAL_DATA_MISSING"
GATE_JOURNAL_POLICY_OPEN = "GATE_JOURNAL_POLICY_OPEN"
GATE_JOURNAL_REVENGE_BLOCK = "GATE_JOURNAL_REVENGE_BLOCK"
GATE_JOURNAL_DRAWDOWN_CAUTION = "GATE_JOURNAL_DRAWDOWN_CAUTION"
COMPOSE_FLOOR_POLICY_OPEN = "COMPOSE_FLOOR_POLICY_OPEN"
COMPOSE_SCORE_FLOOR_NOT_MET = "COMPOSE_SCORE_FLOOR_NOT_MET"
GATES_ALL_PASS = "GATES_ALL_PASS"

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
# Scanner contract/version validation (Step 02; target contract only)
# ---------------------------------------------------------------------------
SCANNER_SCHEMA_INVALID = "SCANNER_SCHEMA_INVALID"
SCANNER_VERSION_MISSING = "SCANNER_VERSION_MISSING"
SCANNER_VERSION_MISMATCH = "SCANNER_VERSION_MISMATCH"
SCANNER_FORBIDDEN_SCORED_FIELD = "SCANNER_FORBIDDEN_SCORED_FIELD"
SCANNER_LEGACY_V3_AUDIT_ONLY = "SCANNER_LEGACY_V3_AUDIT_ONLY"
SCANNER_BACKTEST_PARITY_VIOLATION = "SCANNER_BACKTEST_PARITY_VIOLATION"
SCANNER_JOURNAL_PARTITION_MIXED = "SCANNER_JOURNAL_PARTITION_MIXED"
SCANNER_SAFETY_AUDIT_MISSING = "SCANNER_SAFETY_AUDIT_MISSING"
SCANNER_SAFETY_AUDIT_NON_PIT = "SCANNER_SAFETY_AUDIT_NON_PIT"
SCANNER_SAFETY_AUDIT_UNKNOWN = "SCANNER_SAFETY_AUDIT_UNKNOWN"
SCANNER_CALIBRATION_INSUFFICIENT = "SCANNER_CALIBRATION_INSUFFICIENT"
SCANNER_CONFIG_NOT_ACTIVATABLE = "SCANNER_CONFIG_NOT_ACTIVATABLE"
TECHNICAL_DATA_UNAVAILABLE = "TECHNICAL_DATA_UNAVAILABLE"

# ---------------------------------------------------------------------------
# MarketSafetyGate sub-gate reasons (Step 04; target-only, not live-wired yet)
# Chỉ chốt các sub-gate sẵn policy. Những mục policy còn OPEN (spread per symbol,
# candle freshness SLA, volatility band) fail-closed về UNKNOWN khi chưa được
# cấu hình/calibrate; không đặt optimistic default thay thế vì không có căn cứ.
# ---------------------------------------------------------------------------
# Connectivity
SAFETY_MT5_NOT_READY = "SAFETY_MT5_NOT_READY"
SAFETY_MT5_STATE_UNKNOWN = "SAFETY_MT5_STATE_UNKNOWN"
# Data / candle freshness
SAFETY_DATA_STALE = "SAFETY_DATA_STALE"
SAFETY_DATA_FRESHNESS_UNKNOWN = "SAFETY_DATA_FRESHNESS_UNKNOWN"
# Spread
SAFETY_SPREAD_ABNORMAL = "SAFETY_SPREAD_ABNORMAL"
SAFETY_SPREAD_THRESHOLD_UNSET = "SAFETY_SPREAD_THRESHOLD_UNSET"
SAFETY_SPREAD_UNKNOWN = "SAFETY_SPREAD_UNKNOWN"
# News / event window (LOCKED: 0-30m BLOCK, 30m-3h CAUTION)
SAFETY_NEWS_HIGH_IMPACT_BLOCK = "SAFETY_NEWS_HIGH_IMPACT_BLOCK"
SAFETY_NEWS_HIGH_IMPACT_CAUTION = "SAFETY_NEWS_HIGH_IMPACT_CAUTION"
SAFETY_NEWS_SOURCE_UNAVAILABLE = "SAFETY_NEWS_SOURCE_UNAVAILABLE"
# Volatility (band OPEN -> UNKNOWN until calibrated)
SAFETY_VOLATILITY_EXTREME = "SAFETY_VOLATILITY_EXTREME"
SAFETY_VOLATILITY_BAND_UNSET = "SAFETY_VOLATILITY_BAND_UNSET"
SAFETY_VOLATILITY_UNKNOWN = "SAFETY_VOLATILITY_UNKNOWN"

# ---------------------------------------------------------------------------
# Candidate / decision (Step 08; target-only, not live-wired yet).  The
# decision layer consumes ONLY the Step 07 canonical output: Step 07 gate caps
# (DATA_UNAVAILABLE / BLOCKED) can never be promoted, floors/gap/R:R come from
# the ONE versioned threshold contract, READY_NOW additionally requires a
# confirmed entry and a fresh execution signal, and the order payload is only
# ever prepared (never sent) until cutover (Step 12).
# ---------------------------------------------------------------------------
THRESHOLD_POLICY_OPEN = "THRESHOLD_POLICY_OPEN"
THRESHOLD_SCORE_FLOOR_NOT_MET = "THRESHOLD_SCORE_FLOOR_NOT_MET"
THRESHOLD_GAP_NOT_MET = "THRESHOLD_GAP_NOT_MET"
THRESHOLD_RR_NOT_MET = "THRESHOLD_RR_NOT_MET"
ENTRY_CONFIRMED = "ENTRY_CONFIRMED"
ENTRY_UNCONFIRMED = "ENTRY_UNCONFIRMED"
ENTRY_CONFIRMATION_MISSING = "ENTRY_CONFIRMATION_MISSING"
EXECUTION_FRESH_OK = "EXECUTION_FRESH_OK"
EXECUTION_NOT_READY = "EXECUTION_NOT_READY"
EXECUTION_REVALIDATION_REQUIRED = "EXECUTION_REVALIDATION_REQUIRED"
ORDER_PREPARED = "ORDER_PREPARED"
ORDER_NOT_PREPARED = "ORDER_NOT_PREPARED"
CANDIDATE_SIDE_INCONSISTENT = "CANDIDATE_SIDE_INCONSISTENT"

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
    ZONE_RELEVANCE_LOW: "Vùng giá không còn đủ liên quan với bối cảnh hiện tại.",
    ZONE_PRICE_RELATION_INVALID: "Quan hệ giữa giá hiện tại và vùng entry không hợp lệ.",
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
    EXECUTION_ZONE_RR_EMPTY: "Execution zone không còn mức giá đạt R:R hiệu dụng tối thiểu.",
    # Account guard
    DAILY_LOSS_LIMIT_REACHED: "Đã chạm giới hạn thua lỗ trong ngày, tạm dừng giao dịch mới.",
    WEEKLY_LOSS_LIMIT_REACHED: "Đã chạm giới hạn thua lỗ trong tuần, tạm dừng giao dịch mới.",
    MAX_CONSECUTIVE_LOSSES_REACHED: "Số lệnh thua liên tiếp đã chạm giới hạn, tạm dừng giao dịch mới.",
    MAX_OPEN_RISK_REACHED: "Tổng rủi ro đang mở đã chạm giới hạn, không mở thêm lệnh mới.",
    # Macro
    MACRO_ALIGNED: "Bối cảnh vĩ mô ủng hộ hướng giao dịch.",
    MACRO_UNCLEAR: "Bối cảnh vĩ mô chưa rõ ràng, chưa thể đánh giá.",
    MACRO_CONFLICT: "Bối cảnh vĩ mô xung đột với hướng giao dịch.",
    MACRO_DATA_PARTIAL: "Thiếu một phần dữ liệu vĩ mô, giảm nhẹ mức tin cậy.",
    MACRO_DATA_UNAVAILABLE: "Thiếu toàn bộ dữ liệu vĩ mô, giảm mạnh mức tin cậy.",
    MACRO_HIGH_IMPACT_EVENT_NEARBY: "Sắp có sự kiện vĩ mô tác động mạnh liên quan đến đồng tiền của cặp, giảm mức tin cậy.",
    # MacroGate (Step 05; target-only)
    MACRO_NEUTRAL: "Bối cảnh vĩ mô trung lập, không nghiêng về bên nào.",
    MACRO_DEADBAND_UNSET: "Chưa calibrate deadband BUY/SELL — không chứng nhận được hướng vĩ mô (fail-closed UNKNOWN).",
    MACRO_CONFIDENCE_THRESHOLD_UNSET: "Chưa khóa ngưỡng confidence vĩ mô — không chứng nhận được độ tin cậy (fail-closed UNKNOWN).",
    MACRO_LOW_CONFIDENCE: "Confidence vĩ mô dưới ngưỡng đã khóa — không tin tưởng định hướng vĩ mô (fail-closed UNKNOWN).",
    MACRO_CONFLICT_CAP_UNSET: "Chưa chốt conflict cap — xung đột vĩ mô chưa có chính sách xử lý (fail-closed UNKNOWN).",
    MACRO_UNKNOWN_CAP_UNSET: "Chưa chốt unknown cap — trạng thái chưa rõ chưa có chính sách xử lý (fail-closed UNKNOWN).",
    MACRO_SIDE_MISSING: "Thiếu assessed side — không thể đánh giá hướng vĩ mô (fail-closed UNKNOWN).",
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
    # FinalScore (Step 06)
    FINAL_SCORE_DATA_UNAVAILABLE: "Dữ liệu technical signal thiếu hoặc không hợp lệ, không thể tính final score.",
    FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK: "Evidence thiếu/không hợp lệ, final score dùng 50 neutral thay thế an toàn.",
    FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK: "Execution quality thiếu/không hợp lệ, final score dùng 50 neutral thay thế an toàn.",
    # Composition (Step 07)
    SNAPSHOT_STALE: "Snapshot quá cũ so với now, không còn đủ mới để đánh giá.",
    SNAPSHOT_FRESHNESS_UNKNOWN: "Timestamp snapshot ở tương lai, không chứng nhận độ mới được.",
    GATE_SCENARIO_PLAN_MISSING: "Thiếu kế hoạch vào lệnh (entry/SL/TP), không dựng được scenario.",
    GATE_SCENARIO_POLICY_OPEN: "Ngưỡng scenario (min R:R) chưa được calibrate, gate không chứng nhận được.",
    GATE_SCENARIO_RR_BLOCK: "R:R của scenario thấp hơn ngưỡng tối thiểu, chặn kế hoạch.",
    GATE_ACCOUNT_DATA_MISSING: "Thiếu dữ liệu account (balance/margin), gate fail-closed UNKNOWN.",
    GATE_ACCOUNT_MARGIN_BLOCK: "Free margin không đủ cho kế hoạch, không mở được lệnh.",
    GATE_PORTFOLIO_DATA_MISSING: "Thiếu dữ liệu portfolio (vị thế mở/exposure), gate fail-closed UNKNOWN.",
    GATE_PORTFOLIO_POLICY_OPEN: "Ngưỡng portfolio (số vị thế/exposure) chưa được calibrate.",
    GATE_PORTFOLIO_LIMIT_BLOCK: "Đã chạm giới hạn portfolio, không mở thêm lệnh.",
    GATE_JOURNAL_DATA_MISSING: "Thiếu dữ liệu journal, gate fail-closed UNKNOWN.",
    GATE_JOURNAL_POLICY_OPEN: "Ngưỡng journal (drawdown) chưa được calibrate.",
    GATE_JOURNAL_REVENGE_BLOCK: "Phát hiện dấu hiệu revenge trade theo journal, chặn lệnh.",
    GATE_JOURNAL_DRAWDOWN_CAUTION: "Chuỗi lệnh thua vượt ngưỡng, cảnh báo không vào lệnh mới.",
    COMPOSE_FLOOR_POLICY_OPEN: "Ngưỡng score (technical/setup floor) chưa được calibrate, không chứng nhận WAITING_CONFIRMATION.",
    COMPOSE_SCORE_FLOOR_NOT_MET: "Score của side được chọn dưới floor, không đạt điều kiện chờ vào lệnh.",
    GATES_ALL_PASS: "Mọi gate trong composition đều PASS, chưa có gì chặn.",
    # Candidate / decision (Step 08)
    THRESHOLD_POLICY_OPEN: "Threshold contract chưa có giá trị calibrate cho floor/gap/R:R, fail-closed không promote.",
    THRESHOLD_SCORE_FLOOR_NOT_MET: "Score của side được chọn dưới floor của threshold contract.",
    THRESHOLD_GAP_NOT_MET: "Chênh lệch score giữa hai side dưới min_score_gap của threshold contract.",
    THRESHOLD_RR_NOT_MET: "Tỷ lệ risk/reward của scenario dưới min_risk_reward của threshold contract.",
    ENTRY_CONFIRMED: "Entry đã được xác nhận, đủ điều kiện cân nhắc READY_NOW.",
    ENTRY_UNCONFIRMED: "Entry chưa được xác nhận, giới hạn ở WAITING_CONFIRMATION.",
    ENTRY_CONFIRMATION_MISSING: "Thiếu trạng thái xác nhận entry, fail-closed xem như chưa xác nhận.",
    EXECUTION_FRESH_OK: "Snapshot không stale/future, execution có thể dựa trên dữ liệu hiện hành.",
    EXECUTION_NOT_READY: "Execution chưa sẵn sàng, giới hạn ở WAITING_CONFIRMATION.",
    EXECUTION_REVALIDATION_REQUIRED: "READY_NOW vẫn phải revalidate execution trước khi đặt lệnh (cutover).",
    ORDER_PREPARED: "Order payload đã dựng sẵn theo identity đầy đủ, chưa gửi lệnh thật.",
    ORDER_NOT_PREPARED: "Trạng thái candidate chưa cho phép dựng order payload.",
    CANDIDATE_SIDE_INCONSISTENT: "Side của decision không khớp score/scenario/gate, fail-closed DATA_UNAVAILABLE.",
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
    # Scanner contract/version validation
    SCANNER_SCHEMA_INVALID: "Payload Scanner không đúng canonical schema.",
    SCANNER_VERSION_MISSING: "Payload thiếu version/schema bắt buộc.",
    SCANNER_VERSION_MISMATCH: "Payload không khớp version/schema đã khóa.",
    SCANNER_FORBIDDEN_SCORED_FIELD: "Payload chứa Risk hoặc Macro dưới dạng scored component bị cấm.",
    SCANNER_LEGACY_V3_AUDIT_ONLY: "Artifact Scanner V3 chỉ được giữ để audit và không thể replay bằng runtime.",
    SCANNER_BACKTEST_PARITY_VIOLATION: "Backtest không dùng cùng composition/semantics với live (parity contract bị vi phạm).",
    SCANNER_JOURNAL_PARTITION_MIXED: "Không được trộn journal evidence từ các partition scorer/policy khác nhau.",
    SCANNER_SAFETY_AUDIT_MISSING: "Thiếu dữ liệu historical point-in-time cho safety sub-gate; không tự giả định bình thường.",
    SCANNER_SAFETY_AUDIT_NON_PIT: "Nguồn data có nhưng không point-in-time; không đủ điều kiện cho calibration/auto-entry.",
    SCANNER_SAFETY_AUDIT_UNKNOWN: "Trạng thái dữ liệu safety không xác định — fail-closed UNKNOWN, không PASS.",
    SCANNER_CALIBRATION_INSUFFICIENT: "Sample calibration không đủ min evidence; giữ threshold fail-closed, không chốt production.",
    SCANNER_CONFIG_NOT_ACTIVATABLE: "Config chưa đủ điều kiện activate (version/schema/fingerprint/evidence) — backtest=False.",
    # Legacy v4-moniker alias keys (read-only migration 2026-08-17): artifacts
    # written before the icon renaming carry the old "SCANNER_V4_*"/"V4_*" code
    # values; keep their Vietnamese translation so old journals/reports still
    # render.  These literal keys intentionally keep the v4 spelling.
    "SCANNER_V4_SCHEMA_INVALID": "Payload Scanner không đúng canonical schema.",
    "SCANNER_V4_VERSION_MISSING": "Payload thiếu version/schema bắt buộc.",
    "SCANNER_V4_VERSION_MISMATCH": "Payload không khớp version/schema đã khóa.",
    "SCANNER_V4_FORBIDDEN_SCORED_FIELD": "Payload chứa Risk hoặc Macro dưới dạng scored component bị cấm.",
    "SCANNER_V4_LEGACY_V3_AUDIT_ONLY": "Artifact Scanner V3 chỉ được giữ để audit và không thể replay bằng runtime.",
    "SCANNER_V4_BACKTEST_PARITY_VIOLATION": "Backtest không dùng cùng composition/semantics với live (parity contract bị vi phạm).",
    "SCANNER_V4_JOURNAL_PARTITION_MIXED": "Không được trộn journal evidence từ các partition scorer/policy khác nhau.",
    "SCANNER_V4_SAFETY_AUDIT_MISSING": "Thiếu dữ liệu historical point-in-time cho safety sub-gate; không tự giả định bình thường.",
    "SCANNER_V4_SAFETY_AUDIT_NON_PIT": "Nguồn data có nhưng không point-in-time; không đủ điều kiện cho calibration/auto-entry.",
    "SCANNER_V4_SAFETY_AUDIT_UNKNOWN": "Trạng thái dữ liệu safety không xác định — fail-closed UNKNOWN, không PASS.",
    "SCANNER_V4_CALIBRATION_INSUFFICIENT": "Sample calibration không đủ min evidence; giữ threshold fail-closed, không chốt production.",
    "SCANNER_V4_CONFIG_NOT_ACTIVATABLE": "Config chưa đủ điều kiện activate (version/schema/fingerprint/evidence) — backtest=False.",
    "V4_THRESHOLD_POLICY_OPEN": "Threshold contract chưa có giá trị calibrate cho floor/gap/R:R, fail-closed không promote.",
    "V4_THRESHOLD_SCORE_FLOOR_NOT_MET": "Score của side được chọn dưới floor của threshold contract.",
    "V4_THRESHOLD_GAP_NOT_MET": "Chênh lệch score giữa hai side dưới min_score_gap của threshold contract.",
    "V4_THRESHOLD_RR_NOT_MET": "Tỷ lệ risk/reward của scenario dưới min_risk_reward của threshold contract.",
    "V4_ENTRY_CONFIRMED": "Entry đã được xác nhận, đủ điều kiện cân nhắc READY_NOW.",
    "V4_ENTRY_UNCONFIRMED": "Entry chưa được xác nhận, giới hạn ở WAITING_CONFIRMATION.",
    "V4_ENTRY_CONFIRMATION_MISSING": "Thiếu trạng thái xác nhận entry, fail-closed xem như chưa xác nhận.",
    "V4_EXECUTION_FRESH_OK": "Snapshot không stale/future, execution có thể dựa trên dữ liệu hiện hành.",
    "V4_EXECUTION_NOT_READY": "Execution chưa sẵn sàng, giới hạn ở WAITING_CONFIRMATION.",
    "V4_EXECUTION_REVALIDATION_REQUIRED": "READY_NOW vẫn phải revalidate execution trước khi đặt lệnh (cutover).",
    "V4_ORDER_PREPARED": "Order payload đã dựng sẵn theo identity đầy đủ, chưa gửi lệnh thật.",
    "V4_ORDER_NOT_PREPARED": "Trạng thái candidate chưa cho phép dựng order payload.",
    "V4_CANDIDATE_SIDE_INCONSISTENT": "Side của decision không khớp score/scenario/gate, fail-closed DATA_UNAVAILABLE.",
    # MarketSafetyGate (Step 04; target-only)
    SAFETY_MT5_NOT_READY: "Connectivity: MT5 chưa sẵn sàng hoặc broker chưa đăng nhập — không vào lệnh.",
    SAFETY_MT5_STATE_UNKNOWN: "Connectivity: không xác định được trạng thái terminal/broker — fail-closed UNKNOWN.",
    SAFETY_DATA_STALE: "Dữ liệu candle cũ hơn freshness SLA — không vào lệnh trên dữ liệu lỗi thời.",
    SAFETY_DATA_FRESHNESS_UNKNOWN: "Freshness SLA hoặc mốc thời gian candle chưa xác định — fail-closed UNKNOWN.",
    SAFETY_SPREAD_ABNORMAL: "Spread vượt ngưỡng an toàn cho symbol — không vào lệnh.",
    SAFETY_SPREAD_THRESHOLD_UNSET: "Chưa có ngưỡng spread theo symbol — fail-closed UNKNOWN (policy mở).",
    SAFETY_SPREAD_UNKNOWN: "Spread chưa xác định được — fail-closed UNKNOWN.",
    SAFETY_NEWS_HIGH_IMPACT_BLOCK: "Tin tác động cao trong 0-30 phút tới — chặn vào lệnh.",
    SAFETY_NEWS_HIGH_IMPACT_CAUTION: "Tin tác động cao trong 30 phút-3 giờ tới — thận trọng,ganh theo xác nhận sau.",
    SAFETY_NEWS_SOURCE_UNAVAILABLE: "Không xác nhận được nguồn tin — fail-closed UNKNOWN (không tự gán PASS).",
    SAFETY_VOLATILITY_EXTREME: "Độ biến động vượt band đã calibrate — thận trọng, độ biến động bất thường.",
    SAFETY_VOLATILITY_BAND_UNSET: "Chưa calibrate band volatility — fail-closed UNKNOWN (không tự gán CAUTION).",
    SAFETY_VOLATILITY_UNKNOWN: "Chỉ số volatility chưa xác định — fail-closed UNKNOWN.",
    TECHNICAL_DATA_UNAVAILABLE: "Thiếu hoặc sai dữ liệu bắt buộc để tính TechnicalSignalScore.",
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


def merge_unique_codes(*groups: object) -> list[str]:
    """Merge multiple code lists, deduplicating while preserving order.

    - Skips ``None`` groups and non-list/tuple/set items.
    - Skips ``None`` elements and empty strings.
    - Never raises.
    """
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        if group is None:
            continue
        if not isinstance(group, (list, tuple, set)):
            continue
        for code in group:
            if code is None:
                continue
            s = str(code).strip()
            if not s:
                continue
            if s not in seen:
                seen.add(s)
                result.append(s)
    return result
