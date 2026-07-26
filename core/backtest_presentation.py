"""Presentation-safe lifecycle and action policy for Backtest results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BACKTEST_PRESENTATION_VERSION = "backtest-presentation-v1"

ACTION_NONE = "NONE"
ACTION_SAVE_DRAFT = "SAVE_DRAFT"
ACTION_APPLY_VALIDATED = "APPLY_VALIDATED"


@dataclass(frozen=True, slots=True)
class BacktestResultAction:
    kind: str
    label: str
    visible: bool
    reason: str


_STATUS_LABELS = {
    "RESEARCH_ONLY": "Chỉ dùng để nghiên cứu",
    "DRAFT": "Bản nháp cần kiểm tra thêm",
    "VALIDATED": "Đã kiểm chứng",
    "RELEASE_READY": "Đã sẵn sàng phát hành",
    "REVIEW_REQUIRED": "Cần xem xét trước khi phát hành",
    "LEGACY_RESEARCH": "Kết quả cũ, chỉ dùng để tham khảo",
}

_REASON_LABELS = {
    "VALIDATION_REPLAY_COMPLETE": "Đã hoàn tất kiểm chứng ngoài mẫu.",
    "CONFIG_NOT_REVIEWED_OR_PUBLISHED": "Cấu hình chưa được duyệt và phát hành.",
    "PURPOSE_OR_EVIDENCE_NOT_RELEASE_ELIGIBLE": "Đây là kết quả nghiên cứu hoặc chưa đủ bằng chứng để phát hành.",
    "BATCH_PORTFOLIO_NOT_PUBLISHABLE_AS_SYMBOL_CONFIG": "Kết quả nhiều mã chỉ dùng để đánh giá danh mục, không áp cho một mã riêng lẻ.",
    "LEGACY_BACKTEST_ENGINE": "Kết quả được tạo bằng engine cũ.",
    "REVALIDATION_WITH_CURRENT_ENGINE_REQUIRED": "Cần chạy lại bằng engine hiện hành.",
    "RELEASE_REPORT_REQUIRED": "Chưa có báo cáo phát hành đạt yêu cầu.",
    "FROZEN_OOS_REPLAY_REQUIRED": "Chưa có kiểm chứng ngoài mẫu bằng cấu hình đã đóng băng.",
    "IS_CANDIDATE_SAMPLE_TOO_SMALL": "Số mẫu trong giai đoạn huấn luyện còn quá ít.",
    "OOS_SAMPLE_TOO_SMALL": "Số lệnh kiểm chứng ngoài mẫu còn quá ít.",
    "OOS_EXPECTANCY_TOO_LOW": "Kỳ vọng lợi nhuận ngoài mẫu chưa đạt yêu cầu.",
    "OOS_PROFIT_FACTOR_TOO_LOW": "Hệ số lợi nhuận ngoài mẫu chưa đạt yêu cầu.",
    "OOS_DRAWDOWN_TOO_HIGH": "Mức sụt giảm vốn ngoài mẫu vượt giới hạn.",
    "OOS_EXPECTANCY_CI_NOT_POSITIVE": "Khoảng tin cậy của kỳ vọng ngoài mẫu chưa dương.",
    "OOS_POSITIVE_EDGE_PROBABILITY_TOO_LOW": "Xác suất có lợi thế dương chưa đủ cao.",
    "OOS_EDGE_P_VALUE_TOO_HIGH": "Bằng chứng thống kê về lợi thế chưa đủ mạnh.",
    "OOS_STATISTICAL_POWER_INSUFFICIENT": "Cỡ mẫu chưa đủ mạnh về mặt thống kê.",
    "WALK_FORWARD_MISSING": "Chưa có kết quả kiểm tra cuốn chiếu Walk-Forward.",
    "WALK_FORWARD_WINDOWS_TOO_FEW": "Số cửa sổ Walk-Forward còn quá ít.",
    "WALK_FORWARD_NOT_ROBUST": "Kết quả Walk-Forward chưa đủ ổn định.",
    "WALK_FORWARD_OOS_SAMPLE_TOO_SMALL": "Mẫu ngoài kỳ trong Walk-Forward còn quá ít.",
    "WALK_FORWARD_OOS_EXPECTANCY_TOO_LOW": "Kỳ vọng ngoài kỳ trong Walk-Forward chưa đạt.",
    "VALIDATED_DATA_TOO_OLD": "Dữ liệu kiểm chứng đã quá cũ.",
    "BACKTEST_RELEASE_REPORT_MISSING": "Chưa có báo cáo phát hành.",
    "BACKTEST_RELEASE_REPORT_NOT_READY": "Báo cáo phát hành chưa đạt.",
    "BACKTEST_RELEASE_REPORT_HAS_BLOCKS": "Báo cáo phát hành vẫn còn điều kiện bị chặn.",
    "RELEASE_REVIEWER_REQUIRED": "Chưa có người chịu trách nhiệm duyệt phát hành.",
    "RELEASE_REVIEW_NOT_APPROVED": "Báo cáo phát hành chưa được phê duyệt.",
    "FORWARD_SAMPLE_TOO_SMALL": "Chưa đủ giao dịch chạy thử để đánh giá.",
    "FORWARD_FILL_RATE_TOO_LOW": "Tỷ lệ khớp lệnh chạy thử còn thấp.",
    "FORWARD_REJECTION_RATE_TOO_HIGH": "Tỷ lệ lệnh bị từ chối trong chạy thử còn cao.",
    "FORWARD_SLIPPAGE_TOO_HIGH": "Trượt giá chạy thử vượt giới hạn.",
    "FORWARD_PERFORMANCE_DEGRADATION_TOO_HIGH": "Hiệu suất chạy thử suy giảm quá nhiều.",
    "ENGINE_SHADOW_SAMPLE_TOO_SMALL": "Chưa đủ mẫu để so sánh hai engine.",
    "ENGINE_SHADOW_DISAGREEMENT_TOO_HIGH": "Hai engine còn cho kết quả khác nhau quá nhiều.",
    "GOLDEN_REPLAY_NOT_PASSED": "Bộ kiểm thử chuẩn chưa đạt.",
}


def snapshot_symbols(payload: object) -> tuple[str, ...]:
    """Return the ordered, unique symbols owned by a snapshot."""

    if not isinstance(payload, dict):
        return ()
    values: list[str] = []

    def add(value: object) -> None:
        symbol = str(value or "").strip()
        if symbol and symbol not in values:
            values.append(symbol)

    request = payload.get("request")
    if isinstance(request, dict):
        add(request.get("symbol"))
        symbols = request.get("symbols")
        if isinstance(symbols, list):
            for symbol in symbols:
                add(symbol)

    replay = payload.get("validation_replay")
    replay_request = replay.get("request") if isinstance(replay, dict) else None
    if isinstance(replay_request, dict):
        add(replay_request.get("symbol"))

    children = payload.get("symbols")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                child_request = child.get("request")
                if isinstance(child_request, dict):
                    add(child_request.get("symbol"))

    if not values:
        trades = payload.get("trades")
        if isinstance(trades, list):
            for trade in trades:
                if isinstance(trade, dict):
                    add(trade.get("symbol"))
    return tuple(values)


def result_action(
    payload: object,
    *,
    selected_symbol: str = "",
) -> BacktestResultAction:
    if not isinstance(payload, dict):
        return _no_action("NO_RESULT")
    if payload.get("mode") == "portfolio_backtest":
        return _no_action("PORTFOLIO_RESEARCH_ONLY")

    symbols = snapshot_symbols(payload)
    if len(symbols) != 1:
        return _no_action("SINGLE_SYMBOL_SNAPSHOT_REQUIRED")
    if selected_symbol and symbols[0] != str(selected_symbol).strip():
        return _no_action("SNAPSHOT_SYMBOL_MISMATCH")

    lifecycle = payload.get("lifecycle")
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    status = str(lifecycle.get("status") or "RESEARCH_ONLY").upper()
    can_publish = lifecycle.get("can_publish_config") is True
    if can_publish or status in {"VALIDATED", "RELEASE_READY"}:
        return BacktestResultAction(
            ACTION_APPLY_VALIDATED,
            "📋 Áp dụng cấu hình",
            True,
            "VALIDATED_RESULT",
        )
    if status == "DRAFT":
        return BacktestResultAction(
            ACTION_SAVE_DRAFT,
            "💾 Lưu đề xuất nháp",
            True,
            "DRAFT_RESULT",
        )
    return _no_action(f"LIFECYCLE_{status}_NOT_ACTIONABLE")


def lifecycle_status_label(status: object) -> str:
    normalized = str(status or "RESEARCH_ONLY").strip().upper()
    return _STATUS_LABELS.get(normalized, "Trạng thái chưa xác định")


def lifecycle_reason_label(reason: object) -> str:
    code = str(reason or "").strip().upper()
    if not code:
        return "Không có lý do chi tiết."
    return _REASON_LABELS.get(
        code,
        f"Chưa đạt một điều kiện kỹ thuật ({code}).",
    )


def lifecycle_reason_labels(reasons: object) -> list[str]:
    if not isinstance(reasons, (list, tuple)):
        return []
    return [lifecycle_reason_label(reason) for reason in reasons]


def _no_action(reason: str) -> BacktestResultAction:
    return BacktestResultAction(ACTION_NONE, "", False, reason)
